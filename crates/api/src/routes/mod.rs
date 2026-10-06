//! Route table of API v1 (paths relative to `/api/v1`) and operational routes.

pub mod admin;
pub mod auth;
pub mod me;
pub mod ops;

use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::state::AppState;

/// Credential endpoints; they get a stricter per-IP rate-limit tier.
pub fn credentials() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(auth::register))
        .routes(routes!(auth::login))
        .routes(routes!(auth::refresh))
        .routes(routes!(auth::request_password_reset))
        .routes(routes!(auth::confirm_password_reset))
}

/// Every other `/api/v1` route.
pub fn api() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(auth::logout))
        .routes(routes!(auth::logout_all))
        .routes(routes!(auth::change_password))
        .routes(routes!(auth::list_sessions))
        .routes(routes!(auth::revoke_session))
        .routes(routes!(me::get_me, me::update_me))
        .routes(routes!(me::get_profile, me::update_profile))
        .routes(routes!(admin::list_users))
        .routes(routes!(admin::get_user, admin::update_user))
        .routes(routes!(admin::list_api_keys, admin::create_api_key))
        .routes(routes!(admin::revoke_api_key))
        .routes(routes!(admin::list_audit_log))
}

/// Operational routes outside `/api/v1` (no authentication, no rate limit).
pub fn ops() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(ops::live))
        .routes(routes!(ops::ready))
        .routes(routes!(ops::jwks))
}
