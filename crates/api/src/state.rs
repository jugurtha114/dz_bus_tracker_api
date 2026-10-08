//! Shared, immutable application state handed to every handler.

use std::sync::Arc;

use dz_app::account::AccountService;
use dz_app::admin::{AdminUserService, ApiKeyService, AuditService};
use dz_app::auth::AuthService;
use dz_app::ports::{IdempotencyStore, RateLimiter, ReadinessProbe};
use dz_app::uploads::UploadService;
use dz_config::Settings;

/// Everything the HTTP layer needs. Cloning is cheap (one `Arc`).
#[derive(Clone)]
pub struct AppState(pub Arc<AppServices>);

/// The services behind [`AppState`]; built by the composition root (`dz-api` binary, tests).
pub struct AppServices {
    pub settings: Arc<Settings>,
    pub auth: AuthService,
    pub accounts: AccountService,
    pub uploads: Arc<UploadService>,
    pub admin_users: AdminUserService,
    pub api_keys: ApiKeyService,
    pub audit: AuditService,
    pub limiter: Arc<dyn RateLimiter>,
    pub idempotency: Arc<dyn IdempotencyStore>,
    pub readiness: Arc<dyn ReadinessProbe>,
    /// Public signing keys (JWKS document).
    pub jwks: serde_json::Value,
}

impl AppState {
    #[must_use]
    pub fn new(services: AppServices) -> Self {
        Self(Arc::new(services))
    }
}

impl std::ops::Deref for AppState {
    type Target = AppServices;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
