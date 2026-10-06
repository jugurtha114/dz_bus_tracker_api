//! Request ids: reuse a well-formed `X-Request-Id` from the proxy, otherwise generate a UUIDv7.
//! The id is echoed in the response and attached to the tracing span.

use axum::extract::Request;
use axum::http::HeaderValue;
use axum::middleware::Next;
use axum::response::Response;

use super::REQUEST_ID;

/// Request id of the current request (also available as a header).
#[derive(Debug, Clone)]
pub struct RequestId(pub String);

fn acceptable(id: &str) -> bool {
    (8..=64).contains(&id.len()) && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
}

pub async fn request_id(mut request: Request, next: Next) -> Response {
    let incoming = request.headers().get(REQUEST_ID).and_then(|v| v.to_str().ok());
    let id = match incoming {
        Some(id) if acceptable(id) => id.to_owned(),
        _ => uuid::Uuid::now_v7().to_string(),
    };
    if let Ok(value) = HeaderValue::from_str(&id) {
        request.headers_mut().insert(REQUEST_ID, value.clone());
        request.extensions_mut().insert(RequestId(id));
        let mut response = next.run(request).await;
        response.headers_mut().insert(REQUEST_ID, value);
        response
    } else {
        next.run(request).await
    }
}

#[cfg(test)]
mod tests {
    use super::acceptable;

    #[test]
    fn rejects_injection_attempts() {
        assert!(acceptable("0199a5b2-1c3d-7e4f-8a9b-0c1d2e3f4a5b"));
        assert!(acceptable("abcdef12"));
        assert!(!acceptable("short"));
        assert!(!acceptable("evil\nlog line"));
        assert!(!acceptable(&"a".repeat(65)));
    }
}
