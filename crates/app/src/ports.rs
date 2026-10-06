//! Ports: the traits the use-cases depend on. Adapters implementing them live in `dz-infra`;
//! in-memory versions for tests live in [`crate::testing`].
//!
//! Mutations that must be atomic with an audit record or a session revocation are single port
//! methods, so every adapter implements them in one database transaction.

use std::net::IpAddr;
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::Lang;
use dz_domain::authz::PermissionSet;
use dz_domain::ids::{ApiKeyId, AuditEntryId, SessionId, UserId};
use dz_domain::user::{Bio, Email, PersonName, PhoneNumber, Profile, Role, User};
use secrecy::SecretString;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::{AppResult, AuthFailure};
use crate::jobs::Job;
use crate::pagination::{Page, PageRequest};

// --- Time ---------------------------------------------------------------------------------------

/// Source of the current time (injectable for tests).
pub trait Clock: Send + Sync {
    fn now(&self) -> DateTime<Utc>;
}

/// The real clock.
#[derive(Debug, Clone, Copy, Default)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> DateTime<Utc> {
        Utc::now()
    }
}

// --- Request metadata -----------------------------------------------------------------------------

/// Facts about the HTTP request that use-cases record (sessions, audit log).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RequestMeta {
    pub ip: Option<IpAddr>,
    pub user_agent: Option<String>,
    pub request_id: Option<String>,
}

// --- Users ------------------------------------------------------------------------------------------

/// A user to insert together with its default profile.
#[derive(Debug, Clone)]
pub struct NewUser {
    pub id: UserId,
    pub email: Email,
    pub password_hash: String,
    pub role: Role,
    pub first_name: PersonName,
    pub last_name: PersonName,
    pub phone_number: Option<PhoneNumber>,
    pub language: Lang,
    pub created_at: DateTime<Utc>,
}

/// A user with the secrets needed to authenticate them.
#[derive(Debug, Clone)]
pub struct Credentials {
    pub user: User,
    /// `None` when the account has no usable password (e.g. imported unusable hash).
    pub password_hash: Option<String>,
    pub failed_login_attempts: u32,
    pub locked_until: Option<DateTime<Utc>>,
    pub language: Lang,
}

/// Self-service changes to the account. `Some(None)` clears an optional field.
#[derive(Debug, Clone, Default)]
pub struct UserPatch {
    pub first_name: Option<PersonName>,
    pub last_name: Option<PersonName>,
    pub phone_number: Option<Option<PhoneNumber>>,
}

impl UserPatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.first_name.is_none() && self.last_name.is_none() && self.phone_number.is_none()
    }
}

/// Self-service changes to the profile.
#[derive(Debug, Clone, Default)]
pub struct ProfilePatch {
    pub bio: Option<Bio>,
    pub language: Option<Lang>,
    pub push_notifications_enabled: Option<bool>,
    pub email_notifications_enabled: Option<bool>,
    pub sms_notifications_enabled: Option<bool>,
}

impl ProfilePatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.bio.is_none()
            && self.language.is_none()
            && self.push_notifications_enabled.is_none()
            && self.email_notifications_enabled.is_none()
            && self.sms_notifications_enabled.is_none()
    }
}

/// Administrative changes to an account.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct AdminUserPatch {
    pub is_active: Option<bool>,
    pub role: Option<Role>,
}

/// Filters for the admin user list.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct UserFilter {
    pub role: Option<Role>,
    pub is_active: Option<bool>,
    /// Lower-cased e-mail prefix.
    pub email_prefix: Option<String>,
}

/// Account lockout policy applied on failed logins.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LockoutPolicy {
    /// Failures before the first lock.
    pub threshold: u32,
    /// First lock duration; doubles for each further failure, capped at 32×.
    pub base: Duration,
}

impl LockoutPolicy {
    /// Lock duration after `failures` consecutive failures, if any.
    #[must_use]
    pub fn lock_for(&self, failures: u32) -> Option<Duration> {
        if failures < self.threshold {
            return None;
        }
        let exponent = (failures - self.threshold).min(5);
        Some(self.base.saturating_mul(1 << exponent))
    }
}

/// Outcome of an admin change: the user and the sessions that were revoked as a consequence.
#[derive(Debug, Clone)]
pub struct AdminUserUpdate {
    pub user: User,
    pub revoked_sessions: Vec<SessionId>,
}

#[async_trait]
pub trait UserRepository: Send + Sync {
    /// Inserts the user and its profile atomically. Fails with `Conflict(EmailTaken)`.
    async fn insert(&self, user: NewUser) -> AppResult<(User, Profile)>;
    async fn find(&self, id: UserId) -> AppResult<Option<User>>;
    async fn credentials_by_email(&self, email: &Email) -> AppResult<Option<Credentials>>;
    async fn credentials_by_id(&self, id: UserId) -> AppResult<Option<Credentials>>;
    /// Resets the failure counter and lock, stamps the login and optionally upgrades the hash.
    async fn record_login_success(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        upgraded_hash: Option<String>,
    ) -> AppResult<()>;
    /// Increments the failure counter and applies the lock atomically.
    async fn record_login_failure(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        policy: LockoutPolicy,
    ) -> AppResult<()>;
    /// Sets a new password and revokes every session except `keep`, in one transaction.
    async fn change_password(
        &self,
        id: UserId,
        password_hash: String,
        at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>>;
    async fn update(&self, id: UserId, patch: UserPatch, at: DateTime<Utc>) -> AppResult<User>;
    async fn profile(&self, id: UserId) -> AppResult<Option<Profile>>;
    async fn update_profile(
        &self,
        id: UserId,
        patch: ProfilePatch,
        at: DateTime<Utc>,
    ) -> AppResult<Profile>;
    async fn list(&self, filter: &UserFilter, page: PageRequest) -> AppResult<Page<User>>;
    /// Applies an admin change, revokes all sessions when the account is deactivated or its role
    /// changes, and writes the audit entry, in one transaction.
    async fn admin_update(
        &self,
        id: UserId,
        patch: AdminUserPatch,
        audit: NewAuditEntry,
    ) -> AppResult<AdminUserUpdate>;
}

// --- Sessions & refresh tokens -------------------------------------------------------------------

/// SHA-256 of an opaque secret (refresh token, reset token, API key secret).
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct TokenHash(pub [u8; 32]);

impl std::fmt::Debug for TokenHash {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("TokenHash(..)")
    }
}

/// A new session (refresh-token family).
#[derive(Debug, Clone)]
pub struct NewSession {
    pub id: SessionId,
    pub user_id: UserId,
    pub created_at: DateTime<Utc>,
    /// Absolute end of the session, whatever the activity.
    pub expires_at: DateTime<Utc>,
    pub user_agent: Option<String>,
    pub ip: Option<IpAddr>,
}

/// A refresh token belonging to a session.
#[derive(Debug, Clone)]
pub struct NewRefreshToken {
    pub hash: TokenHash,
    pub session_id: SessionId,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

/// Public view of an active session.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionInfo {
    pub id: SessionId,
    pub user_id: UserId,
    pub created_at: DateTime<Utc>,
    pub last_used_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub user_agent: Option<String>,
    pub ip: Option<IpAddr>,
}

/// Result of presenting a refresh token.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RotateOutcome {
    /// The token was valid; it is now spent and `next` is the new current token.
    Rotated { user_id: UserId, session_id: SessionId, refresh_expires_at: DateTime<Utc> },
    /// Unknown, expired, or belonging to a revoked/expired session.
    Invalid,
    /// The token had already been used: the session has been revoked (theft suspected).
    Reused { user_id: UserId, session_id: SessionId },
}

/// Why a session was revoked (stored for support and forensics).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RevocationReason {
    Logout,
    PasswordChanged,
    PasswordReset,
    RefreshTokenReuse,
    AdminAction,
    UserRequest,
}

impl RevocationReason {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Logout => "logout",
            Self::PasswordChanged => "password_changed",
            Self::PasswordReset => "password_reset",
            Self::RefreshTokenReuse => "refresh_token_reuse",
            Self::AdminAction => "admin_action",
            Self::UserRequest => "user_request",
        }
    }
}

#[async_trait]
pub trait SessionRepository: Send + Sync {
    async fn create(&self, session: NewSession, token: NewRefreshToken) -> AppResult<()>;
    /// Atomically spends `presented` and stores `next` in the same session. The new token
    /// expires at `min(now + refresh_ttl, session end)`.
    async fn rotate(
        &self,
        presented: TokenHash,
        next: TokenHash,
        now: DateTime<Utc>,
        refresh_ttl: Duration,
    ) -> AppResult<RotateOutcome>;
    /// Revokes one session of `user_id`. Returns `false` when it does not exist or is already
    /// revoked.
    async fn revoke(
        &self,
        user_id: UserId,
        session_id: SessionId,
        reason: RevocationReason,
        at: DateTime<Utc>,
    ) -> AppResult<bool>;
    /// Revokes every active session of `user_id` except `keep`; returns the revoked ids.
    async fn revoke_all(
        &self,
        user_id: UserId,
        reason: RevocationReason,
        at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>>;
    async fn list_active(&self, user_id: UserId, now: DateTime<Utc>)
    -> AppResult<Vec<SessionInfo>>;
    /// Deletes sessions and tokens that ended before `before`.
    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64>;
}

// --- Password reset -------------------------------------------------------------------------------

#[async_trait]
pub trait PasswordResetRepository: Send + Sync {
    /// Stores a reset token and invalidates the user's previous unused tokens.
    async fn issue(
        &self,
        user_id: UserId,
        hash: TokenHash,
        created_at: DateTime<Utc>,
        expires_at: DateTime<Utc>,
    ) -> AppResult<()>;
    /// The user owning a valid (unused, unexpired) token.
    async fn find_valid(&self, hash: TokenHash, now: DateTime<Utc>) -> AppResult<Option<UserId>>;
    /// Atomically marks the token used, sets the password and revokes every session.
    /// Returns `None` when the token is no longer valid.
    async fn consume(
        &self,
        hash: TokenHash,
        password_hash: String,
        now: DateTime<Utc>,
    ) -> AppResult<Option<(UserId, Vec<SessionId>)>>;
    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64>;
}

// --- API keys ---------------------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct NewApiKey {
    pub id: ApiKeyId,
    pub name: String,
    pub prefix: String,
    pub secret_hash: TokenHash,
    pub scopes: PermissionSet,
    pub created_by: UserId,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApiKeyRecord {
    pub id: ApiKeyId,
    pub name: String,
    pub prefix: String,
    pub scopes: PermissionSet,
    pub created_by: Option<UserId>,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
    pub last_used_at: Option<DateTime<Utc>>,
    pub revoked_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone)]
pub struct ApiKeyCredentials {
    pub record: ApiKeyRecord,
    pub secret_hash: TokenHash,
}

#[async_trait]
pub trait ApiKeyRepository: Send + Sync {
    async fn insert(&self, key: NewApiKey, audit: NewAuditEntry) -> AppResult<ApiKeyRecord>;
    async fn find_by_prefix(&self, prefix: &str) -> AppResult<Option<ApiKeyCredentials>>;
    /// Records usage, at most once per minute per key (cheap conditional update).
    async fn touch(&self, id: ApiKeyId, at: DateTime<Utc>) -> AppResult<()>;
    async fn list(&self, page: PageRequest) -> AppResult<Page<ApiKeyRecord>>;
    /// Revokes the key and writes the audit entry atomically; `None` if it does not exist.
    async fn revoke(
        &self,
        id: ApiKeyId,
        at: DateTime<Utc>,
        audit: NewAuditEntry,
    ) -> AppResult<Option<ApiKeyRecord>>;
}

// --- Audit log ----------------------------------------------------------------------------------------

/// Who performed an audited action.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", content = "id", rename_all = "snake_case")]
pub enum AuditActor {
    User(UserId),
    Service(ApiKeyId),
    System,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NewAuditEntry {
    pub id: AuditEntryId,
    pub occurred_at: DateTime<Utc>,
    pub actor: AuditActor,
    pub action: &'static str,
    pub resource_type: &'static str,
    pub resource_id: Option<String>,
    pub details: serde_json::Value,
    pub ip: Option<IpAddr>,
    pub request_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AuditEntry {
    pub id: AuditEntryId,
    pub occurred_at: DateTime<Utc>,
    pub actor: AuditActor,
    pub action: String,
    pub resource_type: String,
    pub resource_id: Option<String>,
    pub details: serde_json::Value,
    pub ip: Option<IpAddr>,
    pub request_id: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AuditFilter {
    pub actor_id: Option<Uuid>,
    pub resource_type: Option<String>,
    pub resource_id: Option<String>,
    pub action: Option<String>,
}

#[async_trait]
pub trait AuditRepository: Send + Sync {
    async fn list(&self, filter: &AuditFilter, page: PageRequest) -> AppResult<Page<AuditEntry>>;
}

// --- Security primitives ----------------------------------------------------------------------------

/// Result of checking a password against a stored hash.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PasswordCheck {
    Mismatch,
    /// `needs_rehash` is set for legacy (Django PBKDF2) or outdated Argon2 parameters.
    Match { needs_rehash: bool },
}

/// Password hashing (CPU heavy: implementations must not block the async runtime).
#[async_trait]
pub trait PasswordHasher: Send + Sync {
    async fn hash(&self, password: &SecretString) -> AppResult<String>;
    async fn verify(&self, password: &SecretString, stored_hash: &str) -> AppResult<PasswordCheck>;
    /// Performs a verification against a dummy hash so that unknown accounts take as long as
    /// known ones (no user enumeration through timing).
    async fn burn(&self, password: &SecretString);
}

/// Claims carried by an access token.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AccessClaims {
    pub sub: UserId,
    pub sid: SessionId,
    pub role: Role,
    pub lang: Lang,
    pub iat: i64,
    pub exp: i64,
    pub jti: Uuid,
}

/// Signs and verifies access tokens (issuer and audience are adapter configuration).
pub trait AccessTokenCodec: Send + Sync {
    fn issue(&self, claims: &AccessClaims) -> AppResult<String>;
    fn verify(&self, token: &str, now: DateTime<Utc>) -> Result<AccessClaims, AuthFailure>;
}

/// Immediate revocation of access tokens before they expire.
#[async_trait]
pub trait RevocationStore: Send + Sync {
    async fn revoke_sessions(&self, sessions: &[SessionId], ttl: Duration) -> AppResult<()>;
    async fn is_session_revoked(&self, session: SessionId) -> AppResult<bool>;
}

/// A rate-limit quota (GCRA): `limit` requests per `period` on average, with up to `burst`
/// requests allowed back-to-back.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Quota {
    pub limit: u32,
    pub period: Duration,
    pub burst: u32,
}

impl Quota {
    /// `per_minute` requests per minute with the given burst.
    #[must_use]
    pub const fn per_minute(per_minute: u32, burst: u32) -> Self {
        Self { limit: per_minute, period: Duration::from_secs(60), burst }
    }

    /// Time between two requests at the sustained rate (the GCRA emission interval).
    #[must_use]
    pub fn emission_interval(&self) -> Duration {
        self.period / self.limit.max(1)
    }
}

/// Decision for one request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RateDecision {
    pub allowed: bool,
    pub limit: u32,
    pub remaining: u32,
    /// Wait before retrying (zero when allowed).
    pub retry_after: Duration,
    /// Time until the bucket is full again.
    pub reset_after: Duration,
}

#[async_trait]
pub trait RateLimiter: Send + Sync {
    async fn check(&self, key: &str, quota: Quota) -> AppResult<RateDecision>;
}

// --- Jobs & mail ------------------------------------------------------------------------------------

/// Scheduling options for a job.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct JobOptions {
    /// Not before this instant (default: now).
    pub run_at: Option<DateTime<Utc>>,
    /// While a job with this key is queued or running, enqueueing another is a no-op.
    pub dedup_key: Option<String>,
    /// Default: 5.
    pub max_attempts: Option<u16>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EnqueueOutcome {
    Enqueued(Uuid),
    Duplicate,
}

#[async_trait]
pub trait JobQueue: Send + Sync {
    async fn enqueue(&self, job: &Job, options: JobOptions) -> AppResult<EnqueueOutcome>;
}

/// A rendered e-mail.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmailMessage {
    pub to: String,
    pub subject: String,
    pub text_body: String,
    pub html_body: String,
    pub lang: Lang,
}

#[async_trait]
pub trait Mailer: Send + Sync {
    async fn send(&self, message: &EmailMessage) -> AppResult<()>;
}

// --- Health ---------------------------------------------------------------------------------------------

/// Health of one dependency.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ComponentHealth {
    pub name: &'static str,
    pub healthy: bool,
    pub latency_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

#[async_trait]
pub trait ReadinessProbe: Send + Sync {
    async fn check(&self) -> Vec<ComponentHealth>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lockout_backs_off_exponentially_with_a_cap() {
        let policy = LockoutPolicy { threshold: 5, base: Duration::from_secs(60) };
        assert_eq!(policy.lock_for(4), None);
        assert_eq!(policy.lock_for(5), Some(Duration::from_secs(60)));
        assert_eq!(policy.lock_for(6), Some(Duration::from_secs(120)));
        assert_eq!(policy.lock_for(10), Some(Duration::from_secs(60 * 32)));
        assert_eq!(policy.lock_for(50), Some(Duration::from_secs(60 * 32)));
    }
}
