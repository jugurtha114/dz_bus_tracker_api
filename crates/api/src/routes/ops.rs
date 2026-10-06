//! Operational endpoints: health probes, signing keys, API description and docs.

use axum::Json;
use axum::extract::State;
use axum::http::header::{CACHE_CONTROL, CONTENT_SECURITY_POLICY, CONTENT_TYPE};
use axum::http::{HeaderValue, StatusCode};
use axum::response::{Html, IntoResponse, Response};

use crate::dto::{ComponentHealthDto, HealthDto};
use crate::state::AppState;

/// Liveness: the process is up. Never touches dependencies (a database outage must not get
/// healthy API containers restarted).
#[utoipa::path(
    get, path = "/health/live", tag = "ops",
    responses((status = 200, description = "Alive", body = HealthDto))
)]
pub async fn live() -> Json<HealthDto> {
    Json(HealthDto { status: "ok", checks: Vec::new() })
}

/// Readiness: database reachable, migrations applied, Valkey reachable.
#[utoipa::path(
    get, path = "/health/ready", tag = "ops",
    responses(
        (status = 200, description = "Ready to serve traffic", body = HealthDto),
        (status = 503, description = "A dependency is unavailable", body = HealthDto),
    )
)]
pub async fn ready(State(state): State<AppState>) -> Response {
    let checks = state.readiness.check().await;
    let healthy = checks.iter().all(|c| c.healthy);
    let body = HealthDto {
        status: if healthy { "ok" } else { "unavailable" },
        checks: checks
            .into_iter()
            .map(|c| ComponentHealthDto {
                name: c.name,
                healthy: c.healthy,
                latency_ms: c.latency_ms,
                detail: c.detail,
            })
            .collect(),
    };
    let status = if healthy { StatusCode::OK } else { StatusCode::SERVICE_UNAVAILABLE };
    let mut response = (status, Json(body)).into_response();
    response.headers_mut().insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// Public keys that verify access tokens (JSON Web Key Set, RFC 7517).
#[utoipa::path(
    get, path = "/.well-known/jwks.json", tag = "ops",
    responses((status = 200, description = "JWKS", content_type = "application/jwk-set+json"))
)]
pub async fn jwks(State(state): State<AppState>) -> Response {
    let mut response = Json(state.jwks.clone()).into_response();
    let headers = response.headers_mut();
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/jwk-set+json"));
    headers.insert(CACHE_CONTROL, HeaderValue::from_static("public, max-age=300"));
    response
}

/// Pinned API reference UI. The script version is fixed and verified with Subresource
/// Integrity; the page may only load that script and talk to this origin.
const SCALAR_VERSION: &str = "1.73.0";
const SCALAR_SRI: &str = "sha384-OKyMdsDX84ypSZEhVun8YElXk5c2GQaH3EXPOc6ItmVcLDUAvKHYwvDLvAgsqVtB";

pub async fn docs() -> Response {
    let html = format!(
        r#"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DZ Bus Tracker API</title>
</head>
<body>
<script id="api-reference" data-url="/api/openapi.json"></script>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@{SCALAR_VERSION}/dist/browser/standalone.js" integrity="{SCALAR_SRI}" crossorigin="anonymous"></script>
</body>
</html>"#
    );
    let mut response = Html(html).into_response();
    response.headers_mut().insert(
        CONTENT_SECURITY_POLICY,
        HeaderValue::from_static(
            "default-src 'none'; script-src https://cdn.jsdelivr.net; \
             style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.scalar.com; \
             font-src 'self' data: https://cdn.jsdelivr.net https://fonts.scalar.com; \
             img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; \
             base-uri 'none'; form-action 'none'",
        ),
    );
    response
}
