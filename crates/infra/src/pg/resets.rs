//! Password-reset tokens.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::AppResult;
use dz_app::ports::{PasswordResetRepository, TokenHash};
use dz_domain::ids::{SessionId, UserId};

use super::{PgStore, db_error};

#[async_trait]
impl PasswordResetRepository for PgStore {
    async fn issue(
        &self,
        user_id: UserId,
        hash: TokenHash,
        created_at: DateTime<Utc>,
        expires_at: DateTime<Utc>,
    ) -> AppResult<()> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Only the most recent link works.
        sqlx::query!(
            r#"
            UPDATE password_reset_tokens SET used_at = $2
            WHERE user_id = $1 AND used_at IS NULL
            "#,
            user_id.as_uuid(),
            created_at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO password_reset_tokens (token_hash, user_id, created_at, expires_at)
            VALUES ($1, $2, $3, $4)
            "#,
            &hash.0[..],
            user_id.as_uuid(),
            created_at,
            expires_at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok(())
    }

    async fn find_valid(&self, hash: TokenHash, now: DateTime<Utc>) -> AppResult<Option<UserId>> {
        let user_id = sqlx::query_scalar!(
            r#"
            SELECT user_id FROM password_reset_tokens
            WHERE token_hash = $1 AND used_at IS NULL AND expires_at > $2
            "#,
            &hash.0[..],
            now,
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?;
        Ok(user_id.map(UserId::from_uuid))
    }

    async fn consume(
        &self,
        hash: TokenHash,
        password_hash: String,
        now: DateTime<Utc>,
    ) -> AppResult<Option<(UserId, Vec<SessionId>)>> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // The conditional UPDATE is the guard: a token can be consumed exactly once even under
        // concurrent requests.
        let Some(user_id) = sqlx::query_scalar!(
            r#"
            UPDATE password_reset_tokens SET used_at = $2
            WHERE token_hash = $1 AND used_at IS NULL AND expires_at > $2
            RETURNING user_id
            "#,
            &hash.0[..],
            now,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        else {
            return Ok(None);
        };
        let user_id = UserId::from_uuid(user_id);
        sqlx::query!(
            r#"
            UPDATE users
            SET password_hash = $2, password_changed_at = $3, updated_at = $3,
                failed_login_attempts = 0, locked_until = NULL
            WHERE id = $1
            "#,
            user_id.as_uuid(),
            password_hash,
            now,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        let revoked =
            super::sessions::revoke_all_in(&mut tx, user_id, "password_reset", now, None).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(Some((user_id, revoked)))
    }

    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64> {
        let result = sqlx::query!("DELETE FROM password_reset_tokens WHERE expires_at < $1", before)
            .execute(self.pool())
            .await
            .map_err(db_error)?;
        Ok(result.rows_affected())
    }
}
