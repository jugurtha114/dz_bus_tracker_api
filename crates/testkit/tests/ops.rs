//! Operational endpoints and the cross-cutting HTTP contract (problem documents, headers,
//! CORS, limits, rate limiting, client-IP resolution).

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::net::SocketAddr;

use axum::http::{Method, StatusCode};
use dz_testkit::TestApp;
use serde_json::json;

#[tokio::test]
async fn liveness_and_readiness() {
    let app = TestApp::spawn().await;

    let live = app.get("/health/live").send().await.expect(StatusCode::OK);
    assert_eq!(live.json(), json!({ "status": "ok" }));

    let ready = app.get("/health/ready").send().await.expect(StatusCode::OK);
    let body = ready.json();
    assert_eq!(body["status"], "ok");
    let names: Vec<&str> =
        body["checks"].as_array().unwrap().iter().map(|c| c["name"].as_str().unwrap()).collect();
    for expected in ["database", "migrations", "valkey"] {
        assert!(names.contains(&expected), "missing {expected} in {names:?}");
    }
    assert_eq!(ready.header("cache-control"), Some("no-store"));
}

#[tokio::test]
async fn jwks_publishes_the_signing_key() {
    let app = TestApp::spawn().await;
    let response = app.get("/.well-known/jwks.json").send().await.expect(StatusCode::OK);
    assert_eq!(response.header("content-type"), Some("application/jwk-set+json"));
    let keys = response.json()["keys"].as_array().unwrap().clone();
    assert_eq!(keys.len(), 1);
    assert_eq!(keys[0]["kty"], "OKP");
    assert_eq!(keys[0]["crv"], "Ed25519");
    assert_eq!(keys[0]["alg"], "EdDSA");
    assert!(keys[0].get("d").is_none(), "private key material must never be published");
}

#[tokio::test]
async fn openapi_document_and_docs_page() {
    let app = TestApp::spawn().await;
    let spec = app.get("/api/openapi.json").send().await.expect(StatusCode::OK).json();
    assert!(spec["openapi"].as_str().unwrap().starts_with("3.1"));
    assert_eq!(spec["servers"][0]["url"], "http://api.test");
    assert!(spec["paths"]["/api/v1/auth/login"]["post"].is_object());
    assert!(spec["components"]["securitySchemes"]["bearer"].is_object());

    let docs = app.get("/api/docs").send().await.expect(StatusCode::OK);
    let csp = docs.header("content-security-policy").unwrap();
    assert!(csp.contains("script-src"), "{csp}");
    let html = String::from_utf8_lossy(&docs.body);
    assert!(html.contains("integrity=\"sha384-"), "the docs script must be pinned with SRI");

    let disabled = TestApp::builder().configure(|s| s.http.docs_enabled = false).build().await;
    disabled.get("/api/docs").send().await.problem(StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn errors_are_problem_documents() {
    let app = TestApp::spawn().await;

    let missing = app.get("/api/v1/nope").send().await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    let doc = missing.json();
    assert_eq!(doc["instance"], "/api/v1/nope");
    assert_eq!(doc["request_id"].as_str(), missing.header("x-request-id"));

    let wrong_method = app.request(Method::PUT, "/api/v1/auth/login").send().await;
    assert_eq!(wrong_method.problem(StatusCode::METHOD_NOT_ALLOWED), "method_not_allowed");

    let not_json = app.post("/api/v1/auth/login").raw("text/plain", "hello").send().await;
    assert_eq!(not_json.problem(StatusCode::UNSUPPORTED_MEDIA_TYPE), "unsupported_media_type");

    let malformed = app.post("/api/v1/auth/login").raw("application/json", "{\"email\":").send().await;
    assert_eq!(malformed.problem(StatusCode::BAD_REQUEST), "malformed_request");
}

#[tokio::test]
async fn problems_are_localized() {
    let app = TestApp::spawn().await;
    let mut titles = Vec::new();
    for (accept, lang) in [("ar", "ar"), ("en-GB,en;q=0.9", "en"), ("de", "fr"), ("", "fr")] {
        let mut request = app.get("/api/v1/me");
        if !accept.is_empty() {
            request = request.lang(accept);
        }
        let response = request.send().await;
        assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "authentication_required");
        assert_eq!(response.header("content-language"), Some(lang), "Accept-Language {accept:?}");
        titles.push(response.json()["title"].as_str().unwrap().to_owned());
    }
    assert_ne!(titles[0], titles[1]);
    assert_ne!(titles[1], titles[2]);
    assert_eq!(titles[2], titles[3], "French is the default");
}

#[tokio::test]
async fn security_headers_and_request_ids() {
    let app = TestApp::spawn().await;
    let response = app.get("/health/live").send().await;
    assert_eq!(response.header("x-content-type-options"), Some("nosniff"));
    assert_eq!(response.header("x-frame-options"), Some("DENY"));
    assert_eq!(response.header("referrer-policy"), Some("no-referrer"));
    assert_eq!(response.header("cache-control"), Some("no-store"));
    let generated = response.header("x-request-id").unwrap();
    assert_eq!(generated.len(), 36, "a UUID is generated when the client sends none");

    let echoed = app.get("/health/live").header("x-request-id", "trace-abc-123").send().await;
    assert_eq!(echoed.header("x-request-id"), Some("trace-abc-123"));

    let hostile = app.get("/health/live").header("x-request-id", "a\"b<script>").send().await;
    assert_ne!(hostile.header("x-request-id"), Some("a\"b<script>"));
}

#[tokio::test]
async fn cors_allows_only_configured_origins() {
    let app = TestApp::builder()
        .configure(|s| s.http.cors_allowed_origins = vec!["https://app.example.test".to_owned()])
        .build()
        .await;

    let preflight = app
        .request(Method::OPTIONS, "/api/v1/auth/login")
        .header("origin", "https://app.example.test")
        .header("access-control-request-method", "POST")
        .header("access-control-request-headers", "content-type,idempotency-key")
        .send()
        .await;
    assert!(preflight.status.is_success());
    assert_eq!(
        preflight.header("access-control-allow-origin"),
        Some("https://app.example.test")
    );

    let foreign = app.get("/health/live").header("origin", "https://evil.example").send().await;
    assert_eq!(foreign.header("access-control-allow-origin"), None);
}

#[tokio::test]
async fn request_bodies_are_limited() {
    let app = TestApp::builder().configure(|s| s.http.body_limit_bytes = 4096).build().await;
    let big = format!("{{\"email\":\"{}@example.test\",\"password\":\"x\"}}", "a".repeat(8192));
    let response = app.post("/api/v1/auth/login").raw("application/json", big).send().await;
    assert_eq!(response.problem(StatusCode::PAYLOAD_TOO_LARGE), "payload_too_large");
}

#[tokio::test]
async fn credential_endpoints_are_rate_limited_per_client_ip() {
    let app = TestApp::builder().configure(|s| s.rate_limit.auth_per_minute = 4).build().await;
    let login = json!({ "email": "nobody@example.test", "password": "wrong password!" });

    // Burst of 2 (half the per-minute rate), then rejected.
    for _ in 0..2 {
        let response = app.post("/api/v1/auth/login").json(&login).send().await;
        assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "invalid_credentials");
        assert!(response.header("ratelimit-remaining").is_some());
    }
    let limited = app.post("/api/v1/auth/login").json(&login).send().await;
    assert_eq!(limited.problem(StatusCode::TOO_MANY_REQUESTS), "rate_limited");
    let retry_after: u64 = limited.header("retry-after").unwrap().parse().unwrap();
    assert!((1..=60).contains(&retry_after));
    assert_eq!(limited.header("ratelimit-remaining"), Some("0"));

    // Other endpoints use the general tier and are unaffected.
    app.get("/api/v1/me").send().await.problem(StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn forwarded_addresses_are_trusted_only_from_proxies() {
    let proxy: SocketAddr = "10.0.0.2:40000".parse().unwrap();
    let app = TestApp::builder()
        .peer(proxy)
        .configure(|s| {
            s.http.trusted_proxies = vec!["10.0.0.0/8".parse().unwrap()];
            s.rate_limit.auth_per_minute = 2;
        })
        .build()
        .await;
    let login = json!({ "email": "nobody@example.test", "password": "wrong password!" });
    let attempt = |client: &'static str| {
        app.post("/api/v1/auth/login").header("x-forwarded-for", client).json(&login).send()
    };

    // Each client behind the proxy has its own bucket (burst 1).
    assert_eq!(attempt("203.0.113.1").await.status, StatusCode::UNAUTHORIZED);
    assert_eq!(attempt("203.0.113.1").await.status, StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(attempt("203.0.113.2").await.status, StatusCode::UNAUTHORIZED);

    // A direct (untrusted) client cannot pick a fresh bucket with a forged header.
    let direct = TestApp::builder().configure(|s| s.rate_limit.auth_per_minute = 2).build().await;
    let forged = |client: &'static str| {
        direct.post("/api/v1/auth/login").header("x-forwarded-for", client).json(&login).send()
    };
    assert_eq!(forged("203.0.113.1").await.status, StatusCode::UNAUTHORIZED);
    assert_eq!(forged("203.0.113.2").await.status, StatusCode::TOO_MANY_REQUESTS);
}
