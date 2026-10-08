//! Construction of audit-log entries, shared by every bounded context.
//!
//! Administrative mutations hand the entry to their repository inside
//! [`crate::ports::WriteEffects`], so it is written in the same transaction as the change.

use chrono::{DateTime, Utc};
use dz_domain::authz::Actor;
use dz_domain::ids::AuditEntryId;

use crate::ports::{AuditActor, NewAuditEntry, RequestMeta};

/// The audited identity of an actor.
#[must_use]
pub fn actor(actor: &Actor) -> AuditActor {
    match actor {
        Actor::User { id, .. } => AuditActor::User(*id),
        Actor::Service { key_id, .. } => AuditActor::Service(*key_id),
        Actor::Anonymous => AuditActor::System,
    }
}

/// An audit entry for `action` (`<resource>.<verb>`) on one resource.
pub(crate) fn entry(
    actor: &Actor,
    meta: &RequestMeta,
    at: DateTime<Utc>,
    action: &'static str,
    resource_type: &'static str,
    resource_id: String,
    details: serde_json::Value,
) -> NewAuditEntry {
    NewAuditEntry {
        id: AuditEntryId::generate(),
        occurred_at: at,
        actor: self::actor(actor),
        action,
        resource_type,
        resource_id: Some(resource_id),
        details,
        ip: meta.ip,
        request_id: meta.request_id.clone(),
    }
}
