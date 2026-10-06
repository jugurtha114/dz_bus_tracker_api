//! A small in-process HTTP client over the router.

use axum::Router;
use axum::body::{Body, Bytes};
use axum::http::header::{ACCEPT_LANGUAGE, AUTHORIZATION, CONTENT_TYPE};
use axum::http::{HeaderMap, Method, Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

/// A request being built; [`TestRequest::send`] runs it through the full middleware stack.
#[must_use]
pub struct TestRequest {
    router: Router,
    builder: axum::http::request::Builder,
    body: Body,
}

impl TestRequest {
    pub(crate) fn new(router: Router, method: Method, uri: &str) -> Self {
        Self { router, builder: Request::builder().method(method).uri(uri), body: Body::empty() }
    }

    pub fn header(mut self, name: &str, value: &str) -> Self {
        self.builder = self.builder.header(name, value);
        self
    }

    pub fn bearer(self, token: &str) -> Self {
        let value = format!("Bearer {token}");
        self.header(AUTHORIZATION.as_str(), &value)
    }

    pub fn api_key(self, secret: &str) -> Self {
        self.header("x-api-key", secret)
    }

    pub fn lang(self, accept_language: &str) -> Self {
        self.header(ACCEPT_LANGUAGE.as_str(), accept_language)
    }

    pub fn json(mut self, value: &Value) -> Self {
        self.builder = self.builder.header(CONTENT_TYPE, "application/json");
        self.body = Body::from(serde_json::to_vec(value).unwrap());
        self
    }

    pub fn raw(mut self, content_type: &str, body: impl Into<Bytes>) -> Self {
        self.builder = self.builder.header(CONTENT_TYPE, content_type);
        self.body = Body::from(body.into());
        self
    }

    pub async fn send(self) -> TestResponse {
        let request = self.builder.body(self.body).expect("valid test request");
        let response = self.router.oneshot(request).await.expect("router is infallible");
        let (parts, body) = response.into_parts();
        let body = body.collect().await.expect("readable response body").to_bytes();
        TestResponse { status: parts.status, headers: parts.headers, body }
    }
}

/// A buffered response.
#[derive(Debug)]
pub struct TestResponse {
    pub status: StatusCode,
    pub headers: HeaderMap,
    pub body: Bytes,
}

impl TestResponse {
    /// Asserts the status, showing the body when it differs.
    #[track_caller]
    pub fn expect(self, status: StatusCode) -> Self {
        assert_eq!(
            self.status,
            status,
            "unexpected status; body: {}",
            String::from_utf8_lossy(&self.body)
        );
        self
    }

    /// The body as JSON.
    #[track_caller]
    pub fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap_or_else(|error| {
            panic!("body is not JSON ({error}): {}", String::from_utf8_lossy(&self.body))
        })
    }

    #[must_use]
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(name).and_then(|v| v.to_str().ok())
    }

    /// Asserts an RFC 9457 problem document with `status` and returns its `code`.
    #[track_caller]
    pub fn problem(&self, status: StatusCode) -> String {
        assert_eq!(
            self.status,
            status,
            "unexpected status; body: {}",
            String::from_utf8_lossy(&self.body)
        );
        assert_eq!(self.header("content-type"), Some("application/problem+json"));
        let doc = self.json();
        assert_eq!(doc["status"], status.as_u16());
        let code = doc["code"].as_str().expect("problem code").to_owned();
        assert_eq!(doc["type"], format!("urn:dzbus:problem:{}", code.replace('_', "-")));
        code
    }
}
