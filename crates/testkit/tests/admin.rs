//! Administration (users, API keys, audit log) and the role/permission matrix.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::HashSet;

use axum::http::StatusCode;
use dz_domain::user::Role;
use dz_testkit::TestApp;
use serde_json::{Value, json};

#[tokio::test]
async fn permission_matrix() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let driver = app.account(Role::Driver).await;
    let passenger = app.account(Role::Passenger).await;
    let auditor_key = app.api_key(&admin, &["audit_log:read"]).await;
    let catalog_key = app.api_key(&admin, &["catalog:read"]).await;

    #[derive(Clone, Copy)]
    enum Caller {
        Anonymous,
        Passenger,
        Driver,
        Admin,
        AuditorKey,
        CatalogKey,
    }
    use Caller::{Admin, Anonymous, AuditorKey, CatalogKey, Driver, Passenger};
    let user_path = format!("/api/v1/admin/users/{}", passenger.id);

    // (path, [anonymous, passenger, driver, admin, auditor key, catalog key])
    let matrix: [(&str, [u16; 6]); 7] = [
        ("/api/v1/me", [401, 200, 200, 200, 403, 403]),
        ("/api/v1/me/profile", [401, 200, 200, 200, 403, 403]),
        ("/api/v1/auth/sessions", [401, 200, 200, 200, 403, 403]),
        ("/api/v1/admin/users", [401, 403, 403, 200, 403, 403]),
        (&user_path, [401, 403, 403, 200, 403, 403]),
        ("/api/v1/admin/api-keys", [401, 403, 403, 200, 403, 403]),
        ("/api/v1/admin/audit-log", [401, 403, 403, 200, 200, 403]),
    ];
    let callers = [Anonymous, Passenger, Driver, Admin, AuditorKey, CatalogKey];
    for (path, expected) in matrix {
        for (caller, expected) in callers.iter().zip(expected) {
            let request = app.get(path);
            let request = match caller {
                Anonymous => request,
                Passenger => request.bearer(&passenger.access_token),
                Driver => request.bearer(&driver.access_token),
                Admin => request.bearer(&admin.access_token),
                AuditorKey => request.api_key(&auditor_key),
                CatalogKey => request.api_key(&catalog_key),
            };
            let response = request.send().await;
            assert_eq!(
                response.status.as_u16(),
                expected,
                "GET {path}: {}",
                String::from_utf8_lossy(&response.body)
            );
            match expected {
                401 => assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "authentication_required"),
                403 => assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden"),
                _ => {}
            }
        }
    }

    // Writes are denied the same way.
    let patch = json!({ "is_active": false });
    for token in [&passenger.access_token, &driver.access_token] {
        let response = app.patch(&user_path).bearer(token).json(&patch).send().await;
        assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
    }
    let response = app.patch(&user_path).api_key(&auditor_key).json(&patch).send().await;
    assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
}

#[tokio::test]
async fn listing_users_with_cursor_pagination_and_filters() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    for i in 0..5 {
        app.register(&format!("page{i}@example.test")).await;
    }
    app.account(Role::Driver).await;

    let mut seen = Vec::new();
    let mut cursor: Option<String> = None;
    loop {
        let uri = match &cursor {
            Some(c) => format!("/api/v1/admin/users?limit=2&cursor={c}"),
            None => "/api/v1/admin/users?limit=2".to_owned(),
        };
        let page = app.get(&uri).bearer(&admin.access_token).send().await.expect(StatusCode::OK).json();
        let items = page["items"].as_array().unwrap();
        assert!(items.len() <= 2);
        seen.extend(items.iter().map(|u| u["id"].as_str().unwrap().to_owned()));
        match page["next_cursor"].as_str() {
            Some(next) => cursor = Some(next.to_owned()),
            None => break,
        }
    }
    assert_eq!(seen.len(), 7, "admin + 5 passengers + driver");
    assert_eq!(seen.iter().collect::<HashSet<_>>().len(), 7, "pages never overlap");
    let mut newest_first = seen.clone();
    newest_first.sort_by(|a, b| b.cmp(a));
    assert_eq!(seen, newest_first, "UUIDv7 ids sort by creation time, newest first");

    let drivers = app
        .get("/api/v1/admin/users?role=driver")
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(drivers["items"].as_array().unwrap().len(), 1);
    assert_eq!(drivers["items"][0]["role"], "driver");

    let prefix = app
        .get("/api/v1/admin/users?email=PAGE&limit=100")
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(prefix["items"].as_array().unwrap().len(), 5);

    // Only allow-listed filters, and bounded limits.
    for bad in ["?sort=email", "?limit=0", "?limit=101", "?cursor=not-a-cursor", "?role=superuser"] {
        let response =
            app.get(&format!("/api/v1/admin/users{bad}")).bearer(&admin.access_token).send().await;
        assert_eq!(response.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error", "{bad}");
    }
}

#[tokio::test]
async fn reading_a_user() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let user = app
        .get(&format!("/api/v1/admin/users/{}", passenger.id))
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(user["email"], passenger.email);
    assert!(user.get("password_hash").is_none());

    for missing in [uuid::Uuid::now_v7().to_string(), "not-a-uuid".to_owned()] {
        let response =
            app.get(&format!("/api/v1/admin/users/{missing}")).bearer(&admin.access_token).send().await;
        assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
    }
}

#[tokio::test]
async fn deactivating_a_user_signs_them_out_and_is_audited() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;

    let updated = app
        .patch(&format!("/api/v1/admin/users/{}", passenger.id))
        .bearer(&admin.access_token)
        .header("x-request-id", "audit-trail-0001")
        .json(&json!({ "is_active": false }))
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(updated["is_active"], false);

    let me = app.get("/api/v1/me").bearer(&passenger.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");

    let log = app
        .get("/api/v1/admin/audit-log?action=user.update")
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    let entries = log["items"].as_array().unwrap();
    assert_eq!(entries.len(), 1);
    let entry = &entries[0];
    assert_eq!(entry["actor_type"], "user");
    assert_eq!(entry["actor_id"], admin.id.to_string());
    assert_eq!(entry["resource_type"], "user");
    assert_eq!(entry["resource_id"], passenger.id.to_string());
    assert_eq!(entry["details"]["is_active"], false);
    assert_eq!(entry["ip"], "198.51.100.7");
    assert_eq!(entry["request_id"], "audit-trail-0001");

    // Reactivation lets the user sign in again.
    app.patch(&format!("/api/v1/admin/users/{}", passenger.id))
        .bearer(&admin.access_token)
        .json(&json!({ "is_active": true }))
        .send()
        .await
        .expect(StatusCode::OK);
    app.login(&passenger.email).await;
}

#[tokio::test]
async fn role_changes_take_effect_on_the_next_sign_in() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    app.patch(&format!("/api/v1/admin/users/{}", passenger.id))
        .bearer(&admin.access_token)
        .json(&json!({ "role": "driver" }))
        .send()
        .await
        .expect(StatusCode::OK);

    // Tokens carry the role, so existing sessions end.
    let me = app.get("/api/v1/me").bearer(&passenger.access_token).send().await;
    assert_eq!(me.problem(StatusCode::UNAUTHORIZED), "session_revoked");
    let again = app.login(&passenger.email).await;
    assert_eq!(again.role, Role::Driver);

    // `service` is not a user role; nobody can be made one through this endpoint.
    let response = app
        .patch(&format!("/api/v1/admin/users/{}", passenger.id))
        .bearer(&admin.access_token)
        .json(&json!({ "role": "service" }))
        .send()
        .await;
    assert_eq!(response.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
}

#[tokio::test]
async fn administrators_cannot_lock_themselves_out() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    for patch in [json!({ "is_active": false }), json!({ "role": "passenger" })] {
        let response = app
            .patch(&format!("/api/v1/admin/users/{}", admin.id))
            .bearer(&admin.access_token)
            .json(&patch)
            .send()
            .await;
        assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
    }
}

#[tokio::test]
async fn api_key_lifecycle() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;

    let error_fields = |problem: &Value| -> Vec<String> {
        problem["errors"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| e["field"].as_str().unwrap().to_owned())
            .collect()
    };
    let unnamed = app
        .post("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .json(&json!({ "name": "", "scopes": ["audit_log:read"] }))
        .send()
        .await;
    assert_eq!(unnamed.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(error_fields(&unnamed.json()), ["name"]);

    let bad_scopes = app
        .post("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .json(&json!({ "name": "ci", "scopes": ["audit_log:read", "user:manage", "nonsense"] }))
        .send()
        .await;
    assert_eq!(bad_scopes.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(
        error_fields(&bad_scopes.json()),
        ["scopes[1]", "scopes[2]"],
        "user:manage is never grantable to keys"
    );

    let created = app
        .post("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .json(&json!({ "name": "reporting", "scopes": ["audit_log:read"] }))
        .send()
        .await
        .expect(StatusCode::CREATED);
    assert_eq!(created.header("cache-control"), Some("no-store"));
    let body = created.json();
    let id = body["api_key"]["id"].as_str().unwrap().to_owned();
    let secret = body["secret"].as_str().unwrap().to_owned();
    assert!(secret.starts_with(body["api_key"]["prefix"].as_str().unwrap()));
    assert_eq!(created.header("location"), Some(format!("/api/v1/admin/api-keys/{id}").as_str()));

    let listed = app
        .get("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::OK);
    assert!(!String::from_utf8_lossy(&listed.body).contains(&secret), "secrets are shown once");

    app.get("/api/v1/admin/audit-log").api_key(&secret).send().await.expect(StatusCode::OK);
    let used: Value = app
        .get("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .send()
        .await
        .json();
    assert!(used["items"][0]["last_used_at"].is_string());

    app.delete(&format!("/api/v1/admin/api-keys/{id}"))
        .bearer(&admin.access_token)
        .send()
        .await
        .expect(StatusCode::NO_CONTENT);
    let revoked = app.get("/api/v1/admin/audit-log").api_key(&secret).send().await;
    assert_eq!(revoked.problem(StatusCode::UNAUTHORIZED), "api_key_invalid");

    let wrong_secret = format!("{}0", &secret[..secret.len() - 1]);
    let response = app.get("/api/v1/admin/audit-log").api_key(&wrong_secret).send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "api_key_invalid");

    let actions: Vec<String> = app
        .get("/api/v1/admin/audit-log?resource_type=api_key")
        .bearer(&admin.access_token)
        .send()
        .await
        .json()["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| e["action"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(actions, ["api_key.revoke", "api_key.create"]);
}

#[tokio::test]
async fn expired_api_keys_are_rejected() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let secret = app.api_key(&admin, &["audit_log:read"]).await;
    sqlx::query("UPDATE api_keys SET expires_at = now() - interval '1 minute'")
        .execute(app.pool())
        .await
        .unwrap();
    let response = app.get("/api/v1/admin/audit-log").api_key(&secret).send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "api_key_invalid");

    let past = app
        .post("/api/v1/admin/api-keys")
        .bearer(&admin.access_token)
        .json(&json!({ "name": "late", "scopes": ["catalog:read"], "expires_at": "2000-01-01T00:00:00Z" }))
        .send()
        .await;
    assert_eq!(past.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
}

#[tokio::test]
async fn every_protected_endpoint_requires_authentication() {
    use axum::http::Method;
    let app = TestApp::spawn().await;
    let id = uuid::Uuid::now_v7();
    let endpoints = [
        (Method::POST, "/api/v1/auth/logout".to_owned()),
        (Method::POST, "/api/v1/auth/logout-all".to_owned()),
        (Method::POST, "/api/v1/auth/password/change".to_owned()),
        (Method::GET, "/api/v1/auth/sessions".to_owned()),
        (Method::DELETE, format!("/api/v1/auth/sessions/{id}")),
        (Method::GET, "/api/v1/me".to_owned()),
        (Method::PATCH, "/api/v1/me".to_owned()),
        (Method::GET, "/api/v1/me/profile".to_owned()),
        (Method::PATCH, "/api/v1/me/profile".to_owned()),
        (Method::GET, "/api/v1/admin/users".to_owned()),
        (Method::GET, format!("/api/v1/admin/users/{id}")),
        (Method::PATCH, format!("/api/v1/admin/users/{id}")),
        (Method::GET, "/api/v1/admin/api-keys".to_owned()),
        (Method::POST, "/api/v1/admin/api-keys".to_owned()),
        (Method::DELETE, format!("/api/v1/admin/api-keys/{id}")),
        (Method::GET, "/api/v1/admin/audit-log".to_owned()),
    ];
    // Authentication is checked before the body is even parsed.
    for (method, path) in endpoints {
        let response = app.request(method.clone(), &path).json(&json!({})).send().await;
        assert_eq!(
            response.problem(StatusCode::UNAUTHORIZED),
            "authentication_required",
            "{method} {path}"
        );
        assert!(response.header("www-authenticate").is_some(), "{method} {path}");
    }

    let admin = app.account(Role::Admin).await;
    let missing = app.delete(&format!("/api/v1/admin/api-keys/{id}")).bearer(&admin.access_token).send().await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    let missing = app
        .patch(&format!("/api/v1/admin/users/{id}"))
        .bearer(&admin.access_token)
        .json(&json!({ "is_active": false }))
        .send()
        .await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
}
