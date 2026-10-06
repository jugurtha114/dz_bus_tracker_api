//! Append-only audit log.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::pagination::{Cursor, Page, PageRequest};
use dz_app::ports::{AuditActor, AuditEntry, AuditFilter, AuditRepository, NewAuditEntry};
use dz_app::{AppError, AppResult};
use dz_domain::ids::{ApiKeyId, AuditEntryId, UserId};
use sqlx::types::ipnet::IpNet;
use sqlx::{Postgres, Transaction};
use uuid::Uuid;

use super::{PgStore, db_error};

fn actor_columns(actor: AuditActor) -> (&'static str, Option<Uuid>) {
    match actor {
        AuditActor::User(id) => ("user", Some(id.as_uuid())),
        AuditActor::Service(id) => ("service", Some(id.as_uuid())),
        AuditActor::System => ("system", None),
    }
}

/// Writes an entry inside the caller's transaction (atomic with the audited change).
pub(crate) async fn insert(
    tx: &mut Transaction<'_, Postgres>,
    entry: &NewAuditEntry,
) -> AppResult<()> {
    let (actor_type, actor_id) = actor_columns(entry.actor);
    sqlx::query!(
        r#"
        INSERT INTO audit_log (id, occurred_at, actor_type, actor_id, action, resource_type,
                               resource_id, details, ip, request_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        "#,
        entry.id.as_uuid(),
        entry.occurred_at,
        actor_type,
        actor_id,
        entry.action,
        entry.resource_type,
        entry.resource_id,
        entry.details,
        entry.ip.map(IpNet::from),
        entry.request_id.as_deref().map(|r| truncate(r, 100)),
    )
    .execute(&mut **tx)
    .await
    .map_err(db_error)?;
    Ok(())
}

fn truncate(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        Some((idx, _)) => &s[..idx],
        None => s,
    }
}

struct AuditRow {
    id: Uuid,
    occurred_at: DateTime<Utc>,
    actor_type: String,
    actor_id: Option<Uuid>,
    action: String,
    resource_type: String,
    resource_id: Option<String>,
    details: serde_json::Value,
    ip: Option<IpNet>,
    request_id: Option<String>,
}

impl AuditRow {
    fn into_entry(self) -> AppResult<AuditEntry> {
        let actor = match (self.actor_type.as_str(), self.actor_id) {
            ("user", Some(id)) => AuditActor::User(UserId::from_uuid(id)),
            ("service", Some(id)) => AuditActor::Service(ApiKeyId::from_uuid(id)),
            ("system", None) => AuditActor::System,
            _ => return Err(AppError::Internal(anyhow::anyhow!("invalid audit actor"))),
        };
        Ok(AuditEntry {
            id: AuditEntryId::from_uuid(self.id),
            occurred_at: self.occurred_at,
            actor,
            action: self.action,
            resource_type: self.resource_type,
            resource_id: self.resource_id,
            details: self.details,
            ip: self.ip.map(|net| net.addr()),
            request_id: self.request_id,
        })
    }
}

#[async_trait]
impl AuditRepository for PgStore {
    async fn list(&self, filter: &AuditFilter, page: PageRequest) -> AppResult<Page<AuditEntry>> {
        let rows = sqlx::query_as!(
            AuditRow,
            r#"
            SELECT id, occurred_at, actor_type, actor_id, action, resource_type, resource_id,
                   details, ip, request_id
            FROM audit_log
            WHERE ($1::uuid IS NULL OR actor_id = $1)
              AND ($2::text IS NULL OR resource_type = $2)
              AND ($3::text IS NULL OR resource_id = $3)
              AND ($4::text IS NULL OR action = $4)
              AND ($5::timestamptz IS NULL OR (occurred_at, id) < ($5, $6))
            ORDER BY occurred_at DESC, id DESC
            LIMIT $7
            "#,
            filter.actor_id,
            filter.resource_type,
            filter.resource_id,
            filter.action,
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let entries = rows.into_iter().map(AuditRow::into_entry).collect::<AppResult<Vec<_>>>()?;
        Ok(Page::from_rows(entries, page, |e| Cursor {
            created_at: e.occurred_at,
            id: e.id.as_uuid(),
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::truncate;

    #[test]
    fn truncates_on_char_boundaries() {
        assert_eq!(truncate("héllo", 2), "hé");
        assert_eq!(truncate("abc", 10), "abc");
    }
}
