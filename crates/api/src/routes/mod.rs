//! Route table of API v1 (paths relative to `/api/v1`) and operational routes.

pub mod admin;
pub mod auth;
pub mod me;
pub mod network;
pub mod ops;
pub mod uploads;

use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use self::network::{lines, schedules, stops};

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
        .routes(routes!(me::set_avatar, me::delete_avatar))
        .routes(routes!(uploads::create_upload))
        .routes(routes!(uploads::get_upload))
        .routes(routes!(stops::list_stops, stops::create_stop))
        .routes(routes!(stops::nearby_stops))
        .routes(routes!(stops::get_stop, stops::update_stop, stops::delete_stop))
        .routes(routes!(stops::stop_lines))
        .routes(routes!(stops::set_stop_photo, stops::delete_stop_photo))
        .routes(routes!(lines::list_lines, lines::create_line))
        .routes(routes!(lines::get_line, lines::update_line, lines::delete_line))
        .routes(routes!(lines::line_stops, lines::replace_line_stops, lines::add_line_stop))
        .routes(routes!(lines::remove_line_stop))
        .routes(routes!(lines::get_line_route, lines::set_line_route, lines::delete_line_route))
        .routes(routes!(schedules::list_line_schedules, schedules::create_schedule))
        .routes(routes!(
            schedules::get_schedule,
            schedules::update_schedule,
            schedules::delete_schedule
        ))
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
