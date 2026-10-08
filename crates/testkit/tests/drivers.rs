//! Driver programme against real PostgreSQL and S3 (RustFS): applications with identity
//! documents, the driver's own profile, every transition of the state machine (allowed and
//! refused), the role change on approval, suspension side effects, privacy of profiles,
//! conflicts, the status history and its append-only table, and the notification jobs.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::BTreeSet;

use axum::http::{Method, StatusCode};
use chrono::{DateTime, Utc};
use dz_app::AppError;
use dz_app::drivers::ports::{DriverRepository, StatusChange};
use dz_app::ports::{ObjectStorage, WriteEffects};
use dz_domain::ConflictKind;
use dz_domain::driver::DriverStatus;
use dz_domain::ids::{DriverId, DriverStatusChangeId, UserId};
use dz_domain::user::Role;
use dz_testkit::{Account, TestApp, TestRequest, TestResponse};
use futures::future::join_all;
use serde_json::{Value, json};
use uuid::Uuid;

/// A tiny but real PNG (1×1, transparent).
const PNG: &[u8] = &[
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
    0x89, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
    0x42, 0x60, 0x82,
];
const PDF: &[u8] = b"%PDF-1.4\n% driving licence scan\n%%EOF\n";

const ID_CARD: &str = "109850123456789012";
const OTHER_ID_CARD: &str = "209850123456789012";

const GET: Method = Method::GET;
const POST: Method = Method::POST;
const PUT: Method = Method::PUT;
const PATCH: Method = Method::PATCH;

/// Who sends a request.
#[derive(Clone, Copy)]
enum As<'a> {
    Anonymous,
    User(&'a Account),
    Key(&'a str),
}

fn auth(request: TestRequest, caller: As<'_>) -> TestRequest {
    match caller {
        As::Anonymous => request,
        As::User(account) => request.bearer(&account.access_token),
        As::Key(secret) => request.api_key(secret),
    }
}

async fn call(
    app: &TestApp,
    caller: As<'_>,
    method: Method,
    uri: &str,
    body: Option<Value>,
) -> TestResponse {
    let request = auth(app.request(method, uri), caller);
    match body {
        Some(body) => request.json(&body).send().await,
        None => request.send().await,
    }
}

/// The JSON body of a successful (`200`) request.
async fn ok(
    app: &TestApp,
    caller: As<'_>,
    method: Method,
    uri: &str,
    body: Option<Value>,
) -> Value {
    call(app, caller, method, uri, body).await.expect(StatusCode::OK).json()
}

/// `(status, status_reason)` of a profile.
fn state(profile: &Value) -> (Value, Value) {
    (profile["status"].clone(), profile["status_reason"].clone())
}

/// `(field, code)` of every field error of a `422` problem document.
fn errors(response: &TestResponse) -> Vec<(String, String)> {
    assert_eq!(response.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    let text = |v: &Value| v.as_str().unwrap().to_owned();
    let doc = response.json();
    let errors = doc["errors"].as_array().unwrap();
    errors.iter().map(|e| (text(&e["field"]), text(&e["code"]))).collect()
}

fn pairs(expected: &[(&str, &str)]) -> Vec<(String, String)> {
    expected.iter().map(|(f, c)| ((*f).to_owned(), (*c).to_owned())).collect()
}

fn id_of(value: &Value) -> Uuid {
    value["id"].as_str().and_then(|id| id.parse().ok()).expect("id")
}

/// Uploads both identity documents as `account`.
async fn documents(app: &TestApp, account: &Account) -> (Uuid, Uuid) {
    let id_card = app.upload(account, "driver_id_card", "image/png", PNG).await;
    let licence = app.upload(account, "driver_license", "application/pdf", PDF).await;
    (id_card, licence)
}

async fn application_body(app: &TestApp, account: &Account, id_card: &str, licence: &str) -> Value {
    let (id_card_upload, licence_upload) = documents(app, account).await;
    json!({
        "phone_number": "0555 12 34 56",
        "id_card_number": id_card,
        "id_card_photo_upload_id": id_card_upload,
        "driver_license_number": licence,
        "driver_license_photo_upload_id": licence_upload,
        "years_of_experience": 6,
    })
}

async fn apply(app: &TestApp, account: &Account, body: Value) -> TestResponse {
    call(app, As::User(account), POST, "/api/v1/drivers/applications", Some(body)).await
}

/// A passenger with a pending application: `(account, profile)`.
async fn applicant(app: &TestApp, id_card: &str, licence: &str) -> (Account, Value) {
    let account = app.account(Role::Passenger).await;
    let body = application_body(app, &account, id_card, licence).await;
    let profile = apply(app, &account, body).await.expect(StatusCode::CREATED).json();
    (account, profile)
}

/// `POST /drivers/{id}/<verb>` as `caller`, with `{reason}` when given. Approvals name the
/// current version of the profile, as a reviewer who just read it does.
async fn review(
    app: &TestApp,
    caller: As<'_>,
    id: Uuid,
    verb: &str,
    reason: Option<&str>,
) -> TestResponse {
    let uri = format!("/api/v1/drivers/{id}/{verb}");
    let body = if verb == "approve" {
        Some(json!({ "expected_updated_at": stored_version(app, id).await }))
    } else {
        reason.map(|r| json!({ "reason": r }))
    };
    call(app, caller, POST, &uri, body).await
}

/// The `updated_at` of a profile in the database (now for an unknown profile).
async fn stored_version(app: &TestApp, id: Uuid) -> DateTime<Utc> {
    let stored = sqlx::query_scalar("SELECT updated_at FROM drivers WHERE id = $1")
        .bind(id)
        .fetch_optional(app.pool())
        .await
        .unwrap();
    stored.unwrap_or_else(Utc::now)
}

async fn reapply(app: &TestApp, account: &Account) -> TestResponse {
    call(app, As::User(account), POST, "/api/v1/drivers/me/reapply", None).await
}

/// The current role of an account in the database.
async fn stored_role(app: &TestApp, id: Uuid) -> String {
    sqlx::query_scalar("SELECT role FROM users WHERE id = $1")
        .bind(id)
        .fetch_one(app.pool())
        .await
        .unwrap()
}

async fn object_key(app: &TestApp, upload: Uuid) -> String {
    sqlx::query_scalar("SELECT object_key FROM uploads WHERE id = $1")
        .bind(upload)
        .fetch_one(app.pool())
        .await
        .unwrap()
}

async fn upload_status(app: &TestApp, upload: Uuid) -> String {
    sqlx::query_scalar("SELECT status FROM uploads WHERE id = $1")
        .bind(upload)
        .fetch_one(app.pool())
        .await
        .unwrap()
}

/// Kinds of the queued jobs, oldest first.
async fn queued_jobs(app: &TestApp) -> Vec<String> {
    sqlx::query_scalar("SELECT kind FROM jobs WHERE status = 'queued' ORDER BY created_at, id")
        .fetch_all(app.pool())
        .await
        .unwrap()
}

async fn audit_actions(app: &TestApp, driver: Uuid) -> Vec<String> {
    sqlx::query_scalar(
        "SELECT action FROM audit_log WHERE resource_type = 'driver' AND resource_id = $1
         ORDER BY occurred_at, id",
    )
    .bind(driver.to_string())
    .fetch_all(app.pool())
    .await
    .unwrap()
}

/// `(from_status, to_status)` of the history, oldest first.
async fn steps(app: &TestApp, caller: &Account, id: Uuid) -> Vec<(Value, Value)> {
    let uri = format!("/api/v1/drivers/{id}/status-history");
    let page = call(app, As::User(caller), GET, &uri, None).await.expect(StatusCode::OK).json();
    let items = page["items"].as_array().unwrap();
    items.iter().rev().map(|e| (e["from_status"].clone(), e["to_status"].clone())).collect()
}

#[tokio::test]
async fn an_application_creates_a_pending_profile_bound_to_the_caller() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let (id_card_upload, licence_upload) = documents(&app, &account).await;
    let body = json!({
        "phone_number": "0555 12 34 56",
        "id_card_number": "1098 5012 3456 7890 12",
        "id_card_photo_upload_id": id_card_upload,
        "driver_license_number": "dz-16-1234",
        "driver_license_photo_upload_id": licence_upload,
        "years_of_experience": 6,
    });
    let created = apply(&app, &account, body).await.expect(StatusCode::CREATED);
    let profile = created.json();
    let id = id_of(&profile);
    assert_eq!(created.header("location"), Some(format!("/api/v1/drivers/{id}").as_str()));
    assert_eq!(profile["user"]["id"], account.id.to_string(), "bound to the caller (L-02)");
    assert_eq!(profile["user"]["email"], account.email);
    assert_eq!(profile["user"]["first_name"], "Test");
    assert_eq!(profile["phone_number"], "+213555123456");
    assert_eq!(profile["id_card_number"], ID_CARD);
    assert_eq!(profile["driver_license_number"], "DZ-16-1234");
    assert_eq!(profile["years_of_experience"], 6);
    assert_eq!(profile["status"], "pending");
    assert_eq!(profile["status_reason"], Value::Null);
    assert_eq!(profile["is_available"], false);
    assert_eq!((&profile["rating"], &profile["rating_count"]), (&Value::Null, &json!(0)));
    assert_eq!(profile["status_changed_at"], profile["created_at"]);

    // Both documents are attached and served to the owner through presigned URLs.
    for (upload, field, bytes) in [
        (id_card_upload, "id_card_photo_url", PNG),
        (licence_upload, "driver_license_photo_url", PDF),
    ] {
        assert_eq!(upload_status(&app, upload).await, "attached");
        let url = profile[field].as_str().unwrap();
        assert!(url.contains(&object_key(&app, upload).await));
        assert_eq!(app.download(url).await, (StatusCode::OK, bytes.to_vec()));
    }

    let me = call(&app, As::User(&account), GET, "/api/v1/drivers/me", None).await;
    assert_eq!(id_of(&me.expect(StatusCode::OK).json()), id);
    let location = format!("/api/v1/drivers/{id}");
    let own = call(&app, As::User(&account), GET, &location, None).await.expect(StatusCode::OK);
    assert_eq!(own.json()["id_card_number"], ID_CARD);
    let history = steps(&app, &account, id).await;
    assert_eq!(history, vec![(Value::Null, json!("pending"))]);

    // Self-service is not audited; the driver and the reviewers are notified after the commit.
    assert!(audit_actions(&app, id).await.is_empty());
    assert_eq!(queued_jobs(&app).await, ["driver_status_changed", "driver_review_requested"]);
    let admin = app.account(Role::Admin).await;
    assert_eq!(app.run_jobs().await, 2);
    let mail = app.sent_mail();
    let to: BTreeSet<&str> = mail.iter().map(|m| m.to.as_str()).collect();
    assert_eq!(to, BTreeSet::from([account.email.as_str(), admin.email.as_str()]));
    let review_mail = mail.iter().find(|m| m.to == admin.email).unwrap();
    assert!(review_mail.text_body.contains(&id.to_string()));
}

#[tokio::test]
async fn applications_are_validated() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let bad = json!({
        "phone_number": "0215123456",
        "id_card_number": "12345",
        "id_card_photo_upload_id": Uuid::now_v7(),
        "driver_license_number": "AB 12",
        "driver_license_photo_upload_id": Uuid::now_v7(),
        "years_of_experience": 61,
    });
    assert_eq!(
        errors(&apply(&app, &account, bad).await),
        pairs(&[
            ("phone_number", "invalid_phone"),
            ("id_card_number", "invalid_format"),
            ("driver_license_number", "invalid_format"),
            ("years_of_experience", "out_of_range"),
        ])
    );

    let mut body = application_body(&app, &account, ID_CARD, "L-1").await;
    body["status"] = json!("approved");
    let response = apply(&app, &account, body.clone()).await;
    assert_eq!(errors(&response), pairs(&[("status", "unknown_field")]));
    let mut missing = body.clone();
    missing.as_object_mut().unwrap().remove("status");
    missing.as_object_mut().unwrap().remove("driver_license_number");
    let response = apply(&app, &account, missing).await;
    assert_eq!(errors(&response), pairs(&[("driver_license_number", "required")]));

    // Uploads of the wrong purpose (swapped) are unusable, and both are reported.
    let mut swapped = body.clone();
    swapped.as_object_mut().unwrap().remove("status");
    let id_card = swapped["id_card_photo_upload_id"].take();
    swapped["id_card_photo_upload_id"] = swapped["driver_license_photo_upload_id"].take();
    swapped["driver_license_photo_upload_id"] = id_card;
    assert_eq!(
        errors(&apply(&app, &account, swapped).await),
        pairs(&[
            ("id_card_photo_upload_id", "invalid_upload"),
            ("driver_license_photo_upload_id", "invalid_upload"),
        ])
    );
    // Someone else's upload is unusable too.
    let other = app.account(Role::Passenger).await;
    let mut foreign = body;
    foreign.as_object_mut().unwrap().remove("status");
    foreign["id_card_photo_upload_id"] =
        json!(app.upload(&other, "driver_id_card", "image/png", PNG).await);
    let response = apply(&app, &account, foreign).await;
    assert_eq!(errors(&response), pairs(&[("id_card_photo_upload_id", "invalid_upload")]));
    let none = call(&app, As::User(&account), GET, "/api/v1/drivers/me", None).await;
    assert_eq!(none.problem(StatusCode::NOT_FOUND), "not_found");
}

#[tokio::test]
async fn applying_needs_a_signed_in_applicant() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let key = app.api_key(&admin, &["catalog:read"]).await;
    let body = json!({
        "phone_number": "0555123456",
        "id_card_number": ID_CARD,
        "id_card_photo_upload_id": Uuid::now_v7(),
        "driver_license_number": "L-1",
        "driver_license_photo_upload_id": Uuid::now_v7(),
        "years_of_experience": 1,
    });
    let uri = "/api/v1/drivers/applications";
    let anonymous = call(&app, As::Anonymous, POST, uri, Some(body.clone())).await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let by_admin = call(&app, As::User(&admin), POST, uri, Some(body.clone())).await;
    assert_eq!(by_admin.problem(StatusCode::FORBIDDEN), "forbidden");
    let by_key = call(&app, As::Key(&key), POST, uri, Some(body)).await;
    assert_eq!(by_key.problem(StatusCode::FORBIDDEN), "forbidden");
    let own = [
        (GET, "/api/v1/drivers/me", None),
        (PATCH, "/api/v1/drivers/me", Some(json!({ "years_of_experience": 1 }))),
        (PUT, "/api/v1/drivers/me/availability", Some(json!({ "is_available": true }))),
        (POST, "/api/v1/drivers/me/reapply", None),
    ];
    for (method, uri, body) in own {
        let response = call(&app, As::Anonymous, method.clone(), uri, body.clone()).await;
        let problem = response.problem(StatusCode::UNAUTHORIZED);
        assert_eq!(problem, "authentication_required", "{method} {uri}");
        let response = call(&app, As::Key(&key), method.clone(), uri, body).await;
        assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden", "{method} {uri}");
    }
}

#[tokio::test]
async fn duplicate_profiles_and_documents_conflict_and_roll_back() {
    let app = TestApp::spawn().await;
    let (account, _) = applicant(&app, ID_CARD, "L-1").await;
    let again = application_body(&app, &account, OTHER_ID_CARD, "L-2").await;
    let response = apply(&app, &account, again).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "driver_profile_exists");

    let other = app.account(Role::Passenger).await;
    let same_card = application_body(&app, &other, ID_CARD, "L-2").await;
    let response = apply(&app, &other, same_card.clone()).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "id_card_taken");
    // The transaction rolled back: the uploads are still usable.
    for field in ["id_card_photo_upload_id", "driver_license_photo_upload_id"] {
        let upload = same_card[field].as_str().unwrap().parse().unwrap();
        assert_eq!(upload_status(&app, upload).await, "pending");
    }
    let mut same_licence = same_card;
    same_licence["id_card_number"] = json!(OTHER_ID_CARD);
    same_licence["driver_license_number"] = json!("l-1");
    let response = apply(&app, &other, same_licence.clone()).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "license_taken", "case-insensitive");
    same_licence["driver_license_number"] = json!("L-2");
    apply(&app, &other, same_licence).await.expect(StatusCode::CREATED);

    // Changing one's numbers to someone else's conflicts as well.
    let patch = json!({ "id_card_number": OTHER_ID_CARD });
    let response = call(&app, As::User(&account), PATCH, "/api/v1/drivers/me", Some(patch)).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "id_card_taken");
    let patch = json!({ "driver_license_number": "l-2" });
    let response = call(&app, As::User(&account), PATCH, "/api/v1/drivers/me", Some(patch)).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "license_taken");
}

#[tokio::test]
async fn every_transition_is_allowed_or_refused_by_the_state_machine() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let reviewer = As::User(&admin);
    let reason = Some("Documents illisibles");
    // Every action except the `allowed` ones is refused with `invalid_transition`.
    let refuse_all_but = |allowed: &'static [&'static str]| {
        let (app, account, admin) = (&app, &account, &admin);
        async move {
            for verb in ["approve", "reject", "suspend", "reinstate", "reapply"] {
                if allowed.contains(&verb) {
                    continue;
                }
                let response = if verb == "reapply" {
                    reapply(app, account).await
                } else {
                    let with_reason = matches!(verb, "reject" | "suspend").then_some("x");
                    review(app, As::User(admin), id, verb, with_reason).await
                };
                assert_eq!(response.problem(StatusCode::CONFLICT), "invalid_transition", "{verb}");
            }
        }
    };

    // pending: approve or reject.
    refuse_all_but(&["approve", "reject"]).await;
    let rejected = review(&app, reviewer, id, "reject", reason).await.expect(StatusCode::OK).json();
    assert_eq!(state(&rejected), (json!("rejected"), json!(reason)));
    // rejected: reapply only.
    refuse_all_but(&["reapply"]).await;
    let pending = reapply(&app, &account).await.expect(StatusCode::OK).json();
    assert_eq!(state(&pending), (json!("pending"), Value::Null));
    let approved = review(&app, reviewer, id, "approve", None).await.expect(StatusCode::OK).json();
    assert_eq!(approved["status"], "approved");
    // approved: suspend only.
    refuse_all_but(&["suspend"]).await;
    let suspended = review(&app, reviewer, id, "suspend", Some("Plaintes répétées")).await;
    let suspended = suspended.expect(StatusCode::OK).json();
    assert_eq!(state(&suspended), (json!("suspended"), json!("Plaintes répétées")));
    // suspended: reinstate only.
    refuse_all_but(&["reinstate"]).await;
    let reinstated = review(&app, reviewer, id, "reinstate", None).await;
    let reinstated = reinstated.expect(StatusCode::OK).json();
    assert_eq!(state(&reinstated), (json!("approved"), Value::Null));

    let history = steps(&app, &admin, id).await;
    let s = |v: &str| json!(v);
    assert_eq!(
        history,
        vec![
            (Value::Null, s("pending")),
            (s("pending"), s("rejected")),
            (s("rejected"), s("pending")),
            (s("pending"), s("approved")),
            (s("approved"), s("suspended")),
            (s("suspended"), s("approved")),
        ]
    );
    let uri = format!("/api/v1/drivers/{id}/status-history?limit=2");
    let page = call(&app, As::User(&account), GET, &uri, None).await.expect(StatusCode::OK).json();
    let newest = &page["items"][0];
    assert_eq!(newest["changed_by"], admin.id.to_string());
    assert_eq!(page["items"][1]["reason"], "Plaintes répétées");
    let cursor = page["next_cursor"].as_str().unwrap();
    let uri = format!("/api/v1/drivers/{id}/status-history?limit=10&cursor={cursor}");
    let rest = call(&app, As::User(&account), GET, &uri, None).await.expect(StatusCode::OK).json();
    assert_eq!(rest["items"].as_array().unwrap().len(), 4);
    assert_eq!(rest["items"][3]["changed_by"], account.id.to_string(), "the application");

    // Reviews are audited (not the driver's own actions).
    assert_eq!(
        audit_actions(&app, id).await,
        ["driver.reject", "driver.approve", "driver.suspend", "driver.reinstate"]
    );
}

#[tokio::test]
async fn reasons_are_required_to_reject_and_suspend() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (_, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let missing = review(&app, As::User(&admin), id, "reject", None).await;
    assert_eq!(missing.status, StatusCode::UNSUPPORTED_MEDIA_TYPE, "a body is required");
    let uri = format!("/api/v1/drivers/{id}/reject");
    let empty = call(&app, As::User(&admin), POST, &uri, Some(json!({}))).await;
    assert_eq!(errors(&empty), pairs(&[("reason", "required")]));
    let blank = review(&app, As::User(&admin), id, "reject", Some("   ")).await;
    assert_eq!(errors(&blank), pairs(&[("reason", "required")]));
    let long = "x".repeat(1001);
    let too_long = review(&app, As::User(&admin), id, "reject", Some(&long)).await;
    assert_eq!(errors(&too_long), pairs(&[("reason", "too_long")]));
    let body = json!({ "reason": "x", "notify": false });
    let extra = call(&app, As::User(&admin), POST, &uri, Some(body)).await;
    assert_eq!(errors(&extra), pairs(&[("notify", "unknown_field")]));
    review(&app, As::User(&admin), id, "approve", None).await.expect(StatusCode::OK);
    let blank = review(&app, As::User(&admin), id, "suspend", Some("")).await;
    assert_eq!(errors(&blank), pairs(&[("reason", "required")]));
}

#[tokio::test]
async fn approvals_apply_only_to_the_reviewed_documents() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let profile_uri = format!("/api/v1/drivers/{id}");
    let approve_uri = format!("{profile_uri}/approve");

    // The reviewer examines the application; its version is exact to the microsecond.
    let reviewed = ok(&app, As::User(&admin), GET, &profile_uri, None).await;
    let version = reviewed["updated_at"].clone();
    let parsed: DateTime<Utc> = serde_json::from_value(version.clone()).unwrap();
    assert_eq!(parsed, stored_version(&app, id).await);

    // Meanwhile the applicant replaces the identity card scan: the profile stays pending.
    let scan = app.upload(&account, "driver_id_card", "image/png", PNG).await;
    let patch = json!({ "id_card_photo_upload_id": scan });
    let swapped = ok(&app, As::User(&account), PATCH, "/api/v1/drivers/me", Some(patch)).await;
    assert_eq!(swapped["status"], "pending");
    assert_ne!(swapped["updated_at"], version);
    let jobs = queued_jobs(&app).await;

    // Approving the reviewed version would approve a scan nobody saw: refused, nothing changes.
    let stale = json!({ "expected_updated_at": version });
    let response = call(&app, As::User(&admin), POST, &approve_uri, Some(stale)).await;
    assert_eq!(response.problem(StatusCode::CONFLICT), "stale_state");
    let current = ok(&app, As::User(&admin), GET, &profile_uri, None).await;
    assert_eq!(current["status"], "pending");
    assert_eq!(current["updated_at"], swapped["updated_at"]);
    assert_eq!(stored_role(&app, account.id).await, "passenger");
    assert_eq!(steps(&app, &admin, id).await.len(), 1, "no status change recorded");
    assert!(audit_actions(&app, id).await.is_empty(), "nothing audited");
    assert_eq!(queued_jobs(&app).await, jobs, "nobody notified");

    // Once the current documents are reviewed, the approval applies to them.
    let url = current["id_card_photo_url"].as_str().unwrap();
    assert!(url.contains(&object_key(&app, scan).await), "the reviewer sees the new scan");
    let fresh = json!({ "expected_updated_at": current["updated_at"] });
    let approved = call(&app, As::User(&admin), POST, &approve_uri, Some(fresh)).await;
    assert_eq!(approved.expect(StatusCode::OK).json()["status"], "approved");
    assert_eq!(stored_role(&app, account.id).await, "driver");
    assert_eq!(audit_actions(&app, id).await, ["driver.approve"]);
}

/// The use-case compares versions before writing; the write compares them again, atomically,
/// for documents changed after that read.
#[tokio::test]
async fn the_database_only_approves_the_reviewed_version() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let reviewed = stored_version(&app, id).await;
    let patch = Some(json!({ "driver_license_number": "L-9" }));
    ok(&app, As::User(&account), PATCH, "/api/v1/drivers/me", patch).await;
    let approval = |expected_updated_at| StatusChange {
        id: DriverStatusChangeId::generate(),
        from: Some(DriverStatus::Pending),
        to: DriverStatus::Approved,
        reason: None,
        changed_by: Some(UserId::from_uuid(admin.id)),
        at: Utc::now(),
        expected_updated_at: Some(expected_updated_at),
    };
    let store = &*app.infra.store;
    let (driver, effects) = (DriverId::from_uuid(id), WriteEffects::default);

    let stale = DriverRepository::transition(store, driver, approval(reviewed), effects()).await;
    assert!(matches!(stale, Err(AppError::Conflict(ConflictKind::StaleState))), "{stale:?}");
    let unknown = DriverId::generate();
    let missing = DriverRepository::transition(store, unknown, approval(reviewed), effects()).await;
    assert!(matches!(missing, Err(AppError::NotFound("driver"))), "{missing:?}");
    let current = ok(&app, As::User(&admin), GET, &format!("/api/v1/drivers/{id}"), None).await;
    assert_eq!(current["status"], "pending");
    assert_eq!(current["driver_license_number"], "L-9", "the applicant's change is kept");
    assert_eq!(stored_role(&app, account.id).await, "passenger");
    assert_eq!(steps(&app, &admin, id).await.len(), 1, "no status change recorded");

    let fresh = approval(stored_version(&app, id).await);
    let approved = DriverRepository::transition(store, driver, fresh, effects()).await.unwrap();
    assert_eq!(approved.driver.status, DriverStatus::Approved);
    assert_eq!(stored_role(&app, account.id).await, "driver");
}

#[tokio::test]
async fn approvals_require_the_reviewed_version() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let profile_uri = format!("/api/v1/drivers/{}", id_of(&profile));
    let uri = format!("{profile_uri}/approve");
    let reviewer = As::User(&admin);
    let required = pairs(&[("expected_updated_at", "required")]);

    // No body at all (approvals used to have none), or no version in it.
    let missing = call(&app, reviewer, POST, &uri, None).await;
    assert_eq!(errors(&missing), required);
    let empty = call(&app, reviewer, POST, &uri, Some(json!({}))).await;
    assert_eq!(errors(&empty), required);
    let invalid_format = pairs(&[("expected_updated_at", "invalid_format")]);
    for invalid in [Value::Null, json!("yesterday"), json!(1_791_000_000)] {
        let body = json!({ "expected_updated_at": invalid });
        let response = call(&app, reviewer, POST, &uri, Some(body)).await;
        assert_eq!(errors(&response), invalid_format, "{invalid}");
    }
    let extra = json!({ "expected_updated_at": profile["updated_at"], "approve": true });
    let response = call(&app, reviewer, POST, &uri, Some(extra)).await;
    assert_eq!(errors(&response), pairs(&[("approve", "unknown_field")]));
    // A body must still be JSON.
    let version = profile["updated_at"].as_str().unwrap().to_owned();
    let text = app.request(POST, &uri).bearer(&admin.access_token).raw("text/plain", version);
    let response = text.send().await;
    assert_eq!(response.problem(StatusCode::UNSUPPORTED_MEDIA_TYPE), "unsupported_media_type");
    let blank = app.request(POST, &uri).bearer(&admin.access_token).raw("application/json", "");
    assert_eq!(blank.send().await.problem(StatusCode::BAD_REQUEST), "malformed_request");

    let current = ok(&app, reviewer, GET, &profile_uri, None).await;
    assert_eq!(current["status"], "pending", "nothing was approved");
    assert_eq!(stored_role(&app, account.id).await, "passenger");
}

#[tokio::test]
async fn approval_makes_the_applicant_a_driver_at_the_next_refresh() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    review(&app, As::User(&admin), id, "approve", None).await.expect(StatusCode::OK);
    assert_eq!(stored_role(&app, account.id).await, "driver");

    // The current access token still carries the passenger role…
    let me = call(&app, As::User(&account), GET, "/api/v1/me", None).await.expect(StatusCode::OK);
    assert_eq!(me.json()["role"], "driver", "the account itself is up to date");
    let bus_photo =
        json!({ "purpose": "bus_photo", "content_type": "image/png", "size_bytes": 10 });
    let uploads = "/api/v1/uploads";
    let before = call(&app, As::User(&account), POST, uploads, Some(bus_photo.clone())).await;
    assert_eq!(before.problem(StatusCode::FORBIDDEN), "forbidden");
    // …until it is refreshed: no session was revoked.
    let refreshed = app
        .post("/api/v1/auth/refresh")
        .json(&json!({ "refresh_token": account.refresh_token }))
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    let token = refreshed["access_token"].as_str().unwrap();
    let after = app.post(uploads).bearer(token).json(&bus_photo).send().await;
    after.expect(StatusCode::CREATED);

    // A suspended driver keeps the role (to follow their status); reinstating keeps it too.
    review(&app, As::User(&admin), id, "suspend", Some("Contrôle")).await.expect(StatusCode::OK);
    assert_eq!(stored_role(&app, account.id).await, "driver");
    let own = app.get("/api/v1/drivers/me").bearer(token).send().await.expect(StatusCode::OK);
    assert_eq!(own.json()["status"], "suspended");

    // Administrators keep their role when an application of theirs is approved.
    let (other, profile) = applicant(&app, OTHER_ID_CARD, "L-2").await;
    sqlx::query("UPDATE users SET role = 'admin' WHERE id = $1")
        .bind(other.id)
        .execute(app.pool())
        .await
        .unwrap();
    review(&app, As::User(&admin), id_of(&profile), "approve", None).await.expect(StatusCode::OK);
    assert_eq!(stored_role(&app, other.id).await, "admin");
}

#[tokio::test]
async fn suspension_takes_the_driver_and_their_buses_off_duty() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let availability = |value: bool| json!({ "is_available": value });
    let uri = "/api/v1/drivers/me/availability";
    let pending = call(&app, As::User(&account), PUT, uri, Some(availability(true))).await;
    assert_eq!(pending.problem(StatusCode::CONFLICT), "invalid_state");
    review(&app, As::User(&admin), id, "approve", None).await.expect(StatusCode::OK);
    let available = call(&app, As::User(&account), PUT, uri, Some(availability(true))).await;
    assert_eq!(available.expect(StatusCode::OK).json()["is_available"], true);

    // Buses arrive with WP4; insert them directly.
    let buses =
        [("12345-116-16", "active"), ("777-116-16", "maintenance"), ("1-100-01", "inactive")];
    for (plate, status) in buses {
        sqlx::query(
            "INSERT INTO buses (license_plate, driver_id, model, manufacturer, year, capacity,
                                status)
             VALUES ($1, $2, 'Citaro', 'Mercedes', 2020, 90, $3)",
        )
        .bind(plate)
        .bind(id)
        .bind(status)
        .execute(app.pool())
        .await
        .unwrap();
    }
    let suspended = review(&app, As::User(&admin), id, "suspend", Some("Accident")).await;
    assert_eq!(suspended.expect(StatusCode::OK).json()["is_available"], false);
    let statuses: Vec<String> = sqlx::query_scalar("SELECT status FROM buses WHERE driver_id = $1")
        .bind(id)
        .fetch_all(app.pool())
        .await
        .unwrap();
    assert_eq!(statuses, ["inactive", "inactive", "inactive"]);
    let again = call(&app, As::User(&account), PUT, uri, Some(availability(true))).await;
    assert_eq!(again.problem(StatusCode::CONFLICT), "invalid_state");
    let reinstated = review(&app, As::User(&admin), id, "reinstate", None).await;
    assert_eq!(reinstated.expect(StatusCode::OK).json()["is_available"], false);

    let invalid = call(&app, As::User(&account), PUT, uri, Some(json!({}))).await;
    assert_eq!(errors(&invalid), pairs(&[("is_available", "required")]));
    let stranger = app.account(Role::Passenger).await;
    let none = call(&app, As::User(&stranger), PUT, uri, Some(availability(true))).await;
    assert_eq!(none.problem(StatusCode::NOT_FOUND), "not_found");
}

#[tokio::test]
async fn new_documents_send_an_approved_profile_back_to_review() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    review(&app, As::User(&admin), id, "approve", None).await.expect(StatusCode::OK);
    let me = "/api/v1/drivers/me";
    let availability = json!({ "is_available": true });
    call(&app, As::User(&account), PUT, "/api/v1/drivers/me/availability", Some(availability))
        .await
        .expect(StatusCode::OK);
    app.run_jobs().await;

    // Contact details are not documents.
    let patch = json!({ "phone_number": "0770 11 22 33", "years_of_experience": 9 });
    let updated = ok(&app, As::User(&account), PATCH, me, Some(patch)).await;
    assert_eq!((&updated["status"], &updated["is_available"]), (&json!("approved"), &json!(true)));
    assert_eq!(updated["phone_number"], "+213770112233");
    assert_eq!(updated["years_of_experience"], 9);
    assert!(queued_jobs(&app).await.is_empty());

    // A new licence scan: pending again, off duty, the old scan deleted after its URL expired.
    let old_key: String =
        sqlx::query_scalar("SELECT driver_license_photo_key FROM drivers WHERE id = $1")
            .bind(id)
            .fetch_one(app.pool())
            .await
            .unwrap();
    let scan = app.upload(&account, "driver_license", "image/png", PNG).await;
    let patch = json!({ "driver_license_photo_upload_id": scan });
    let pending = ok(&app, As::User(&account), PATCH, me, Some(patch)).await;
    assert_eq!((&pending["status"], &pending["is_available"]), (&json!("pending"), &json!(false)));
    let new_url = pending["driver_license_photo_url"].as_str().unwrap();
    assert!(new_url.contains(&object_key(&app, scan).await));
    assert_eq!(app.download(new_url).await, (StatusCode::OK, PNG.to_vec()));
    assert_eq!(
        queued_jobs(&app).await,
        ["driver_status_changed", "driver_review_requested", "storage_delete_object"]
    );
    let history = steps(&app, &account, id).await;
    assert_eq!(history.last().unwrap(), &(json!("approved"), json!("pending")));
    sqlx::query("UPDATE jobs SET run_at = now() WHERE kind = 'storage_delete_object'")
        .execute(app.pool())
        .await
        .unwrap();
    assert_eq!(app.run_jobs().await, 3);
    let storage = app.storage().unwrap();
    assert!(storage.head(&old_key).await.unwrap().is_none(), "the replaced scan is deleted");
    assert!(storage.head(&object_key(&app, scan).await).await.unwrap().is_some());

    // The same values again change nothing.
    let same = json!({ "id_card_number": ID_CARD, "driver_license_number": "l-1" });
    let unchanged = ok(&app, As::User(&account), PATCH, me, Some(same)).await;
    assert_eq!(unchanged["updated_at"], pending["updated_at"]);

    // A used upload cannot be attached again; read-only fields cannot be patched.
    let reused = json!({ "driver_license_photo_upload_id": scan });
    let response = call(&app, As::User(&account), PATCH, me, Some(reused)).await;
    assert_eq!(errors(&response), pairs(&[("driver_license_photo_upload_id", "invalid_upload")]));
    for field in ["status", "is_available", "user_id", "rating"] {
        let response = call(&app, As::User(&account), PATCH, me, Some(json!({ field: "x" }))).await;
        assert_eq!(errors(&response), pairs(&[(field, "unknown_field")]));
    }
    let bad = json!({ "phone_number": "123", "years_of_experience": 70 });
    let response = call(&app, As::User(&account), PATCH, me, Some(bad)).await;
    assert_eq!(
        errors(&response),
        pairs(&[("phone_number", "invalid_phone"), ("years_of_experience", "out_of_range")])
    );
    let stranger = app.account(Role::Passenger).await;
    let patch = json!({ "years_of_experience": 1 });
    let none = call(&app, As::User(&stranger), PATCH, me, Some(patch)).await;
    assert_eq!(none.problem(StatusCode::NOT_FOUND), "not_found");
}

#[tokio::test]
async fn profiles_and_documents_are_never_shown_to_other_users() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let key = app.api_key(&admin, &["catalog:read", "bus:read", "tracking:read"]).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let (_, second) = applicant(&app, OTHER_ID_CARD, "L-2").await;
    let passenger = app.account(Role::Passenger).await;
    let driver = app.account(Role::Driver).await;

    let profile_uri = format!("/api/v1/drivers/{id}");
    let history_uri = format!("{profile_uri}/status-history");
    for outsider in [&passenger, &driver] {
        for uri in [&profile_uri, &history_uri] {
            let response = call(&app, As::User(outsider), GET, uri, None).await;
            assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found", "{uri}");
            let body = String::from_utf8_lossy(&response.body).into_owned();
            assert!(!body.contains(ID_CARD) && !body.contains("driver_id_card"));
        }
        let list = call(&app, As::User(outsider), GET, "/api/v1/drivers", None).await;
        assert_eq!(list.problem(StatusCode::FORBIDDEN), "forbidden");
    }
    // The other applicant cannot see this profile either.
    let second_owner: Uuid = second["user"]["id"].as_str().unwrap().parse().unwrap();
    assert_ne!(second_owner, account.id);
    for uri in [&profile_uri, &history_uri, &"/api/v1/drivers".to_owned()] {
        let response = call(&app, As::Anonymous, GET, uri, None).await;
        assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "authentication_required");
        let response = call(&app, As::Key(&key), GET, uri, None).await;
        assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
    }
    let unknown = format!("/api/v1/drivers/{}", Uuid::now_v7());
    let response = call(&app, As::User(&admin), GET, &unknown, None).await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
    let response = call(&app, As::User(&admin), GET, "/api/v1/drivers/not-a-uuid", None).await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");

    // Reviewers see everything, documents included.
    let seen = ok(&app, As::User(&admin), GET, &profile_uri, None).await;
    assert_eq!(seen["id_card_number"], ID_CARD);
    let url = seen["id_card_photo_url"].as_str().unwrap();
    assert_eq!(app.download(url).await, (StatusCode::OK, PNG.to_vec()));
    call(&app, As::User(&admin), GET, &history_uri, None).await.expect(StatusCode::OK);
    let invalid = [
        ("limit=0", ("limit", "out_of_range")),
        ("limit=101", ("limit", "out_of_range")),
        ("cursor=garbage", ("cursor", "invalid_format")),
        ("since=2026", ("since", "unknown_field")),
    ];
    for (query, expected) in invalid {
        let uri = format!("{history_uri}?{query}");
        let response = call(&app, As::User(&admin), GET, &uri, None).await;
        assert_eq!(errors(&response), pairs(&[expected]), "{query}");
    }
}

#[tokio::test]
async fn reviews_need_driver_review_and_an_existing_profile() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let key = app.api_key(&admin, &["catalog:read"]).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let driver = app.account(Role::Driver).await;
    for verb in ["approve", "reject", "suspend", "reinstate"] {
        let reason = matches!(verb, "reject" | "suspend").then_some("x");
        let anonymous = review(&app, As::Anonymous, id, verb, reason).await;
        assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
        for caller in [As::User(&account), As::User(&driver), As::Key(&key)] {
            let response = review(&app, caller, id, verb, reason).await;
            assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden", "{verb}");
        }
        let unknown = review(&app, As::User(&admin), Uuid::now_v7(), verb, reason).await;
        assert_eq!(unknown.problem(StatusCode::NOT_FOUND), "not_found");
    }
    let malformed = call(&app, As::User(&admin), POST, "/api/v1/drivers/x/approve", None).await;
    assert_eq!(malformed.problem(StatusCode::NOT_FOUND), "not_found");

    // An applicant promoted to administrator meanwhile cannot approve themself.
    sqlx::query("UPDATE users SET role = 'admin' WHERE id = $1")
        .bind(account.id)
        .execute(app.pool())
        .await
        .unwrap();
    let promoted = app.login(&account.email).await;
    let response = review(&app, As::User(&promoted), id, "approve", None).await;
    assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
    let current = call(&app, As::User(&admin), GET, &format!("/api/v1/drivers/{id}"), None).await;
    assert_eq!(current.expect(StatusCode::OK).json()["status"], "pending");
}

#[tokio::test]
async fn reviewers_list_profiles_with_filters_and_pagination() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (first, a) = applicant(&app, ID_CARD, "L-1").await;
    let (_, b) = applicant(&app, OTHER_ID_CARD, "L-2").await;
    let (_, c) = applicant(&app, "309850123456789012", "L-3").await;
    review(&app, As::User(&admin), id_of(&a), "approve", None).await.expect(StatusCode::OK);
    let available = Some(json!({ "is_available": true }));
    ok(&app, As::User(&first), PUT, "/api/v1/drivers/me/availability", available).await;
    review(&app, As::User(&admin), id_of(&b), "reject", Some("Non")).await.expect(StatusCode::OK);

    let list = |query: &'static str| {
        let app = &app;
        let admin = &admin;
        async move {
            let uri = format!("/api/v1/drivers{query}");
            let page = ok(app, As::User(admin), GET, &uri, None).await;
            let ids: Vec<Uuid> = page["items"].as_array().unwrap().iter().map(id_of).collect();
            (ids, page["next_cursor"].clone())
        }
    };
    let (all, _) = list("").await;
    assert_eq!(all, vec![id_of(&c), id_of(&b), id_of(&a)], "newest first");
    assert_eq!(list("?status=approved").await.0, vec![id_of(&a)]);
    assert_eq!(list("?status=rejected").await.0, vec![id_of(&b)]);
    assert_eq!(list("?status=pending&is_available=false").await.0, vec![id_of(&c)]);
    assert_eq!(list("?is_available=true").await.0, vec![id_of(&a)]);
    let (page, cursor) = list("?limit=2").await;
    assert_eq!(page, vec![id_of(&c), id_of(&b)]);
    let uri = format!("/api/v1/drivers?limit=2&cursor={}", cursor.as_str().unwrap());
    let rest = call(&app, As::User(&admin), GET, &uri, None).await.expect(StatusCode::OK).json();
    let rest_ids: Vec<Uuid> = rest["items"].as_array().unwrap().iter().map(id_of).collect();
    assert_eq!(rest_ids, vec![id_of(&a)]);
    assert_eq!(rest["next_cursor"], Value::Null);

    let bad = call(&app, As::User(&admin), GET, "/api/v1/drivers?status=active", None).await;
    assert_eq!(bad.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    let unknown = call(&app, As::User(&admin), GET, "/api/v1/drivers?role=driver", None).await;
    assert_eq!(errors(&unknown), pairs(&[("role", "unknown_field")]));
    let limit = call(&app, As::User(&admin), GET, "/api/v1/drivers?limit=0", None).await;
    assert_eq!(errors(&limit), pairs(&[("limit", "out_of_range")]));
}

#[tokio::test]
async fn concurrent_reviews_apply_exactly_once() {
    let app = TestApp::spawn().await;
    let first = app.account(Role::Admin).await;
    let second = app.account(Role::Admin).await;
    let (_, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    let responses = join_all([
        review(&app, As::User(&first), id, "approve", None),
        review(&app, As::User(&second), id, "reject", Some("Non")),
    ])
    .await;
    let mut statuses: Vec<StatusCode> = responses.iter().map(|r| r.status).collect();
    statuses.sort();
    assert_eq!(statuses, [StatusCode::OK, StatusCode::CONFLICT]);
    let loser = responses.iter().find(|r| r.status == StatusCode::CONFLICT).unwrap();
    assert_eq!(loser.problem(StatusCode::CONFLICT), "invalid_transition");
    let history = steps(&app, &first, id).await;
    assert_eq!(history.len(), 2, "one review recorded");
    assert_eq!(audit_actions(&app, id).await.len(), 1);
}

#[tokio::test]
async fn reapplying_notifies_the_reviewers_again() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    review(&app, As::User(&admin), id, "reject", Some("Scan flou")).await.expect(StatusCode::OK);
    assert_eq!(app.run_jobs().await, 3, "application (2 jobs) then rejection");
    let to_driver: Vec<_> = app.sent_mail().into_iter().filter(|m| m.to == account.email).collect();
    // The application e-mail is dropped (overtaken by the rejection); the rejection explains.
    assert_eq!(to_driver.len(), 1);
    assert!(to_driver[0].text_body.contains("Scan flou"));
    let reviewers_before = app.sent_mail().iter().filter(|m| m.to == admin.email).count();
    assert_eq!(reviewers_before, 0, "reviewed before the job ran: nobody bothered");

    reapply(&app, &account).await.expect(StatusCode::OK);
    assert_eq!(queued_jobs(&app).await, ["driver_status_changed", "driver_review_requested"]);
    assert_eq!(app.run_jobs().await, 2);
    assert_eq!(app.sent_mail().iter().filter(|m| m.to == admin.email).count(), 1);
    let none = app.account(Role::Passenger).await;
    let response = reapply(&app, &none).await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
}

#[tokio::test]
async fn a_running_review_request_does_not_swallow_a_new_one() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (account, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    review(&app, As::User(&admin), id, "reject", Some("Scan flou")).await.expect(StatusCode::OK);
    // A worker claimed the application's request and read `rejected`: it is dropping it.
    sqlx::query(
        "UPDATE jobs SET status = 'running', attempts = 1, locked_by = 'slow-worker',
         locked_until = now() + interval '5 minutes'
         WHERE kind = 'driver_review_requested'",
    )
    .execute(app.pool())
    .await
    .unwrap();

    // Re-applying meanwhile queues a request of its own; so does a change of documents.
    reapply(&app, &account).await.expect(StatusCode::OK);
    let patch = Some(json!({ "id_card_number": OTHER_ID_CARD }));
    ok(&app, As::User(&account), PATCH, "/api/v1/drivers/me", patch).await;
    let requests: Vec<String> = sqlx::query_scalar(
        "SELECT status FROM jobs WHERE kind = 'driver_review_requested' ORDER BY created_at, id",
    )
    .fetch_all(app.pool())
    .await
    .unwrap();
    assert_eq!(requests, ["running", "queued", "queued"]);

    // The running job finishes on its drop path; the queued ones reach the reviewer.
    sqlx::query(
        "UPDATE jobs SET status = 'succeeded', finished_at = now(), locked_by = NULL,
         locked_until = NULL WHERE status = 'running'",
    )
    .execute(app.pool())
    .await
    .unwrap();
    app.run_jobs().await;
    assert_eq!(app.sent_mail().iter().filter(|m| m.to == admin.email).count(), 2);
}

#[tokio::test]
async fn without_storage_applications_are_unavailable() {
    let app = TestApp::builder().configure(|s| s.storage.endpoint = None).build().await;
    let account = app.account(Role::Passenger).await;
    let body = json!({
        "phone_number": "0555123456",
        "id_card_number": ID_CARD,
        "id_card_photo_upload_id": Uuid::now_v7(),
        "driver_license_number": "L-1",
        "driver_license_photo_upload_id": Uuid::now_v7(),
        "years_of_experience": 1,
    });
    let response = apply(&app, &account, body).await;
    assert_eq!(response.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
}

#[tokio::test]
async fn the_status_history_is_append_only_and_constrained() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let (_, profile) = applicant(&app, ID_CARD, "L-1").await;
    let id = id_of(&profile);
    review(&app, As::User(&admin), id, "approve", None).await.expect(StatusCode::OK);

    for statement in [
        "UPDATE driver_status_log SET reason = 'edited'",
        "DELETE FROM driver_status_log",
        "TRUNCATE driver_status_log",
    ] {
        let error = sqlx::query(statement).execute(app.pool()).await.unwrap_err();
        assert!(error.to_string().contains("append-only"), "{statement}: {error}");
    }
    // Only real, explained changes can be recorded.
    let insert = |from: Option<&'static str>, to: &'static str, reason: &'static str| {
        sqlx::query(
            "INSERT INTO driver_status_log (id, driver_id, from_status, to_status, reason,
                                            created_at)
             VALUES ($1, $2, $3, $4, $5, now())",
        )
        .bind(Uuid::now_v7())
        .bind(id)
        .bind(from)
        .bind(to)
        .bind(reason)
        .execute(app.pool())
    };
    let constraint = |error: sqlx::Error| match error {
        sqlx::Error::Database(db) => db.constraint().map(str::to_owned),
        other => panic!("unexpected error {other}"),
    };
    let same = insert(Some("pending"), "pending", "").await.unwrap_err();
    assert_eq!(constraint(same).as_deref(), Some("driver_status_log_changes_status"));
    let unexplained = insert(Some("approved"), "suspended", " ").await.unwrap_err();
    assert_eq!(constraint(unexplained).as_deref(), Some("driver_status_log_reason_required"));
    // Only approved drivers can be available.
    let available = "UPDATE drivers SET is_available = true, status = 'pending' WHERE id = $1";
    let error = sqlx::query(available)
        .bind(id)
        .execute(app.pool())
        .await
        .unwrap_err();
    assert_eq!(constraint(error).as_deref(), Some("drivers_available_only_when_approved"));

    // Deleting a reviewer's account keeps the history and forgets the author.
    let delete = sqlx::query("DELETE FROM users WHERE id = $1").bind(admin.id);
    delete.execute(app.pool()).await.unwrap();
    let authors: Vec<Option<Uuid>> = sqlx::query_scalar(
        "SELECT changed_by FROM driver_status_log WHERE driver_id = $1 ORDER BY created_at",
    )
    .bind(id)
    .fetch_all(app.pool())
    .await
    .unwrap();
    assert_eq!(authors.len(), 2);
    assert!(authors[0].is_some() && authors[1].is_none());
}
