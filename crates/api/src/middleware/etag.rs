//! Weak ETags for cacheable GET responses, with `If-None-Match` → `304 Not Modified`.
//!
//! The tag is derived from the response body, so it changes exactly when the representation
//! changes; clients save bandwidth on unchanged resources without any per-resource versioning.

use axum::body::{Body, HttpBody};
use axum::extract::Request;
use axum::http::header::{CACHE_CONTROL, ETAG, IF_NONE_MATCH};
use axum::http::{HeaderValue, Method, StatusCode};
use axum::middleware::Next;
use axum::response::Response;
use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use sha2::{Digest, Sha256};

/// Larger bodies are not buffered for tagging.
const MAX_TAGGED_BODY: u64 = 2 * 1024 * 1024;

fn matches(if_none_match: &str, etag: &str) -> bool {
    let strip = |t: &str| t.trim().trim_start_matches("W/").to_owned();
    let ours = strip(etag);
    if_none_match.split(',').any(|candidate| candidate.trim() == "*" || strip(candidate) == ours)
}

pub async fn etag(request: Request, next: Next) -> Response {
    if !matches!(*request.method(), Method::GET | Method::HEAD) {
        return next.run(request).await;
    }
    let if_none_match =
        request.headers().get(IF_NONE_MATCH).and_then(|v| v.to_str().ok()).map(str::to_owned);
    let response = next.run(request).await;
    if response.status() != StatusCode::OK || response.headers().contains_key(ETAG) {
        return response;
    }
    let fits = response.body().size_hint().exact().is_some_and(|n| n <= MAX_TAGGED_BODY);
    if !fits {
        return response;
    }
    let (mut parts, body) = response.into_parts();
    let Ok(bytes) = axum::body::to_bytes(body, usize::try_from(MAX_TAGGED_BODY).unwrap_or(usize::MAX)).await
    else {
        // Unreachable given the exact size hint; fail safe without a body.
        return Response::from_parts(parts, Body::empty());
    };
    let digest = Sha256::digest(&bytes);
    let tag = format!("W/\"{}\"", URL_SAFE_NO_PAD.encode(&digest[..16]));
    if let Ok(value) = HeaderValue::from_str(&tag) {
        parts.headers.insert(ETAG, value);
    }
    parts.headers.entry(CACHE_CONTROL).or_insert(HeaderValue::from_static("private, no-cache"));
    if if_none_match.as_deref().is_some_and(|inm| matches(inm, &tag)) {
        parts.status = StatusCode::NOT_MODIFIED;
        parts.headers.remove(axum::http::header::CONTENT_TYPE);
        parts.headers.remove(axum::http::header::CONTENT_LENGTH);
        return Response::from_parts(parts, Body::empty());
    }
    Response::from_parts(parts, Body::from(bytes))
}

#[cfg(test)]
mod tests {
    use super::matches;

    #[test]
    fn if_none_match_comparison_is_weak() {
        assert!(matches("W/\"abc\"", "W/\"abc\""));
        assert!(matches("\"abc\"", "W/\"abc\""));
        assert!(matches("\"x\", W/\"abc\"", "W/\"abc\""));
        assert!(matches("*", "W/\"abc\""));
        assert!(!matches("W/\"abd\"", "W/\"abc\""));
    }
}
