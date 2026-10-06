//! Resolves the caller once per request.
//!
//! * `Authorization: Bearer <access token>` → a user (signature, expiry and revocation checked).
//! * `Authorization: ApiKey <key>` or `X-Api-Key: <key>` → a service.
//! * No credentials → anonymous.
//!
//! Credentials that are present but invalid are rejected with 401; they never silently degrade
//! to anonymous (legacy defect L-11).

use axum::extract::{Request, State};
use axum::http::HeaderMap;
use axum::http::header::AUTHORIZATION;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use dz_app::AuthFailure;
use dz_app::auth::actor_from_claims;
use dz_app::ports::AccessClaims;
use dz_domain::authz::Actor;

use crate::error::{ApiError, ResolvedLang};
use crate::state::AppState;

/// The authenticated caller, available to every handler.
#[derive(Debug, Clone)]
pub struct AuthContext {
    pub actor: Actor,
    /// Present for users authenticated with an access token.
    pub claims: Option<AccessClaims>,
}

impl AuthContext {
    #[must_use]
    pub fn anonymous() -> Self {
        Self { actor: Actor::Anonymous, claims: None }
    }
}

enum Presented {
    None,
    Bearer(String),
    ApiKey(String),
    Unsupported,
}

fn presented(headers: &HeaderMap) -> Presented {
    if let Some(value) = headers.get(AUTHORIZATION) {
        let Ok(value) = value.to_str() else { return Presented::Unsupported };
        let (scheme, credential) = value.trim().split_once(' ').unwrap_or((value, ""));
        let credential = credential.trim();
        if credential.is_empty() {
            return Presented::Unsupported;
        }
        return if scheme.eq_ignore_ascii_case("bearer") {
            Presented::Bearer(credential.to_owned())
        } else if scheme.eq_ignore_ascii_case("apikey") {
            Presented::ApiKey(credential.to_owned())
        } else {
            Presented::Unsupported
        };
    }
    match headers.get("x-api-key").map(|v| v.to_str()) {
        Some(Ok(key)) if !key.trim().is_empty() => Presented::ApiKey(key.trim().to_owned()),
        Some(_) => Presented::Unsupported,
        None => Presented::None,
    }
}

pub async fn authenticate(State(state): State<AppState>, mut request: Request, next: Next) -> Response {
    let context = match presented(request.headers()) {
        Presented::None => AuthContext::anonymous(),
        Presented::Bearer(token) => match state.auth.authenticate(&token).await {
            Ok(claims) => AuthContext { actor: actor_from_claims(&claims), claims: Some(claims) },
            Err(error) => return ApiError::from(error).into_response(),
        },
        Presented::ApiKey(key) => match state.api_keys.authenticate(&key).await {
            Ok(actor) => AuthContext { actor, claims: None },
            Err(error) => return ApiError::from(error).into_response(),
        },
        Presented::Unsupported => {
            return ApiError::unauthenticated(AuthFailure::TokenInvalid).into_response();
        }
    };
    let lang = context.claims.as_ref().map(|c| c.lang);
    if let Some(claims) = &context.claims {
        tracing::Span::current().record("user_id", tracing::field::display(claims.sub));
    }
    request.extensions_mut().insert(context);
    let mut response = next.run(request).await;
    if let Some(lang) = lang {
        response.extensions_mut().insert(ResolvedLang(lang));
    }
    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    fn with(name: &'static str, value: &str) -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert(name, HeaderValue::from_str(value).unwrap());
        h
    }

    #[test]
    fn parses_supported_schemes() {
        assert!(matches!(presented(&HeaderMap::new()), Presented::None));
        assert!(matches!(presented(&with("authorization", "Bearer abc")), Presented::Bearer(t) if t == "abc"));
        assert!(matches!(presented(&with("authorization", "bearer  abc ")), Presented::Bearer(t) if t == "abc"));
        assert!(matches!(presented(&with("authorization", "ApiKey dzk_x")), Presented::ApiKey(_)));
        assert!(matches!(presented(&with("x-api-key", "dzk_x")), Presented::ApiKey(_)));
        assert!(matches!(presented(&with("authorization", "Basic dXNlcjpwYXNz")), Presented::Unsupported));
        assert!(matches!(presented(&with("authorization", "Bearer")), Presented::Unsupported));
    }
}
