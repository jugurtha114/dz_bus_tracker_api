//! `/api/v1/stops`, `/api/v1/lines` and `/api/v1/schedules`: the network catalogue.
//!
//! Reads are public (`catalog:read`, held by anonymous callers too) and show active rows only;
//! stop, line and schedule administrators also see inactive rows. Writes need `stop:write`,
//! `line:write` or `schedule:write` (administrators, or API keys with those scopes) and are
//! audited.

pub mod lines;
pub mod schedules;
pub mod stops;

use axum::Json;
use axum::http::header::LOCATION;
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use serde::Serialize;

/// `201 Created` with `Location` and the created resource.
fn created(location: &str, body: impl Serialize) -> Response {
    let mut response = (StatusCode::CREATED, Json(body)).into_response();
    if let Ok(value) = HeaderValue::from_str(location) {
        response.headers_mut().insert(LOCATION, value);
    }
    response
}
