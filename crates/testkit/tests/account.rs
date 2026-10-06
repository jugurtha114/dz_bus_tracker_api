//! The caller's own account and profile, conditional requests and idempotent POSTs.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use axum::http::StatusCode;
use dz_testkit::TestApp;
use serde_json::json;

#[tokio::test]
async fn me_supports_conditional_requests() {
    let app = TestApp::spawn().await;
    let account = app.register("etag@example.test").await;

    let first = app.get("/api/v1/me").bearer(&account.access_token).send().await.expect(StatusCode::OK);
    let etag = first.header("etag").unwrap().to_owned();
    assert!(etag.starts_with("W/\""), "{etag}");
    assert_eq!(first.header("cache-control"), Some("private, no-cache"));

    let cached = app
        .get("/api/v1/me")
        .bearer(&account.access_token)
        .header("if-none-match", &etag)
        .send()
        .await
        .expect(StatusCode::NOT_MODIFIED);
    assert!(cached.body.is_empty());
    assert_eq!(cached.header("etag"), Some(etag.as_str()));

    app.patch("/api/v1/me")
        .bearer(&account.access_token)
        .json(&json!({ "first_name": "Changed" }))
        .send()
        .await
        .expect(StatusCode::OK);
    let changed = app
        .get("/api/v1/me")
        .bearer(&account.access_token)
        .header("if-none-match", &etag)
        .send()
        .await
        .expect(StatusCode::OK);
    assert_ne!(changed.header("etag"), Some(etag.as_str()));
}

#[tokio::test]
async fn updating_the_account() {
    let app = TestApp::spawn().await;
    let account = app.register("me@example.test").await;

    let updated = app
        .patch("/api/v1/me")
        .bearer(&account.access_token)
        .json(&json!({ "first_name": "  Yacine ", "last_name": "Saidi", "phone_number": "+213 661 00 11 22" }))
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(updated["first_name"], "Yacine");
    assert_eq!(updated["last_name"], "Saidi");
    assert_eq!(updated["phone_number"], "+213661001122");

    // `null` clears an optional field; an absent field is left alone.
    let cleared = app
        .patch("/api/v1/me")
        .bearer(&account.access_token)
        .json(&json!({ "phone_number": null }))
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(cleared["phone_number"], serde_json::Value::Null);
    assert_eq!(cleared["first_name"], "Yacine");

    // Neither the role nor the e-mail can be changed here.
    for field in ["role", "email", "is_active"] {
        let response = app
            .patch("/api/v1/me")
            .bearer(&account.access_token)
            .json(&json!({ field: "admin" }))
            .send()
            .await;
        assert_eq!(response.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
        assert_eq!(response.json()["errors"][0]["code"], "unknown_field");
    }
}

#[tokio::test]
async fn phone_numbers_are_unique() {
    let app = TestApp::spawn().await;
    let first = app.register("phone1@example.test").await;
    let second = app.register("phone2@example.test").await;
    for (account, expected) in [(&first, StatusCode::OK), (&second, StatusCode::CONFLICT)] {
        let response = app
            .patch("/api/v1/me")
            .bearer(&account.access_token)
            .json(&json!({ "phone_number": "0770 00 00 01" }))
            .send()
            .await;
        assert_eq!(response.status, expected);
    }
    let response = app
        .patch("/api/v1/me")
        .bearer(&second.access_token)
        .json(&json!({ "phone_number": "0770 00 00 01" }))
        .send()
        .await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "phone_taken");
}

#[tokio::test]
async fn profile_preferences() {
    let app = TestApp::spawn().await;
    let account = app.register("profile@example.test").await;

    let profile =
        app.get("/api/v1/me/profile").bearer(&account.access_token).send().await.expect(StatusCode::OK).json();
    assert_eq!(profile["language"], "fr");
    assert_eq!(profile["push_notifications_enabled"], true);

    let updated = app
        .patch("/api/v1/me/profile")
        .bearer(&account.access_token)
        .json(&json!({ "language": "en", "bio": "Daily commuter", "sms_notifications_enabled": true }))
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(updated["language"], "en");
    assert_eq!(updated["bio"], "Daily commuter");
    assert_eq!(updated["sms_notifications_enabled"], true);

    // The account language drives problem documents when no Accept-Language is sent.
    let invalid = app
        .patch("/api/v1/me/profile")
        .bearer(&account.access_token)
        .json(&json!({ "language": "de" }))
        .send()
        .await;
    assert_eq!(invalid.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");

    let too_long = app
        .patch("/api/v1/me/profile")
        .bearer(&account.access_token)
        .json(&json!({ "bio": "x".repeat(1001) }))
        .send()
        .await;
    assert_eq!(too_long.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(too_long.json()["errors"][0]["field"], "bio");
}

#[tokio::test]
async fn idempotency_keys_replay_completed_requests() {
    let app = TestApp::spawn().await;
    app.register("idem@example.test").await;
    let body = json!({ "email": "idem@example.test" });

    let first = app
        .post("/api/v1/auth/password/reset")
        .header("idempotency-key", "c0ffee00-0000-4000-8000-000000000001")
        .json(&body)
        .send()
        .await
        .expect(StatusCode::ACCEPTED);
    assert_eq!(first.header("idempotent-replayed"), None);
    let replay = app
        .post("/api/v1/auth/password/reset")
        .header("idempotency-key", "c0ffee00-0000-4000-8000-000000000001")
        .json(&body)
        .send()
        .await
        .expect(StatusCode::ACCEPTED);
    assert_eq!(replay.header("idempotent-replayed"), Some("true"));

    // The same key with another payload is a client bug.
    let mismatch = app
        .post("/api/v1/auth/password/reset")
        .header("idempotency-key", "c0ffee00-0000-4000-8000-000000000001")
        .json(&json!({ "email": "other@example.test" }))
        .send()
        .await;
    assert_eq!(mismatch.problem(StatusCode::UNPROCESSABLE_ENTITY), "idempotency_key_reused");

    let malformed = app
        .post("/api/v1/auth/password/reset")
        .header("idempotency-key", "")
        .json(&body)
        .send()
        .await;
    assert_eq!(malformed.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
}

#[tokio::test]
async fn secret_bearing_responses_are_never_replayed() {
    let app = TestApp::spawn().await;
    let request = || {
        app.post("/api/v1/auth/register")
            .header("idempotency-key", "register-once-0001")
            .json(&json!({ "email": "secret@example.test", "password": dz_testkit::PASSWORD }))
            .send()
    };
    let created = request().await.expect(StatusCode::CREATED);
    assert_eq!(created.header("cache-control"), Some("no-store"));
    // Tokens are not stored for replay: the retry runs again (and hits the unique e-mail).
    let retry = request().await;
    assert_eq!(retry.header("idempotent-replayed"), None);
    assert_eq!(retry.problem(StatusCode::CONFLICT), "email_taken");
}
