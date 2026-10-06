//! Sessions (refresh-token families) and refresh tokens.

use std::net::IpAddr;
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::jobs::after;
use dz_app::ports::{
    NewRefreshToken, NewSession, RevocationReason, RotateOutcome, SessionInfo, SessionRepository,
    TokenHash,
};
use dz_app::AppResult;
use dz_domain::ids::{SessionId, UserId};
use sqlx::types::ipnet::IpNet;
use sqlx::{Postgres, Transaction};

use super::{PgStore, db_error};

/// Revokes every active session of `user_id` (except `keep`) inside an open transaction.
pub(crate) async fn revoke_all_in(
    tx: &mut Transaction<'_, Postgres>,
    user_id: UserId,
    reason: &str,
    at: DateTime<Utc>,
    keep: Option<SessionId>,
) -> AppResult<Vec<SessionId>> {
    let ids = sqlx::query_scalar!(
        r#"
        UPDATE auth_sessions
        SET revoked_at = $2, revoked_reason = $3
        WHERE user_id = $1 AND revoked_at IS NULL AND ($4::uuid IS NULL OR id <> $4)
        RETURNING id
        "#,
        user_id.as_uuid(),
        at,
        reason,
        keep.map(|s| s.as_uuid()),
    )
    .fetch_all(&mut **tx)
    .await
    .map_err(db_error)?;
    Ok(ids.into_iter().map(SessionId::from_uuid).collect())
}

fn ip_to_net(ip: Option<IpAddr>) -> Option<IpNet> {
    ip.map(IpNet::from)
}

#[async_trait]
impl SessionRepository for PgStore {
    async fn create(&self, session: NewSession, token: NewRefreshToken) -> AppResult<()> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO auth_sessions (id, user_id, created_at, last_used_at, expires_at,
                                       user_agent, ip)
            VALUES ($1, $2, $3, $3, $4, $5, $6)
            "#,
            session.id.as_uuid(),
            session.user_id.as_uuid(),
            session.created_at,
            session.expires_at,
            session.user_agent,
            ip_to_net(session.ip),
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO refresh_tokens (token_hash, session_id, issued_at, expires_at)
            VALUES ($1, $2, $3, $4)
            "#,
            &token.hash.0[..],
            token.session_id.as_uuid(),
            token.issued_at,
            token.expires_at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok(())
    }

    async fn rotate(
        &self,
        presented: TokenHash,
        next: TokenHash,
        now: DateTime<Utc>,
        refresh_ttl: Duration,
    ) -> AppResult<RotateOutcome> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Lock both rows: two concurrent refreshes with the same token serialize here, and the
        // second one sees `used_at` set (reuse).
        let Some(row) = sqlx::query!(
            r#"
            SELECT rt.session_id, rt.expires_at, rt.used_at,
                   s.user_id, s.expires_at AS session_expires_at, s.revoked_at
            FROM refresh_tokens rt
            JOIN auth_sessions s ON s.id = rt.session_id
            WHERE rt.token_hash = $1
            FOR UPDATE OF rt, s
            "#,
            &presented.0[..],
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        else {
            return Ok(RotateOutcome::Invalid);
        };
        let user_id = UserId::from_uuid(row.user_id);
        let session_id = SessionId::from_uuid(row.session_id);

        if row.used_at.is_some() {
            if row.revoked_at.is_none() {
                sqlx::query!(
                    r#"
                    UPDATE auth_sessions SET revoked_at = $2, revoked_reason = 'refresh_token_reuse'
                    WHERE id = $1
                    "#,
                    row.session_id,
                    now,
                )
                .execute(&mut *tx)
                .await
                .map_err(db_error)?;
                tx.commit().await.map_err(db_error)?;
            }
            return Ok(RotateOutcome::Reused { user_id, session_id });
        }
        if row.revoked_at.is_some() || row.expires_at <= now || row.session_expires_at <= now {
            return Ok(RotateOutcome::Invalid);
        }

        let refresh_expires_at = after(now, refresh_ttl).min(row.session_expires_at);
        sqlx::query!(
            "UPDATE refresh_tokens SET used_at = $2 WHERE token_hash = $1",
            &presented.0[..],
            now,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO refresh_tokens (token_hash, session_id, issued_at, expires_at)
            VALUES ($1, $2, $3, $4)
            "#,
            &next.0[..],
            row.session_id,
            now,
            refresh_expires_at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!(
            "UPDATE auth_sessions SET last_used_at = $2 WHERE id = $1",
            row.session_id,
            now,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok(RotateOutcome::Rotated { user_id, session_id, refresh_expires_at })
    }

    async fn revoke(
        &self,
        user_id: UserId,
        session_id: SessionId,
        reason: RevocationReason,
        at: DateTime<Utc>,
    ) -> AppResult<bool> {
        let result = sqlx::query!(
            r#"
            UPDATE auth_sessions SET revoked_at = $3, revoked_reason = $4
            WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
            "#,
            session_id.as_uuid(),
            user_id.as_uuid(),
            at,
            reason.as_str(),
        )
        .execute(self.pool())
        .await
        .map_err(db_error)?;
        Ok(result.rows_affected() == 1)
    }

    async fn revoke_all(
        &self,
        user_id: UserId,
        reason: RevocationReason,
        at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let revoked = revoke_all_in(&mut tx, user_id, reason.as_str(), at, keep).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(revoked)
    }

    async fn list_active(
        &self,
        user_id: UserId,
        now: DateTime<Utc>,
    ) -> AppResult<Vec<SessionInfo>> {
        let rows = sqlx::query!(
            r#"
            SELECT id, user_id, created_at, last_used_at, expires_at, user_agent, ip
            FROM auth_sessions
            WHERE user_id = $1 AND revoked_at IS NULL AND expires_at > $2
            ORDER BY last_used_at DESC
            LIMIT 100
            "#,
            user_id.as_uuid(),
            now,
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        Ok(rows
            .into_iter()
            .map(|r| SessionInfo {
                id: SessionId::from_uuid(r.id),
                user_id: UserId::from_uuid(r.user_id),
                created_at: r.created_at,
                last_used_at: r.last_used_at,
                expires_at: r.expires_at,
                user_agent: r.user_agent,
                ip: r.ip.map(|net| net.addr()),
            })
            .collect())
    }

    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let sessions = sqlx::query!(
            r#"
            DELETE FROM auth_sessions
            WHERE expires_at < $1 OR (revoked_at IS NOT NULL AND revoked_at < $1)
            "#,
            before,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!("DELETE FROM refresh_tokens WHERE expires_at < $1", before)
            .execute(&mut *tx)
            .await
            .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok(sessions.rows_affected())
    }
}
