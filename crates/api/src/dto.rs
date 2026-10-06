//! Request and response bodies of the public API (v1).
//!
//! Requests reject unknown fields (`deny_unknown_fields`), so a client cannot smuggle extra
//! attributes such as a role. Responses never expose secrets or internal columns.

use chrono::{DateTime, Utc};
use dz_app::admin::CreatedApiKey;
use dz_app::auth::{OwnSession, TokenPair};
use dz_app::pagination::Page;
use dz_app::ports::{ApiKeyRecord, AuditActor, AuditEntry};
use dz_domain::Lang;
use dz_domain::authz::Permission;
use dz_domain::user::{Profile, Role, User};
use serde::{Deserialize, Deserializer, Serialize};
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;
use validator::Validate;

/// Distinguishes an absent field (`None`) from an explicit `null` (`Some(None)`).
fn double_option<'de, D, T>(deserializer: D) -> Result<Option<Option<T>>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer).map(Some)
}

// --- Enums --------------------------------------------------------------------------------------------

/// Role of a user account.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum UserRole {
    Admin,
    Driver,
    Passenger,
}

impl From<Role> for UserRole {
    fn from(role: Role) -> Self {
        match role {
            Role::Admin => Self::Admin,
            Role::Driver => Self::Driver,
            // Users never carry the service role; map defensively to the least privileged.
            Role::Passenger | Role::Service => Self::Passenger,
        }
    }
}

impl UserRole {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Admin => "admin",
            Self::Driver => "driver",
            Self::Passenger => "passenger",
        }
    }
}

/// Preferred language for messages and notifications.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum Language {
    Fr,
    Ar,
    En,
}

impl From<Lang> for Language {
    fn from(lang: Lang) -> Self {
        match lang {
            Lang::Fr => Self::Fr,
            Lang::Ar => Self::Ar,
            Lang::En => Self::En,
        }
    }
}

impl From<Language> for Lang {
    fn from(lang: Language) -> Self {
        match lang {
            Language::Fr => Self::Fr,
            Language::Ar => Self::Ar,
            Language::En => Self::En,
        }
    }
}

// --- Users & profiles ---------------------------------------------------------------------------------

/// A user account.
#[derive(Debug, Serialize, ToSchema)]
pub struct UserDto {
    pub id: Uuid,
    pub email: String,
    pub role: UserRole,
    pub first_name: String,
    pub last_name: String,
    /// E.164 (`+2135XXXXXXXX`).
    pub phone_number: Option<String>,
    pub is_active: bool,
    pub email_verified: bool,
    pub last_login_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl From<User> for UserDto {
    fn from(u: User) -> Self {
        Self {
            id: u.id.as_uuid(),
            email: u.email.as_str().to_owned(),
            role: u.role.into(),
            first_name: u.first_name.as_str().to_owned(),
            last_name: u.last_name.as_str().to_owned(),
            phone_number: u.phone_number.map(|p| p.as_str().to_owned()),
            is_active: u.is_active,
            email_verified: u.email_verified_at.is_some(),
            last_login_at: u.last_login_at,
            created_at: u.created_at,
            updated_at: u.updated_at,
        }
    }
}

/// Personal preferences.
#[derive(Debug, Serialize, ToSchema)]
pub struct ProfileDto {
    pub language: Language,
    pub bio: String,
    pub push_notifications_enabled: bool,
    pub email_notifications_enabled: bool,
    pub sms_notifications_enabled: bool,
    pub updated_at: DateTime<Utc>,
}

impl From<Profile> for ProfileDto {
    fn from(p: Profile) -> Self {
        Self {
            language: p.language.into(),
            bio: p.bio.as_str().to_owned(),
            push_notifications_enabled: p.push_notifications_enabled,
            email_notifications_enabled: p.email_notifications_enabled,
            sms_notifications_enabled: p.sms_notifications_enabled,
            updated_at: p.updated_at,
        }
    }
}

/// The caller's account with its profile.
#[derive(Debug, Serialize, ToSchema)]
pub struct MeDto {
    #[serde(flatten)]
    pub user: UserDto,
    pub profile: ProfileDto,
}

/// Self-service account changes. Send `phone_number: null` to remove the number.
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateMeRequest {
    #[validate(length(max = 150))]
    pub first_name: Option<String>,
    #[validate(length(max = 150))]
    pub last_name: Option<String>,
    #[serde(default, deserialize_with = "double_option")]
    #[schema(value_type = Option<String>)]
    pub phone_number: Option<Option<String>>,
}

/// Profile changes.
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateProfileRequest {
    #[validate(length(max = 1000))]
    pub bio: Option<String>,
    pub language: Option<Language>,
    pub push_notifications_enabled: Option<bool>,
    pub email_notifications_enabled: Option<bool>,
    pub sms_notifications_enabled: Option<bool>,
}

// --- Authentication -------------------------------------------------------------------------------------

/// Creates a passenger account.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RegisterRequest {
    #[validate(length(min = 3, max = 254))]
    #[schema(example = "amina@example.dz")]
    pub email: String,
    /// At least 12 characters; common and personal passwords are refused.
    #[validate(length(min = 1, max = 256))]
    #[schema(format = Password)]
    pub password: String,
    #[validate(length(max = 150))]
    pub first_name: Option<String>,
    #[validate(length(max = 150))]
    pub last_name: Option<String>,
    /// Algerian mobile number (`05…`, `06…`, `07…`, `+213…`).
    #[validate(length(max = 20))]
    pub phone_number: Option<String>,
    pub language: Option<Language>,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LoginRequest {
    #[validate(length(min = 1, max = 254))]
    pub email: String,
    #[validate(length(min = 1, max = 256))]
    #[schema(format = Password)]
    pub password: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RefreshRequest {
    #[validate(length(min = 1, max = 200))]
    pub refresh_token: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ChangePasswordRequest {
    #[validate(length(min = 1, max = 256))]
    #[schema(format = Password)]
    pub current_password: String,
    #[validate(length(min = 1, max = 256))]
    #[schema(format = Password)]
    pub new_password: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PasswordResetRequest {
    #[validate(length(min = 3, max = 254))]
    pub email: String,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PasswordResetConfirmRequest {
    /// The token from the e-mailed link (URL fragment `#token=…`).
    #[validate(length(min = 1, max = 200))]
    pub token: String,
    #[validate(length(min = 1, max = 256))]
    #[schema(format = Password)]
    pub new_password: String,
}

/// Bearer token pair. Clients must serialise refresh calls: presenting a spent refresh token
/// revokes the whole session.
#[derive(Debug, Serialize, ToSchema)]
pub struct TokenPairDto {
    #[schema(example = "Bearer")]
    pub token_type: &'static str,
    pub access_token: String,
    /// Seconds until the access token expires.
    pub expires_in: i64,
    pub access_token_expires_at: DateTime<Utc>,
    pub refresh_token: String,
    pub refresh_token_expires_at: DateTime<Utc>,
    pub session_id: Uuid,
}

impl TokenPairDto {
    #[must_use]
    pub fn new(pair: TokenPair, now: DateTime<Utc>) -> Self {
        Self {
            token_type: "Bearer",
            expires_in: (pair.access_expires_at - now).num_seconds().max(0),
            access_token: pair.access_token,
            access_token_expires_at: pair.access_expires_at,
            refresh_token: pair.refresh_token,
            refresh_token_expires_at: pair.refresh_expires_at,
            session_id: pair.session_id.as_uuid(),
        }
    }
}

/// Result of registration or login.
#[derive(Debug, Serialize, ToSchema)]
pub struct AuthResponse {
    pub user: UserDto,
    pub tokens: TokenPairDto,
}

/// An active session of the caller.
#[derive(Debug, Serialize, ToSchema)]
pub struct SessionDto {
    pub id: Uuid,
    /// True for the session making this request.
    pub current: bool,
    pub created_at: DateTime<Utc>,
    pub last_used_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub user_agent: Option<String>,
    pub ip: Option<String>,
}

impl From<OwnSession> for SessionDto {
    fn from(s: OwnSession) -> Self {
        Self {
            id: s.info.id.as_uuid(),
            current: s.current,
            created_at: s.info.created_at,
            last_used_at: s.info.last_used_at,
            expires_at: s.info.expires_at,
            user_agent: s.info.user_agent,
            ip: s.info.ip.map(|ip| ip.to_string()),
        }
    }
}

// --- Pagination -------------------------------------------------------------------------------------------

/// A page of results. Pass `next_cursor` as `cursor` to fetch the next page.
#[derive(Debug, Serialize, ToSchema)]
pub struct Paginated<T: ToSchema> {
    pub items: Vec<T>,
    pub next_cursor: Option<String>,
}

impl<T: ToSchema> Paginated<T> {
    pub fn from_page<U>(page: Page<U>, map: impl FnMut(U) -> T) -> Self {
        Self {
            next_cursor: page.next_cursor.map(|c| c.encode()),
            items: page.items.into_iter().map(map).collect(),
        }
    }
}

/// Common pagination parameters.
#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct PageQuery {
    /// Opaque cursor from a previous page.
    pub cursor: Option<String>,
    /// Page size (1–100, default 20).
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}

// --- Admin ---------------------------------------------------------------------------------------------------

#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct UserListQuery {
    pub role: Option<UserRole>,
    pub is_active: Option<bool>,
    /// E-mail prefix (case-insensitive).
    #[validate(length(min = 1, max = 254))]
    pub email: Option<String>,
    pub cursor: Option<String>,
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}

/// Administrative account changes. Deactivation or a role change signs the user out.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AdminUpdateUserRequest {
    pub is_active: Option<bool>,
    pub role: Option<UserRole>,
}

#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateApiKeyRequest {
    #[validate(length(min = 1, max = 100))]
    pub name: String,
    /// Permission codes granted to the key (e.g. `tracking:read`, `notification:send`).
    #[validate(length(min = 1, max = 32))]
    pub scopes: Vec<String>,
    /// Optional expiry (at most two years ahead).
    pub expires_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ApiKeyDto {
    pub id: Uuid,
    pub name: String,
    /// Public identifier (first part of the key).
    pub prefix: String,
    pub scopes: Vec<String>,
    pub created_by: Option<Uuid>,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
    pub last_used_at: Option<DateTime<Utc>>,
    pub revoked_at: Option<DateTime<Utc>>,
}

impl From<ApiKeyRecord> for ApiKeyDto {
    fn from(k: ApiKeyRecord) -> Self {
        Self {
            id: k.id.as_uuid(),
            name: k.name,
            prefix: k.prefix,
            scopes: k.scopes.iter().map(Permission::code).map(str::to_owned).collect(),
            created_by: k.created_by.map(|u| u.as_uuid()),
            created_at: k.created_at,
            expires_at: k.expires_at,
            last_used_at: k.last_used_at,
            revoked_at: k.revoked_at,
        }
    }
}

/// A new key. `secret` is shown only in this response: store it securely.
#[derive(Debug, Serialize, ToSchema)]
pub struct CreatedApiKeyDto {
    pub api_key: ApiKeyDto,
    pub secret: String,
}

impl From<CreatedApiKey> for CreatedApiKeyDto {
    fn from(c: CreatedApiKey) -> Self {
        Self { api_key: c.record.into(), secret: c.secret }
    }
}

#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct AuditQuery {
    pub actor_id: Option<Uuid>,
    #[validate(length(min = 1, max = 100))]
    pub resource_type: Option<String>,
    #[validate(length(min = 1, max = 100))]
    pub resource_id: Option<String>,
    #[validate(length(min = 1, max = 100))]
    pub action: Option<String>,
    pub cursor: Option<String>,
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AuditEntryDto {
    pub id: Uuid,
    pub occurred_at: DateTime<Utc>,
    /// `user`, `service` or `system`.
    pub actor_type: &'static str,
    pub actor_id: Option<Uuid>,
    pub action: String,
    pub resource_type: String,
    pub resource_id: Option<String>,
    #[schema(value_type = Object)]
    pub details: serde_json::Value,
    pub ip: Option<String>,
    pub request_id: Option<String>,
}

impl From<AuditEntry> for AuditEntryDto {
    fn from(e: AuditEntry) -> Self {
        let (actor_type, actor_id) = match e.actor {
            AuditActor::User(id) => ("user", Some(id.as_uuid())),
            AuditActor::Service(id) => ("service", Some(id.as_uuid())),
            AuditActor::System => ("system", None),
        };
        Self {
            id: e.id.as_uuid(),
            occurred_at: e.occurred_at,
            actor_type,
            actor_id,
            action: e.action,
            resource_type: e.resource_type,
            resource_id: e.resource_id,
            details: e.details,
            ip: e.ip.map(|ip| ip.to_string()),
            request_id: e.request_id,
        }
    }
}

// --- Operations --------------------------------------------------------------------------------------------

#[derive(Debug, Serialize, ToSchema)]
pub struct ComponentHealthDto {
    pub name: &'static str,
    pub healthy: bool,
    pub latency_ms: u64,
    pub detail: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct HealthDto {
    /// `ok` or `unavailable`.
    pub status: &'static str,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub checks: Vec<ComponentHealthDto>,
}
