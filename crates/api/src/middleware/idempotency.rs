//! `Idempotency-Key` support for POST requests that create resources
//! (draft-ietf-httpapi-idempotency-key-header).
//!
//! * First request with a key: processed; a 2xx response is stored for 24 hours.
//! * Retry with the same key and the same request: the stored response is replayed
//!   (`Idempotent-Replayed: true`) without executing the handler again.
//! * Same key while the first request is still running: `409`.
//! * Same key with a different method, path or body: `422`.
//!
//! Keys are scoped to the caller (user, API key or client IP), so they cannot collide across
//! users. Non-2xx responses are not stored, so a client can fix the request and retry.

use std::time::Duration;

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::header::CONTENT_TYPE;
use axum::http::{HeaderValue, Method, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use dz_app::ports::{IdempotencyBegin, StoredResponse};
use dz_domain::Violation;
use dz_domain::authz::Actor;
use sha2::{Digest, Sha256};

use super::auth::AuthContext;
use super::client_ip::ClientIp;
use crate::error::ApiError;
use crate::state::AppState;

pub const HEADER: &str = "idempotency-key";
const REPLAYED: &str = "idempotent-replayed";
/// How long a key stays reserved while its request is processed.
const LOCK_TTL: Duration = Duration::from_secs(60);
/// How long a completed response can be replayed.
const RESULT_TTL: Duration = Duration::from_secs(24 * 3600);
/// Largest response kept for replay.
const MAX_STORED_RESPONSE: usize = 1024 * 1024;

fn valid_key(key: &str) -> bool {
    (1..=255).contains(&key.len()) && key.bytes().all(|b| b.is_ascii_graphic())
}

fn caller(request: &Request) -> String {
    match request.extensions().get::<AuthContext>().map(|c| &c.actor) {
        Some(Actor::User { id, .. }) => format!("user:{id}"),
        Some(Actor::Service { key_id, .. }) => format!("key:{key_id}"),
        _ => format!(
            "ip:{}",
            request.extensions().get::<ClientIp>().map_or_else(|| "unknown".into(), |ip| ip.0.to_string())
        ),
    }
}

pub async fn idempotency(State(state): State<AppState>, request: Request, next: Next) -> Response {
    if request.method() != Method::POST {
        return next.run(request).await;
    }
    let Some(key) = request.headers().get(HEADER).map(|v| v.to_str().map(str::to_owned)) else {
        return next.run(request).await;
    };
    let Ok(key) = key.map_err(|_| ()).and_then(|k| if valid_key(&k) { Ok(k) } else { Err(()) }) else {
        return ApiError::field("Idempotency-Key", Violation::InvalidFormat).into_response();
    };
    let scope = format!("{}:{}:{key}", caller(&request), request.uri().path());
    let (parts, body) = request.into_parts();
    let limit = state.settings.http.body_limit_bytes;
    let Ok(bytes) = axum::body::to_bytes(body, limit).await else {
        return ApiError::new(StatusCode::PAYLOAD_TOO_LARGE, "payload_too_large").into_response();
    };
    let mut hasher = Sha256::new();
    hasher.update(parts.method.as_str().as_bytes());
    hasher.update([0]);
    hasher.update(parts.uri.path().as_bytes());
    hasher.update([0]);
    hasher.update(&bytes);
    let fingerprint: [u8; 32] = hasher.finalize().into();

    match state.idempotency.begin(&scope, fingerprint, LOCK_TTL).await {
        Err(error) => ApiError::from(error).into_response(),
        Ok(IdempotencyBegin::InProgress) => {
            ApiError::new(StatusCode::CONFLICT, "idempotency_in_progress").into_response()
        }
        Ok(IdempotencyBegin::Mismatch) => {
            ApiError::new(StatusCode::UNPROCESSABLE_ENTITY, "idempotency_key_reused").into_response()
        }
        Ok(IdempotencyBegin::Replay(stored)) => replay(stored),
        Ok(IdempotencyBegin::Proceed) => {
            let response = next.run(Request::from_parts(parts, Body::from(bytes))).await;
            if !response.status().is_success() {
                if let Err(error) = state.idempotency.release(&scope).await {
                    tracing::warn!(%error, "could not release idempotency key");
                }
                return response;
            }
            let (parts, body) = response.into_parts();
            let Ok(body) = axum::body::to_bytes(body, MAX_STORED_RESPONSE).await else {
                tracing::error!("response too large to store for idempotent replay");
                let _ = state.idempotency.release(&scope).await;
                return ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "internal_error").into_response();
            };
            let stored = StoredResponse {
                status: parts.status.as_u16(),
                content_type: parts
                    .headers
                    .get(CONTENT_TYPE)
                    .and_then(|v| v.to_str().ok())
                    .map(str::to_owned),
                body: body.to_vec(),
            };
            if let Err(error) = state.idempotency.complete(&scope, fingerprint, &stored, RESULT_TTL).await {
                tracing::warn!(%error, "could not store idempotent response");
            }
            Response::from_parts(parts, Body::from(body))
        }
    }
}

fn replay(stored: StoredResponse) -> Response {
    let status = StatusCode::from_u16(stored.status).unwrap_or(StatusCode::OK);
    let mut response = (status, stored.body).into_response();
    if let Some(value) = stored.content_type.and_then(|ct| HeaderValue::from_str(&ct).ok()) {
        response.headers_mut().insert(CONTENT_TYPE, value);
    }
    response.headers_mut().insert(REPLAYED, HeaderValue::from_static("true"));
    response
}

#[cfg(test)]
mod tests {
    use super::valid_key;

    #[test]
    fn key_format() {
        assert!(valid_key("8e03978e-40d5-43e8-bc93-6894a57f9324"));
        assert!(!valid_key(""));
        assert!(!valid_key("has space"));
        assert!(!valid_key(&"k".repeat(256)));
    }
}
