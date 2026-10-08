//! Administrative use-cases: user management, API keys, audit log. Every mutation is written to
//! the append-only audit log in the same transaction as the change.

use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use dz_domain::authz::{Action, Actor, Permission, PermissionSet, Policy};
use dz_domain::ids::{ApiKeyId, UserId};
use dz_domain::user::{Role, User};
use dz_domain::{Violation, Violations};
use serde_json::json;

use crate::audit;
use crate::auth::secrets;
use crate::error::{AppError, AppResult, AuthFailure};
use crate::pagination::{Page, PageRequest};
use crate::ports::{
    AdminUserPatch, ApiKeyRecord, ApiKeyRepository, AuditEntry, AuditFilter, AuditRepository,
    Clock, NewApiKey, RequestMeta, RevocationStore, UserFilter, UserRepository, WriteEffects,
};

/// Longest validity accepted for an API key.
const MAX_API_KEY_LIFETIME_DAYS: i64 = 2 * 365;

/// Raw filters of the admin user list.
#[derive(Debug, Clone, Default)]
pub struct UserListQuery {
    pub role: Option<String>,
    pub is_active: Option<bool>,
    pub email_prefix: Option<String>,
}

pub struct AdminUserService {
    users: Arc<dyn UserRepository>,
    revocations: Arc<dyn RevocationStore>,
    clock: Arc<dyn Clock>,
    /// How long revocation markers must live (access-token lifetime + margin).
    revocation_ttl: Duration,
}

impl AdminUserService {
    #[must_use]
    pub fn new(
        users: Arc<dyn UserRepository>,
        revocations: Arc<dyn RevocationStore>,
        clock: Arc<dyn Clock>,
        revocation_ttl: Duration,
    ) -> Self {
        Self { users, revocations, clock, revocation_ttl }
    }

    pub async fn list(
        &self,
        actor: &Actor,
        query: UserListQuery,
        page: PageRequest,
    ) -> AppResult<Page<User>> {
        actor.require(Permission::UserRead)?;
        let mut v = Violations::new();
        let role = query.role.as_deref().and_then(|r| v.check("role", Role::parse_user_role(r)));
        let email_prefix = query.email_prefix.map(|p| p.trim().to_lowercase());
        if email_prefix.as_ref().is_some_and(|p| p.len() > 254) {
            v.push("email_prefix", Violation::TooLong { max: 254 });
        }
        v.into_result()?;
        let filter = UserFilter { role, is_active: query.is_active, email_prefix };
        self.users.list(&filter, page).await
    }

    pub async fn get(&self, actor: &Actor, id: UserId) -> AppResult<User> {
        Policy::authorize(actor, &Action::ReadUser { target: id })?;
        self.users.find(id).await?.ok_or(AppError::NotFound("user"))
    }

    /// Activates/deactivates a user or changes their role. Deactivation and role changes sign
    /// the user out everywhere, because access tokens carry the role.
    pub async fn update(
        &self,
        actor: &Actor,
        id: UserId,
        is_active: Option<bool>,
        role: Option<&str>,
        meta: &RequestMeta,
    ) -> AppResult<User> {
        Policy::authorize(actor, &Action::ManageUser { target: id })?;
        let role = role
            .map(Role::parse_user_role)
            .transpose()
            .map_err(|v| AppError::invalid("role", v))?;
        let patch = AdminUserPatch { is_active, role };
        if patch == AdminUserPatch::default() {
            return self.users.find(id).await?.ok_or(AppError::NotFound("user"));
        }
        let now = self.clock.now();
        let details = json!({
            "is_active": is_active,
            "role": role.map(Role::as_str),
        });
        let audit = audit::entry(actor, meta, now, "user.update", "user", id.to_string(), details);
        let effects = WriteEffects::audited(audit);
        let outcome = self.users.admin_update(id, patch, now, effects).await?;
        if !outcome.revoked_sessions.is_empty() {
            self.revocations.revoke_sessions(&outcome.revoked_sessions, self.revocation_ttl).await?;
        }
        tracing::info!(target_user = %id, revoked = outcome.revoked_sessions.len(), "user updated by admin");
        Ok(outcome.user)
    }
}

/// Input of [`ApiKeyService::create`].
#[derive(Debug, Clone)]
pub struct CreateApiKeyInput {
    pub name: String,
    pub scopes: Vec<String>,
    pub expires_at: Option<DateTime<Utc>>,
}

/// A newly created key: the secret is shown once and never stored in clear.
#[derive(Debug, Clone)]
pub struct CreatedApiKey {
    pub record: ApiKeyRecord,
    pub secret: String,
}

pub struct ApiKeyService {
    keys: Arc<dyn ApiKeyRepository>,
    clock: Arc<dyn Clock>,
}

impl ApiKeyService {
    #[must_use]
    pub fn new(keys: Arc<dyn ApiKeyRepository>, clock: Arc<dyn Clock>) -> Self {
        Self { keys, clock }
    }

    pub async fn create(
        &self,
        actor: &Actor,
        input: CreateApiKeyInput,
        meta: &RequestMeta,
    ) -> AppResult<CreatedApiKey> {
        Policy::authorize(actor, &Action::ManageApiKeys)?;
        let created_by = actor.user_id().ok_or(AppError::Forbidden(dz_domain::DenyReason::MissingPermission))?;
        let now = self.clock.now();
        let mut v = Violations::new();
        let name = input.name.trim().to_owned();
        if name.is_empty() {
            v.push("name", Violation::Required);
        } else if name.chars().count() > 100 {
            v.push("name", Violation::TooLong { max: 100 });
        }
        let allowed: Vec<std::borrow::Cow<'static, str>> = Permission::ALL
            .iter()
            .filter(|p| p.grantable_to_service())
            .map(|p| p.code().into())
            .collect();
        let mut scopes = PermissionSet::EMPTY;
        if input.scopes.is_empty() {
            v.push("scopes", Violation::Required);
        }
        for (i, raw) in input.scopes.iter().enumerate() {
            match Permission::from_code(raw).filter(|p| p.grantable_to_service()) {
                Some(p) => scopes = scopes.union(PermissionSet::of(&[p])),
                None => v.push(
                    format!("scopes[{i}]"),
                    Violation::InvalidChoice { allowed: allowed.clone() },
                ),
            }
        }
        if let Some(expires_at) = input.expires_at {
            let max = now + chrono::Duration::days(MAX_API_KEY_LIFETIME_DAYS);
            if expires_at <= now || expires_at > max {
                v.push("expires_at", Violation::OutOfRange { min: 0, max: MAX_API_KEY_LIFETIME_DAYS });
            }
        }
        v.into_result()?;

        let id = ApiKeyId::generate();
        let prefix = format!("dzk_{}", hex_id());
        let secret = format!("{prefix}_{}", secrets::random_b64(32));
        let details = json!({
            "name": name,
            "scopes": scopes.iter().map(Permission::code).collect::<Vec<_>>(),
            "expires_at": input.expires_at,
        });
        let audit =
            audit::entry(actor, meta, now, "api_key.create", "api_key", id.to_string(), details);
        let record = self
            .keys
            .insert(
                NewApiKey {
                    id,
                    name,
                    prefix,
                    secret_hash: secrets::hash(&secret),
                    scopes,
                    created_by,
                    created_at: now,
                    expires_at: input.expires_at,
                },
                WriteEffects::audited(audit),
            )
            .await?;
        Ok(CreatedApiKey { record, secret })
    }

    pub async fn list(&self, actor: &Actor, page: PageRequest) -> AppResult<Page<ApiKeyRecord>> {
        Policy::authorize(actor, &Action::ManageApiKeys)?;
        self.keys.list(page).await
    }

    pub async fn revoke(
        &self,
        actor: &Actor,
        id: ApiKeyId,
        meta: &RequestMeta,
    ) -> AppResult<ApiKeyRecord> {
        Policy::authorize(actor, &Action::ManageApiKeys)?;
        let now = self.clock.now();
        let audit =
            audit::entry(actor, meta, now, "api_key.revoke", "api_key", id.to_string(), json!({}));
        let effects = WriteEffects::audited(audit);
        self.keys.revoke(id, now, effects).await?.ok_or(AppError::NotFound("api_key"))
    }

    /// Resolves a presented key (`dzk_<id>_<secret>`) to a service actor.
    pub async fn authenticate(&self, presented: &str) -> AppResult<Actor> {
        let invalid = || AppError::Unauthenticated(AuthFailure::ApiKeyInvalid);
        let mut parts = presented.trim().splitn(3, '_');
        let (Some("dzk"), Some(id_part), Some(secret_part)) = (parts.next(), parts.next(), parts.next())
        else {
            return Err(invalid());
        };
        if id_part.len() != 16 || secret_part.is_empty() || presented.len() > 128 {
            return Err(invalid());
        }
        let prefix = format!("dzk_{id_part}");
        let credentials = self.keys.find_by_prefix(&prefix).await?.ok_or_else(invalid)?;
        if !secrets::hashes_equal(&secrets::hash(presented.trim()), &credentials.secret_hash) {
            return Err(invalid());
        }
        let now = self.clock.now();
        let record = credentials.record;
        if record.revoked_at.is_some() || record.expires_at.is_some_and(|at| at <= now) {
            return Err(invalid());
        }
        self.keys.touch(record.id, now).await?;
        Ok(Actor::Service { key_id: record.id, scopes: record.scopes })
    }
}

/// 16 hex characters (64 random bits) identifying a key in logs and lookups.
fn hex_id() -> String {
    use rand::Rng;
    let mut bytes = [0u8; 8];
    rand::rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Raw filters of the audit log.
#[derive(Debug, Clone, Default)]
pub struct AuditQuery {
    pub actor_id: Option<uuid::Uuid>,
    pub resource_type: Option<String>,
    pub resource_id: Option<String>,
    pub action: Option<String>,
}

pub struct AuditService {
    audit: Arc<dyn AuditRepository>,
}

impl AuditService {
    #[must_use]
    pub fn new(audit: Arc<dyn AuditRepository>) -> Self {
        Self { audit }
    }

    pub async fn list(
        &self,
        actor: &Actor,
        query: AuditQuery,
        page: PageRequest,
    ) -> AppResult<Page<AuditEntry>> {
        Policy::authorize(actor, &Action::ReadAuditLog)?;
        let mut v = Violations::new();
        for (field, value) in [
            ("resource_type", &query.resource_type),
            ("resource_id", &query.resource_id),
            ("action", &query.action),
        ] {
            if value.as_ref().is_some_and(|s| s.len() > 100) {
                v.push(field, Violation::TooLong { max: 100 });
            }
        }
        v.into_result()?;
        let filter = AuditFilter {
            actor_id: query.actor_id,
            resource_type: query.resource_type,
            resource_id: query.resource_id,
            action: query.action,
        };
        self.audit.list(&filter, page).await
    }
}

/// Input of [`bootstrap_admin`].
#[derive(Debug)]
pub struct BootstrapAdminInput {
    pub email: String,
    pub password: secrecy::SecretString,
    pub first_name: String,
    pub last_name: String,
}

/// Creates an administrator account (operator CLI only; there is no HTTP path to this).
pub async fn bootstrap_admin(
    users: &dyn UserRepository,
    hasher: &dyn crate::ports::PasswordHasher,
    clock: &dyn Clock,
    policy: dz_domain::password::PasswordPolicy,
    input: BootstrapAdminInput,
) -> AppResult<User> {
    use dz_domain::password::PasswordContext;
    use dz_domain::user::{Email, PersonName};
    use secrecy::ExposeSecret;

    let mut v = Violations::new();
    let email = v.check("email", Email::parse(&input.email));
    let first_name = v.check("first_name", PersonName::parse(&input.first_name));
    let last_name = v.check("last_name", PersonName::parse(&input.last_name));
    if let (Some(email), Some(first), Some(last)) = (&email, &first_name, &last_name) {
        let ctx = PasswordContext {
            email_local_part: Some(email.local_part()),
            first_name: Some(first.as_str()),
            last_name: Some(last.as_str()),
        };
        v.check("password", policy.validate(input.password.expose_secret(), ctx));
    }
    let (Some(email), Some(first_name), Some(last_name)) = (email, first_name, last_name) else {
        return Err(v.into());
    };
    v.into_result()?;
    let password_hash = hasher.hash(&input.password).await?;
    let (user, _) = users
        .insert(crate::ports::NewUser {
            id: UserId::generate(),
            email,
            password_hash,
            role: Role::Admin,
            first_name,
            last_name,
            phone_number: None,
            language: dz_domain::Lang::default(),
            created_at: clock.now(),
        })
        .await?;
    Ok(user)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Fakes;
    use dz_domain::password::PasswordPolicy;

    #[tokio::test]
    async fn bootstraps_an_admin_with_a_strong_password() {
        let f = Fakes::default();
        let weak = BootstrapAdminInput {
            email: "root@example.dz".into(),
            password: secrecy::SecretString::from("password".to_owned()),
            first_name: "Root".into(),
            last_name: "Admin".into(),
        };
        let err = bootstrap_admin(&*f.store, &*f.hasher, &*f.clock, PasswordPolicy::default(), weak)
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::Validation(_)));
        let ok = BootstrapAdminInput {
            email: "Root@Example.dz".into(),
            password: secrecy::SecretString::from("long enough passphrase".to_owned()),
            first_name: "Root".into(),
            last_name: "Admin".into(),
        };
        let user = bootstrap_admin(&*f.store, &*f.hasher, &*f.clock, PasswordPolicy::default(), ok)
            .await
            .unwrap();
        assert_eq!(user.role, Role::Admin);
        assert_eq!(user.email.as_str(), "root@example.dz");
    }
}
