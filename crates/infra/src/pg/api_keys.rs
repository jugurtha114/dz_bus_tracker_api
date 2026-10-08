//! Machine-to-machine API keys.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::pagination::{Cursor, Page, PageRequest};
use dz_app::ports::{
    ApiKeyCredentials, ApiKeyRecord, ApiKeyRepository, NewApiKey, TokenHash, WriteEffects,
};
use dz_app::{AppError, AppResult};
use dz_domain::ConflictKind;
use dz_domain::authz::{Permission, PermissionSet};
use dz_domain::ids::{ApiKeyId, UserId};
use uuid::Uuid;

use super::{PgStore, db_error, effects, violated_constraint};

struct KeyRow {
    id: Uuid,
    name: String,
    prefix: String,
    secret_hash: Vec<u8>,
    scopes: Vec<String>,
    created_by: Option<Uuid>,
    created_at: DateTime<Utc>,
    expires_at: Option<DateTime<Utc>>,
    last_used_at: Option<DateTime<Utc>>,
    revoked_at: Option<DateTime<Utc>>,
}

impl KeyRow {
    fn into_credentials(self) -> AppResult<ApiKeyCredentials> {
        let hash: [u8; 32] = self
            .secret_hash
            .as_slice()
            .try_into()
            .map_err(|_| AppError::Internal(anyhow::anyhow!("invalid API key hash length")))?;
        let scopes = self
            .scopes
            .iter()
            .filter_map(|code| {
                let permission = Permission::from_code(code);
                if permission.is_none() {
                    tracing::warn!(scope = %code, "ignoring unknown API key scope");
                }
                permission
            })
            .collect::<PermissionSet>();
        Ok(ApiKeyCredentials {
            record: ApiKeyRecord {
                id: ApiKeyId::from_uuid(self.id),
                name: self.name,
                prefix: self.prefix,
                scopes,
                created_by: self.created_by.map(UserId::from_uuid),
                created_at: self.created_at,
                expires_at: self.expires_at,
                last_used_at: self.last_used_at,
                revoked_at: self.revoked_at,
            },
            secret_hash: TokenHash(hash),
        })
    }
}

#[async_trait]
impl ApiKeyRepository for PgStore {
    async fn insert(&self, key: NewApiKey, effects: WriteEffects) -> AppResult<ApiKeyRecord> {
        let scopes: Vec<String> = key.scopes.iter().map(|p| p.code().to_owned()).collect();
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            KeyRow,
            r#"
            INSERT INTO api_keys (id, name, prefix, secret_hash, scopes, created_by, created_at,
                                  expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, name, prefix, secret_hash, scopes, created_by, created_at, expires_at,
                      last_used_at, revoked_at
            "#,
            key.id.as_uuid(),
            key.name,
            key.prefix,
            &key.secret_hash.0[..],
            &scopes,
            key.created_by.as_uuid(),
            key.created_at,
            key.expires_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(|e| match violated_constraint(&e) {
            Some("api_keys_prefix_key") => AppError::Conflict(ConflictKind::AlreadyExists),
            _ => db_error(e),
        })?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(row.into_credentials()?.record)
    }

    async fn find_by_prefix(&self, prefix: &str) -> AppResult<Option<ApiKeyCredentials>> {
        sqlx::query_as!(
            KeyRow,
            r#"
            SELECT id, name, prefix, secret_hash, scopes, created_by, created_at, expires_at,
                   last_used_at, revoked_at
            FROM api_keys WHERE prefix = $1
            "#,
            prefix,
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(KeyRow::into_credentials)
        .transpose()
    }

    async fn touch(&self, id: ApiKeyId, at: DateTime<Utc>) -> AppResult<()> {
        // At most one write per key per minute, however busy the key is.
        sqlx::query!(
            r#"
            UPDATE api_keys SET last_used_at = $2
            WHERE id = $1
              AND (last_used_at IS NULL OR last_used_at < $2::timestamptz - interval '60 seconds')
            "#,
            id.as_uuid(),
            at,
        )
        .execute(self.pool())
        .await
        .map_err(db_error)?;
        Ok(())
    }

    async fn list(&self, page: PageRequest) -> AppResult<Page<ApiKeyRecord>> {
        let rows = sqlx::query_as!(
            KeyRow,
            r#"
            SELECT id, name, prefix, secret_hash, scopes, created_by, created_at, expires_at,
                   last_used_at, revoked_at
            FROM api_keys
            WHERE ($1::timestamptz IS NULL OR (created_at, id) < ($1, $2))
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            "#,
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let records = rows
            .into_iter()
            .map(|r| r.into_credentials().map(|c| c.record))
            .collect::<AppResult<Vec<_>>>()?;
        Ok(Page::from_rows(records, page, |k| Cursor {
            created_at: k.created_at,
            id: k.id.as_uuid(),
        }))
    }

    async fn revoke(
        &self,
        id: ApiKeyId,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Option<ApiKeyRecord>> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let Some(row) = sqlx::query_as!(
            KeyRow,
            r#"
            UPDATE api_keys SET revoked_at = COALESCE(revoked_at, $2)
            WHERE id = $1
            RETURNING id, name, prefix, secret_hash, scopes, created_by, created_at, expires_at,
                      last_used_at, revoked_at
            "#,
            id.as_uuid(),
            at,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        else {
            return Ok(None);
        };
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(Some(row.into_credentials()?.record))
    }
}
