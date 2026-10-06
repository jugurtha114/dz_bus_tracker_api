//! HTTP edge of DZ Bus Tracker.
//!
//! [`router`] assembles the API with its middleware stack (outermost first):
//!
//! 1. sensitive-header redaction, request id, tracing span
//! 2. problem-document rendering (localized, with `instance` and `request_id`)
//! 3. panic catching, compression, CORS, security headers, request deadline
//! 4. client-IP resolution (trusted proxies), metrics, body-size limit
//! 5. on `/api/v1`: authentication → rate limiting → idempotency → ETag → handler

pub mod dto;
pub mod error;
pub mod extract;
pub mod i18n;
pub mod middleware;
pub mod openapi;
pub mod routes;
pub mod state;

use std::sync::Arc;
use std::time::Duration;

use axum::Router;
use axum::extract::{DefaultBodyLimit, MatchedPath, Request};
use axum::http::header::{
    ACCEPT_LANGUAGE, AUTHORIZATION, CACHE_CONTROL, CONTENT_LANGUAGE, CONTENT_SECURITY_POLICY,
    CONTENT_TYPE, COOKIE, ETAG, IF_NONE_MATCH, LOCATION, REFERRER_POLICY, RETRY_AFTER,
    SET_COOKIE, X_CONTENT_TYPE_OPTIONS, X_FRAME_OPTIONS,
};
use axum::http::{HeaderName, HeaderValue, Method};
use axum::middleware::{from_fn, from_fn_with_state};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use tower_http::catch_panic::CatchPanicLayer;
use tower_http::compression::CompressionLayer;
use tower_http::cors::{AllowOrigin, CorsLayer};
use tower_http::sensitive_headers::SetSensitiveHeadersLayer;
use tower_http::set_header::SetResponseHeaderLayer;
use tower_http::trace::TraceLayer;
use utoipa::OpenApi as _;
use utoipa::openapi::OpenApi;
use utoipa::openapi::server::Server;
use utoipa_axum::router::OpenApiRouter;

use crate::error::ApiError;
use crate::middleware::REQUEST_ID;
use crate::openapi::ApiDoc;
use crate::state::AppState;

/// The OpenAPI description of the whole API (also used by `dz-api openapi` for CI diffs).
#[must_use]
pub fn openapi() -> OpenApi {
    let (_, api) = OpenApiRouter::<AppState>::with_openapi(ApiDoc::openapi())
        .nest("/api/v1", routes::credentials().merge(routes::api()))
        .merge(routes::ops())
        .split_for_parts();
    api
}

fn cors(origins: &[String]) -> Option<CorsLayer> {
    let origins: Vec<HeaderValue> =
        origins.iter().filter_map(|o| HeaderValue::from_str(o).ok()).collect();
    if origins.is_empty() {
        return None;
    }
    Some(
        CorsLayer::new()
            .allow_origin(AllowOrigin::list(origins))
            .allow_methods([Method::GET, Method::POST, Method::PUT, Method::PATCH, Method::DELETE])
            .allow_headers([
                AUTHORIZATION,
                CONTENT_TYPE,
                ACCEPT_LANGUAGE,
                IF_NONE_MATCH,
                HeaderName::from_static("idempotency-key"),
                HeaderName::from_static(REQUEST_ID),
                HeaderName::from_static("x-api-key"),
            ])
            .expose_headers([
                ETAG,
                RETRY_AFTER,
                LOCATION,
                CONTENT_LANGUAGE,
                HeaderName::from_static(REQUEST_ID),
                HeaderName::from_static("ratelimit-limit"),
                HeaderName::from_static("ratelimit-remaining"),
                HeaderName::from_static("ratelimit-reset"),
                HeaderName::from_static("idempotent-replayed"),
            ])
            .max_age(Duration::from_secs(600)),
    )
}

fn panic_response(_: Box<dyn std::any::Any + Send + 'static>) -> Response {
    tracing::error!("handler panicked");
    ApiError::new(axum::http::StatusCode::INTERNAL_SERVER_ERROR, "internal_error").into_response()
}

/// Builds the complete HTTP application.
pub fn router(state: AppState) -> Router {
    let settings = Arc::clone(&state.settings);

    let credentials = routes::credentials().route_layer(from_fn_with_state(
        state.clone(),
        middleware::rate_limit::credentials_rate_limit,
    ));
    let v1 = credentials
        .merge(routes::api())
        .layer(from_fn(middleware::etag::etag))
        .layer(from_fn_with_state(state.clone(), middleware::idempotency::idempotency))
        .layer(from_fn_with_state(state.clone(), middleware::rate_limit::rate_limit))
        .layer(from_fn_with_state(state.clone(), middleware::auth::authenticate));

    let (api, mut spec) = OpenApiRouter::with_openapi(ApiDoc::openapi())
        .nest("/api/v1", v1)
        .merge(routes::ops())
        .split_for_parts();
    spec.servers = Some(vec![Server::new(settings.http.public_base_url.as_str())]);
    let spec_json: Arc<str> = Arc::from(spec.to_json().unwrap_or_else(|_| "{}".to_owned()));

    let mut app = api.route(
        "/api/openapi.json",
        get(move || {
            let spec_json = Arc::clone(&spec_json);
            async move {
                (
                    [(CONTENT_TYPE, "application/json"), (CACHE_CONTROL, "public, max-age=300")],
                    spec_json.to_string(),
                )
            }
        }),
    );
    if settings.http.docs_enabled {
        app = app.route("/api/docs", get(routes::ops::docs));
    }

    let trusted_proxies = Arc::new(settings.http.trusted_proxies.clone());
    let deadline = Duration::from_secs(settings.http.request_timeout_secs);
    let trace = TraceLayer::new_for_http().make_span_with(|request: &Request| {
        let route = request
            .extensions()
            .get::<MatchedPath>()
            .map_or("unmatched", MatchedPath::as_str)
            .to_owned();
        let request_id =
            request.headers().get(REQUEST_ID).and_then(|v| v.to_str().ok()).unwrap_or_default();
        tracing::info_span!(
            "http",
            method = %request.method(),
            route = %route,
            request_id = %request_id,
            user_id = tracing::field::Empty,
        )
    });

    app.fallback(|| async { ApiError::not_found() })
        .with_state(state)
        .layer(DefaultBodyLimit::max(settings.http.body_limit_bytes))
        .layer(from_fn(middleware::metrics::track))
        .layer(from_fn_with_state(trusted_proxies, middleware::client_ip::client_ip))
        .layer(from_fn_with_state(deadline, middleware::timeout::deadline))
        .layer(SetResponseHeaderLayer::if_not_present(
            X_CONTENT_TYPE_OPTIONS,
            HeaderValue::from_static("nosniff"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(X_FRAME_OPTIONS, HeaderValue::from_static("DENY")))
        .layer(SetResponseHeaderLayer::if_not_present(
            REFERRER_POLICY,
            HeaderValue::from_static("no-referrer"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            CONTENT_SECURITY_POLICY,
            HeaderValue::from_static("default-src 'none'; frame-ancestors 'none'"),
        ))
        .layer(SetResponseHeaderLayer::if_not_present(
            CACHE_CONTROL,
            HeaderValue::from_static("no-store"),
        ))
        .layer(tower::util::option_layer(cors(&settings.http.cors_allowed_origins)))
        .layer(CompressionLayer::new())
        .layer(CatchPanicLayer::custom(panic_response))
        .layer(from_fn(error::render_problems))
        .layer(trace)
        .layer(from_fn(middleware::request_id::request_id))
        .layer(SetSensitiveHeadersLayer::new([
            AUTHORIZATION,
            COOKIE,
            SET_COOKIE,
            HeaderName::from_static("x-api-key"),
        ]))
}
