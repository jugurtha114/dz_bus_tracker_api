//! Authentication flows end to end: registration, login and lockout, refresh-token rotation
//! with reuse detection, sessions, logout, password change and reset.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use axum::http::StatusCode;
use dz_testkit::{PASSWORD, TestApp};
use serde_json::{Value, json};

fn field_codes(problem: &Value) -> Vec<(String, String)> {
    problem["errors"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| (e["field"].as_str().unwrap().to_owned(), e["code"].as_str().unwrap().to_owned()))
        .collect()
}

#[tokio::test]
async fn registration_signs_the_passenger_in() {
    let app = TestApp::spawn().await;
    let response = app
        .post("/api/v1/auth/register")
        .json(&json!({
            "email": "  Amina.Benali@Example.TEST ",
            "password": PASSWORD,
            "first_name": "Amina",
            "last_name": "Benali",
            "phone_number": "0550 12 34 56",
            "language": "ar",
        }))
        .send()
        .await
        .expect(StatusCode::CREATED);
    assert_eq!(response.header("location"), Some("/api/v1/me"));
    assert_eq!(response.header("cache-control"), Some("no-store"));
    let body = response.json();
    assert_eq!(body["user"]["email"], "amina.benali@example.test");
    assert_eq!(body["user"]["role"], "passenger");
    assert_eq!(body["user"]["phone_number"], "+213550123456");
    assert_eq!(body["tokens"]["token_type"], "Bearer");
    assert!(body["tokens"]["refresh_token"].as_str().unwrap().starts_with("dzr_"));

    let access = body["tokens"]["access_token"].as_str().unwrap();
    let me = app.get("/api/v1/me").bearer(access).send().await.expect(StatusCode::OK).json();
    assert_eq!(me["id"], body["user"]["id"]);
    assert_eq!(me["profile"]["language"], "ar");
}

#[tokio::test]
async fn registration_is_validated_strictly() {
    let app = TestApp::spawn().await;

    // Callers cannot choose their role (or send any field the API does not know).
    let smuggled = app
        .post("/api/v1/auth/register")
        .json(&json!({ "email": "x@example.test", "password": PASSWORD, "role": "admin" }))
        .send()
        .await;
    assert_eq!(smuggled.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(field_codes(&smuggled.json()), [("role".to_owned(), "unknown_field".to_owned())]);

    let invalid = app
        .post("/api/v1/auth/register")
        .json(&json!({ "email": "not-an-email", "password": "short", "phone_number": "12" }))
        .send()
        .await;
    assert_eq!(invalid.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    let codes = field_codes(&invalid.json());
    assert!(codes.contains(&("email".to_owned(), "invalid_email".to_owned())), "{codes:?}");
    assert!(codes.contains(&("password".to_owned(), "password_too_short".to_owned())), "{codes:?}");
    assert!(codes.contains(&("phone_number".to_owned(), "invalid_phone".to_owned())), "{codes:?}");

    let similar = app
        .post("/api/v1/auth/register")
        .json(&json!({ "email": "karim.haddad@example.test", "password": "karim.haddad2026" }))
        .send()
        .await;
    assert_eq!(
        field_codes(&similar.json()),
        [("password".to_owned(), "password_too_similar".to_owned())]
    );
}

#[tokio::test]
async fn emails_are_unique_case_insensitively() {
    let app = TestApp::spawn().await;
    app.register("dup@example.test").await;
    let again = app
        .post("/api/v1/auth/register")
        .json(&json!({ "email": "DUP@example.test", "password": PASSWORD }))
        .send()
        .await;
    assert_eq!(again.problem(StatusCode::CONFLICT), "email_taken");
}

#[tokio::test]
async fn login_failures_are_indistinguishable() {
    let app = TestApp::spawn().await;
    app.register("known@example.test").await;

    let wrong_password = app
        .post("/api/v1/auth/login")
        .json(&json!({ "email": "known@example.test", "password": "not the password" }))
        .send()
        .await;
    let unknown_account = app
        .post("/api/v1/auth/login")
        .json(&json!({ "email": "unknown@example.test", "password": "not the password" }))
        .send()
        .await;
    let malformed_email = app
        .post("/api/v1/auth/login")
        .json(&json!({ "email": "nonsense", "password": "not the password" }))
        .send()
        .await;
    let strip = |mut v: Value| {
        v.as_object_mut().unwrap().remove("request_id");
        v
    };
    let expected = strip(wrong_password.json());
    assert_eq!(wrong_password.problem(StatusCode::UNAUTHORIZED), "invalid_credentials");
    assert_eq!(strip(unknown_account.json()), expected);
    assert_eq!(strip(malformed_email.json()), expected);

    let ok = app.login("KNOWN@example.test").await;
    assert_eq!(ok.email, "known@example.test");
}

#[tokio::test]
async fn repeated_failures_lock_the_account() {
    let app = TestApp::builder()
        .configure(|s| {
            s.auth.lockout_threshold = 3;
            s.auth.lockout_base_secs = 300;
        })
        .build()
        .await;
    let account = app.register("locked@example.test").await;
    let wrong = json!({ "email": "locked@example.test", "password": "not the password" });
    for _ in 0..3 {
        app.post("/api/v1/auth/login").json(&wrong).send().await.problem(StatusCode::UNAUTHORIZED);
    }

    // Even the right password is refused while locked, with the same generic error.
    let right = json!({ "email": "locked@example.test", "password": PASSWORD });
    let refused = app.post("/api/v1/auth/login").json(&right).send().await;
    assert_eq!(refused.problem(StatusCode::UNAUTHORIZED), "invalid_credentials");

    let (failures, locked): (i32, bool) = sqlx::query_as(
        "SELECT failed_login_attempts, locked_until > now() + interval '4 minutes' FROM users WHERE id = $1",
    )
    .bind(account.id)
    .fetch_one(app.pool())
    .await
    .unwrap();
    assert_eq!(failures, 3);
    assert!(locked, "the first lock lasts lockout_base_secs");

    // Once the lock has expired, a successful login clears the counter.
    sqlx::query("UPDATE users SET locked_until = now() - interval '1 second' WHERE id = $1")
        .bind(account.id)
        .execute(app.pool())
        .await
        .unwrap();
    app.post("/api/v1/auth/login").json(&right).send().await.expect(StatusCode::OK);
    let failures: i32 = sqlx::query_scalar("SELECT failed_login_attempts FROM users WHERE id = $1")
        .bind(account.id)
        .fetch_one(app.pool())
        .await
        .unwrap();
    assert_eq!(failures, 0);
}

#[tokio::test]
async fn deactivated_accounts_cannot_sign_in_or_refresh() {
    let app = TestApp::spawn().await;
    let account = app.register("gone@example.test").await;
    sqlx::query("UPDATE users SET is_active = false WHERE id = $1")
        .bind(account.id)
        .execute(app.pool())
        .await
        .unwrap();
    let login = app
        .post("/api/v1/auth/login")
        .json(&json!({ "email": "gone@example.test", "password": PASSWORD }))
        .send()
        .await;
    assert_eq!(login.problem(StatusCode::UNAUTHORIZED), "invalid_credentials");
    let refresh = app
        .post("/api/v1/auth/refresh")
        .json(&json!({ "refresh_token": account.refresh_token }))
        .send()
        .await;
    assert_eq!(refresh.problem(StatusCode::UNAUTHORIZED), "refresh_token_invalid");
}

#[tokio::test]
async fn refresh_tokens_rotate_and_reuse_revokes_the_session() {
    let app = TestApp::spawn().await;
    let account = app.register("rotate@example.test").await;

    let rotated = app
        .post("/api/v1/auth/refresh")
        .json(&json!({ "refresh_token": account.refresh_token }))
        .send()
        .await
        .expect(StatusCode::OK);
    assert_eq!(rotated.header("cache-control"), Some("no-store"));
    let pair = rotated.json();
    assert_eq!(pair["session_id"], account.session_id.to_string());
    let new_refresh = pair["refresh_token"].as_str().unwrap().to_owned();
    let new_access = pair["access_token"].as_str().unwrap().to_owned();
    assert_ne!(new_refresh, account.refresh_token);
    app.get("/api/v1/me").bearer(&new_access).send().await.expect(StatusCode::OK);

    // Presenting the spent token again means it was stolen: the whole session dies.
    let replay = app
        .post("/api/v1/auth/refresh")
        .json(&json!({ "refresh_token": account.refresh_token }))
        .send()
        .await;
    assert_eq!(replay.problem(StatusCode::UNAUTHORIZED), "refresh_token_reused");
    let legit = app.post("/api/v1/auth/refresh").json(&json!({ "refresh_token": new_refresh })).send().await;
    assert_eq!(legit.problem(StatusCode::UNAUTHORIZED), "refresh_token_invalid");
    for token in [&new_access, &account.access_token] {
        let me = app.get("/api/v1/me").bearer(token).send().await;
        assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");
    }

    let garbage = app.post("/api/v1/auth/refresh").json(&json!({ "refresh_token": "dzr_nope" })).send().await;
    assert_eq!(garbage.problem(StatusCode::UNAUTHORIZED), "refresh_token_invalid");
}

#[tokio::test]
async fn concurrent_refreshes_rotate_exactly_once() {
    let app = TestApp::spawn().await;
    let account = app.register("race@example.test").await;
    let body = json!({ "refresh_token": account.refresh_token });
    let (a, b) = tokio::join!(
        app.post("/api/v1/auth/refresh").json(&body).send(),
        app.post("/api/v1/auth/refresh").json(&body).send(),
    );
    let mut statuses = [a.status.as_u16(), b.status.as_u16()];
    statuses.sort_unstable();
    assert_eq!(statuses, [200, 401], "exactly one rotation wins");
}

#[tokio::test]
async fn bearer_tokens_are_verified() {
    let app = TestApp::spawn().await;
    let account = app.register("bearer@example.test").await;

    let tampered = format!("{}x", account.access_token);
    let response = app.get("/api/v1/me").bearer(&tampered).send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "token_invalid");
    assert!(response.header("www-authenticate").unwrap().starts_with("Bearer"));

    // A token signed by another deployment's key is rejected.
    let other = TestApp::spawn().await;
    let foreign = other.register("bearer@example.test").await;
    let response = app.get("/api/v1/me").bearer(&foreign.access_token).send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "token_invalid");

    let response = app.get("/api/v1/me").header("authorization", "Basic Zm9vOmJhcg==").send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "token_invalid");
}

#[tokio::test]
async fn logout_ends_only_the_current_session() {
    let app = TestApp::spawn().await;
    let phone = app.register("multi@example.test").await;
    let laptop = app.login("multi@example.test").await;

    app.post("/api/v1/auth/logout").bearer(&phone.access_token).send().await.expect(StatusCode::NO_CONTENT);
    let me = app.get("/api/v1/me").bearer(&phone.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");
    let refresh =
        app.post("/api/v1/auth/refresh").json(&json!({ "refresh_token": phone.refresh_token })).send().await;
    assert_eq!(refresh.problem(StatusCode::UNAUTHORIZED), "refresh_token_invalid");

    app.get("/api/v1/me").bearer(&laptop.access_token).send().await.expect(StatusCode::OK);
}

#[tokio::test]
async fn logout_all_ends_every_session() {
    let app = TestApp::spawn().await;
    let first = app.register("all@example.test").await;
    let second = app.login("all@example.test").await;
    app.post("/api/v1/auth/logout-all").bearer(&second.access_token).send().await.expect(StatusCode::NO_CONTENT);
    for token in [&first.access_token, &second.access_token] {
        let me = app.get("/api/v1/me").bearer(token).send().await;
        assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");
    }
}

#[tokio::test]
async fn sessions_can_be_listed_and_revoked() {
    let app = TestApp::spawn().await;
    let phone = app.register("devices@example.test").await;
    let laptop = app.login("devices@example.test").await;

    let sessions =
        app.get("/api/v1/auth/sessions").bearer(&laptop.access_token).send().await.expect(StatusCode::OK).json();
    let sessions = sessions.as_array().unwrap();
    assert_eq!(sessions.len(), 2);
    let current: Vec<&Value> = sessions.iter().filter(|s| s["current"] == true).collect();
    assert_eq!(current.len(), 1);
    assert_eq!(current[0]["id"], laptop.session_id.to_string());
    assert_eq!(current[0]["ip"], "198.51.100.7");

    app.delete(&format!("/api/v1/auth/sessions/{}", phone.session_id))
        .bearer(&laptop.access_token)
        .send()
        .await
        .expect(StatusCode::NO_CONTENT);
    let me = app.get("/api/v1/me").bearer(&phone.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");

    // Someone else's session is indistinguishable from a missing one.
    let stranger = app.register("stranger@example.test").await;
    let response = app
        .delete(&format!("/api/v1/auth/sessions/{}", stranger.session_id))
        .bearer(&laptop.access_token)
        .send()
        .await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
    app.get("/api/v1/me").bearer(&stranger.access_token).send().await.expect(StatusCode::OK);
}

#[tokio::test]
async fn changing_the_password_signs_out_other_sessions() {
    let app = TestApp::spawn().await;
    let old_device = app.register("change@example.test").await;
    let current = app.login("change@example.test").await;
    let new_password = "an entirely new passphrase";

    let wrong = app
        .post("/api/v1/auth/password/change")
        .bearer(&current.access_token)
        .json(&json!({ "current_password": "not it at all", "new_password": new_password }))
        .send()
        .await;
    assert_eq!(wrong.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(field_codes(&wrong.json()), [("current_password".to_owned(), "incorrect".to_owned())]);

    let same = app
        .post("/api/v1/auth/password/change")
        .bearer(&current.access_token)
        .json(&json!({ "current_password": PASSWORD, "new_password": PASSWORD }))
        .send()
        .await;
    assert_eq!(field_codes(&same.json()), [("new_password".to_owned(), "password_reused".to_owned())]);

    app.post("/api/v1/auth/password/change")
        .bearer(&current.access_token)
        .json(&json!({ "current_password": PASSWORD, "new_password": new_password }))
        .send()
        .await
        .expect(StatusCode::NO_CONTENT);

    app.get("/api/v1/me").bearer(&current.access_token).send().await.expect(StatusCode::OK);
    let me = app.get("/api/v1/me").bearer(&old_device.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");

    let old = app.post("/api/v1/auth/login").json(&json!({ "email": "change@example.test", "password": PASSWORD })).send().await;
    assert_eq!(old.problem(StatusCode::UNAUTHORIZED), "invalid_credentials");
    app.post("/api/v1/auth/login")
        .json(&json!({ "email": "change@example.test", "password": new_password }))
        .send()
        .await
        .expect(StatusCode::OK);
}

#[tokio::test]
async fn password_reset_round_trip() {
    let app = TestApp::spawn().await;
    let account = app.register("reset@example.test").await;

    for email in ["reset@example.test", "nobody@example.test"] {
        let response =
            app.post("/api/v1/auth/password/reset").lang("en").json(&json!({ "email": email })).send().await;
        assert_eq!(response.status, StatusCode::ACCEPTED, "same answer for unknown accounts");
    }
    assert_eq!(app.run_jobs().await, 2);
    let mail = app.sent_mail();
    assert_eq!(mail.len(), 1, "only existing accounts receive an e-mail");
    assert_eq!(mail[0].to, "reset@example.test");
    let link = mail[0].text_body.split_whitespace().find(|w| w.contains("#token=")).unwrap();
    assert!(link.starts_with("http://localhost:3000/reset-password#token="), "{link}");
    let token = link.split("#token=").nth(1).unwrap().to_owned();

    let new_password = "violet harbour lantern 42";
    let weak = app
        .post("/api/v1/auth/password/reset/confirm")
        .json(&json!({ "token": token, "new_password": "123" }))
        .send()
        .await;
    assert_eq!(weak.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");

    app.post("/api/v1/auth/password/reset/confirm")
        .json(&json!({ "token": token, "new_password": new_password }))
        .send()
        .await
        .expect(StatusCode::NO_CONTENT);

    // Single use; every existing session is signed out.
    let again = app
        .post("/api/v1/auth/password/reset/confirm")
        .json(&json!({ "token": token, "new_password": "yet another passphrase" }))
        .send()
        .await;
    assert_eq!(again.problem(StatusCode::BAD_REQUEST), "reset_token_invalid");
    let me = app.get("/api/v1/me").bearer(&account.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");
    app.post("/api/v1/auth/login")
        .json(&json!({ "email": "reset@example.test", "password": new_password }))
        .send()
        .await
        .expect(StatusCode::OK);
}

#[tokio::test]
async fn reset_requests_are_deduplicated_per_address() {
    let app = TestApp::spawn().await;
    app.register("flood@example.test").await;
    for _ in 0..5 {
        app.post("/api/v1/auth/password/reset")
            .json(&json!({ "email": "flood@example.test" }))
            .send()
            .await
            .expect(StatusCode::ACCEPTED);
    }
    assert_eq!(app.run_jobs().await, 1, "pending requests for one address collapse into one job");
    assert_eq!(app.sent_mail().len(), 1);
}
