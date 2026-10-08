//! Uploads to object storage, and the claim step shared by every "attach" write.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::ports::{ClaimedUpload, NewUpload, Upload, UploadRepository};
use dz_app::{AppError, AppResult};
use dz_domain::ConflictKind;
use dz_domain::ids::{UploadId, UserId};
use dz_domain::upload::{UploadPurpose, UploadStatus};
use sqlx::{Postgres, Transaction};
use uuid::Uuid;

use super::{PgStore, db_error, violated_constraint};

struct UploadRow {
    id: Uuid,
    owner_id: Uuid,
    purpose: String,
    object_key: String,
    content_type: String,
    size_bytes: i32,
    status: String,
    created_at: DateTime<Utc>,
    expires_at: DateTime<Utc>,
    attached_at: Option<DateTime<Utc>>,
}

impl UploadRow {
    fn into_upload(self) -> AppResult<Upload> {
        let invalid = |what: &str| AppError::Internal(anyhow::anyhow!("invalid upload {what}"));
        Ok(Upload {
            id: UploadId::from_uuid(self.id),
            owner_id: UserId::from_uuid(self.owner_id),
            purpose: UploadPurpose::parse(&self.purpose).map_err(|_| invalid("purpose"))?,
            object_key: self.object_key,
            content_type: self.content_type,
            size_bytes: u32::try_from(self.size_bytes).map_err(|_| invalid("size"))?,
            status: UploadStatus::parse(&self.status).ok_or_else(|| invalid("status"))?,
            created_at: self.created_at,
            expires_at: self.expires_at,
            attached_at: self.attached_at,
        })
    }
}

/// Marks a claimed upload attached inside the transaction that stores its key on a resource.
/// No pending row means a concurrent request attached it first: `Conflict(UploadAlreadyUsed)`,
/// and the caller's transaction is rolled back.
pub(crate) async fn mark_attached(
    tx: &mut Transaction<'_, Postgres>,
    claimed: &ClaimedUpload,
    at: DateTime<Utc>,
) -> AppResult<()> {
    let updated = sqlx::query!(
        r#"
        UPDATE uploads SET status = 'attached', attached_at = $2
        WHERE id = $1 AND status = 'pending'
        "#,
        claimed.id.as_uuid(),
        at,
    )
    .execute(&mut **tx)
    .await
    .map_err(db_error)?;
    if updated.rows_affected() == 0 {
        return Err(AppError::Conflict(ConflictKind::UploadAlreadyUsed));
    }
    Ok(())
}

#[async_trait]
impl UploadRepository for PgStore {
    async fn insert(&self, upload: NewUpload) -> AppResult<Upload> {
        sqlx::query_as!(
            UploadRow,
            r#"
            INSERT INTO uploads (id, owner_id, purpose, object_key, content_type, size_bytes,
                                 created_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, owner_id, purpose, object_key, content_type, size_bytes, status,
                      created_at, expires_at, attached_at
            "#,
            upload.id.as_uuid(),
            upload.owner_id.as_uuid(),
            upload.purpose.as_str(),
            upload.object_key,
            upload.content_type,
            i32::try_from(upload.size_bytes).map_err(AppError::internal)?,
            upload.created_at,
            upload.expires_at,
        )
        .fetch_one(self.pool())
        .await
        .map_err(|e| match violated_constraint(&e) {
            Some("uploads_object_key_key" | "uploads_pkey") => {
                AppError::Conflict(ConflictKind::AlreadyExists)
            }
            _ => db_error(e),
        })?
        .into_upload()
    }

    async fn find(&self, id: UploadId) -> AppResult<Option<Upload>> {
        sqlx::query_as!(
            UploadRow,
            r#"
            SELECT id, owner_id, purpose, object_key, content_type, size_bytes, status,
                   created_at, expires_at, attached_at
            FROM uploads WHERE id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(UploadRow::into_upload)
        .transpose()
    }

    async fn find_by_key(&self, object_key: &str) -> AppResult<Option<Upload>> {
        // Served by the unique index on `object_key`.
        sqlx::query_as!(
            UploadRow,
            r#"
            SELECT id, owner_id, purpose, object_key, content_type, size_bytes, status,
                   created_at, expires_at, attached_at
            FROM uploads WHERE object_key = $1
            "#,
            object_key,
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(UploadRow::into_upload)
        .transpose()
    }

    async fn list_expired(&self, before: DateTime<Utc>, limit: u32) -> AppResult<Vec<Upload>> {
        sqlx::query_as!(
            UploadRow,
            r#"
            SELECT id, owner_id, purpose, object_key, content_type, size_bytes, status,
                   created_at, expires_at, attached_at
            FROM uploads
            WHERE status = 'pending' AND expires_at < $1
            ORDER BY expires_at
            LIMIT $2
            "#,
            before,
            i64::from(limit),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?
        .into_iter()
        .map(UploadRow::into_upload)
        .collect()
    }

    async fn delete_pending(&self, ids: &[UploadId]) -> AppResult<u64> {
        if ids.is_empty() {
            return Ok(0);
        }
        let ids: Vec<Uuid> = ids.iter().map(UploadId::as_uuid).collect();
        // `status = 'pending'`: an upload attached since it was listed is never deleted.
        let deleted = sqlx::query!(
            "DELETE FROM uploads WHERE id = ANY($1) AND status = 'pending'",
            &ids,
        )
        .execute(self.pool())
        .await
        .map_err(db_error)?;
        Ok(deleted.rows_affected())
    }
}
