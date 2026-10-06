//! Rate limiting (GCRA in Valkey, shared by all replicas).
//!
//! Every request is charged to its caller's tier: users per user id, API keys per key,
//! anonymous callers per client IP. Credential endpoints additionally use a stricter per-IP
//! tier. Responses carry `RateLimit-*` headers; rejections are `429` with `Retry-After`.

use axum::extract::{Request, State};
use axum::http::{HeaderMap, HeaderValue};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use dz_app::ports::{Quota, RateDecision};
use dz_domain::authz::Actor;

use super::auth::AuthContext;
use super::client_ip::ClientIp;
use crate::error::ApiError;
use crate::state::AppState;

fn identity(request: &Request) -> (String, Tier) {
    let actor = request.extensions().get::<AuthContext>().map(|c| &c.actor);
    match actor {
        Some(Actor::User { id, .. }) => (format!("user:{id}"), Tier::User),
        Some(Actor::Service { key_id, .. }) => (format!("key:{key_id}"), Tier::Service),
        _ => (format!("ip:{}", client_ip_label(request)), Tier::Anonymous),
    }
}

fn client_ip_label(request: &Request) -> String {
    request
        .extensions()
        .get::<ClientIp>()
        .map_or_else(|| "unknown".to_owned(), |ip| ip.0.to_string())
}

#[derive(Debug, Clone, Copy)]
enum Tier {
    Anonymous,
    User,
    Service,
    Credentials,
}

impl Tier {
    const fn label(self) -> &'static str {
        match self {
            Self::Anonymous => "anon",
            Self::User => "user",
            Self::Service => "service",
            Self::Credentials => "auth",
        }
    }

    fn quota(self, state: &AppState) -> Quota {
        let s = &state.settings.rate_limit;
        match self {
            Self::Anonymous => Quota::per_minute(s.anon_per_minute, s.anon_per_minute),
            Self::User => Quota::per_minute(s.user_per_minute, s.burst),
            Self::Service => {
                Quota::per_minute(s.service_per_minute, (s.service_per_minute / 4).max(1))
            }
            Self::Credentials => Quota::per_minute(s.auth_per_minute, (s.auth_per_minute / 2).max(1)),
        }
    }
}

fn set_headers(headers: &mut HeaderMap, decision: &RateDecision) {
    headers.insert("ratelimit-limit", HeaderValue::from(decision.limit));
    headers.insert("ratelimit-remaining", HeaderValue::from(decision.remaining));
    headers.insert("ratelimit-reset", HeaderValue::from(decision.reset_after.as_secs().max(1)));
}

async fn enforce(
    state: &AppState,
    tier: Tier,
    key: String,
    request: Request,
    next: Next,
) -> Response {
    if !state.settings.rate_limit.enabled {
        return next.run(request).await;
    }
    let quota = tier.quota(state);
    match state.limiter.check(&format!("{}:{key}", tier.label()), quota).await {
        Ok(decision) if decision.allowed => {
            let mut response = next.run(request).await;
            set_headers(response.headers_mut(), &decision);
            response
        }
        Ok(decision) => {
            metrics::counter!("dz_http_rate_limited_total", "tier" => tier.label()).increment(1);
            let mut response = ApiError::rate_limited(decision.retry_after.as_secs().max(1)).into_response();
            set_headers(response.headers_mut(), &decision);
            response
        }
        Err(_) if state.settings.rate_limit.fail_open => {
            metrics::counter!("dz_http_rate_limiter_errors_total").increment(1);
            next.run(request).await
        }
        Err(error) => ApiError::from(error).into_response(),
    }
}

/// General tier for every API request.
pub async fn rate_limit(State(state): State<AppState>, request: Request, next: Next) -> Response {
    let (key, tier) = identity(&request);
    enforce(&state, tier, key, request, next).await
}

/// Stricter per-IP tier for credential endpoints (login, register, refresh, password reset).
pub async fn credentials_rate_limit(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    let key = format!("ip:{}", client_ip_label(&request));
    enforce(&state, Tier::Credentials, key, request, next).await
}
