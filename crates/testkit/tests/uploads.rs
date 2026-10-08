//! Presigned uploads, claims and avatars against real PostgreSQL and S3 (RustFS): permissions,
//! validation, the end-to-end upload flow, claim failures, the outbox deletion job, the purge
//! of expired uploads and the storage-less mode.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::BTreeMap;
use std::time::Duration;

use axum::http::StatusCode;
use dz_app::jobs::Job;
use dz_app::ports::{
    ClaimedUpload, EnqueueOutcome, JobOptions, JobQueue, ObjectStorage, UserRepository,
    WriteEffects,
};
use dz_app::AppError;
use dz_app::uploads::PRESIGNED_CLOCK_SKEW;
use dz_domain::ConflictKind;
use dz_domain::ids::{UploadId, UserId};
use dz_domain::user::Role;
use dz_testkit::{Account, TestApp, TestResponse};
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

fn declare(purpose: &str, content_type: &str, size: u64) -> Value {
    json!({ "purpose": purpose, "content_type": content_type, "size_bytes": size })
}

async fn request_upload(app: &TestApp, account: &Account, body: &Value) -> TestResponse {
    app.post("/api/v1/uploads").bearer(&account.access_token).json(body).send().await
}

/// `(field, code)` of the first field error of a problem document.
fn first_error(response: &TestResponse) -> (String, String) {
    let error = &response.json()["errors"][0];
    let text = |v: &Value| v.as_str().unwrap_or_default().to_owned();
    (text(&error["field"]), text(&error["code"]))
}

async fn object_key(app: &TestApp, id: Uuid) -> String {
    sqlx::query_scalar("SELECT object_key FROM uploads WHERE id = $1")
        .bind(id)
        .fetch_one(app.pool())
        .await
        .unwrap()
}

/// What a successful claim would return (to drive the repository directly).
async fn as_claimed(app: &TestApp, id: Uuid) -> ClaimedUpload {
    ClaimedUpload { id: UploadId::from_uuid(id), object_key: object_key(app, id).await }
}

async fn exists(app: &TestApp, key: &str) -> bool {
    app.storage().unwrap().head(key).await.unwrap().is_some()
}

async fn set_avatar(app: &TestApp, account: &Account, upload_id: Uuid) -> TestResponse {
    app.put("/api/v1/me/avatar")
        .bearer(&account.access_token)
        .json(&json!({ "upload_id": upload_id }))
        .send()
        .await
}

/// Asserts a 422 on `upload_id` with code `invalid_upload`.
#[track_caller]
fn assert_invalid_upload(response: &TestResponse) {
    assert_eq!(response.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(first_error(response), ("upload_id".into(), "invalid_upload".into()));
}

#[tokio::test]
async fn uploads_are_presigned_per_purpose_and_permission() {
    let app = TestApp::spawn().await;
    let passenger = app.account(Role::Passenger).await;
    let driver = app.account(Role::Driver).await;
    let admin = app.account(Role::Admin).await;

    let allowed = [
        (&passenger, "avatar", "image/png"),
        (&passenger, "driver_id_card", "application/pdf"),
        (&passenger, "driver_license", "image/jpeg"),
        (&driver, "avatar", "image/webp"),
        (&driver, "driver_license", "application/pdf"),
        (&driver, "bus_photo", "image/jpeg"),
        (&admin, "bus_photo", "image/png"),
        (&admin, "stop_photo", "image/webp"),
    ];
    for (account, purpose, content_type) in allowed {
        let response =
            request_upload(&app, account, &declare(purpose, content_type, 1000)).await;
        let response = response.expect(StatusCode::CREATED);
        assert_eq!(response.header("cache-control"), Some("no-store"), "{purpose}");
        let body = response.json();
        let id: Uuid = body["id"].as_str().unwrap().parse().unwrap();
        let location = format!("/api/v1/uploads/{id}");
        assert_eq!(response.header("location"), Some(location.as_str()), "{purpose}");
        assert_eq!(body["purpose"], purpose);
        assert_eq!(body["content_type"], content_type);
        assert_eq!(body["size_bytes"], 1000);
        assert_eq!(body["upload"]["method"], "PUT");
        assert_eq!(body["upload"]["headers"]["content-type"], content_type);
        assert_eq!(body["upload"]["headers"]["content-length"], "1000");
        let key = object_key(&app, id).await;
        assert_eq!(key, format!("{purpose}/{id}"), "server-generated key");
        assert!(!key.contains(&account.id.to_string()), "keys never reveal the uploader");
        let url = body["upload"]["url"].as_str().unwrap();
        assert!(url.contains(&key) && url.contains("X-Amz-Signature="), "{url}");
        let expires_at: chrono::DateTime<chrono::Utc> =
            serde_json::from_value(body["expires_at"].clone()).unwrap();
        let ttl = expires_at - chrono::Utc::now();
        assert!(ttl > chrono::Duration::seconds(890) && ttl <= chrono::Duration::seconds(900));
    }

    let denied = [
        (&passenger, "bus_photo"),
        (&passenger, "stop_photo"),
        (&driver, "stop_photo"),
        (&admin, "driver_id_card"),
        (&admin, "driver_license"),
    ];
    for (account, purpose) in denied {
        let response = request_upload(&app, account, &declare(purpose, "image/png", 10)).await;
        assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden", "{purpose}");
    }
}

#[tokio::test]
async fn upload_declarations_are_validated() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;

    let cases = [
        (declare("avatar", "application/pdf", 10), "content_type", "invalid_choice"),
        (declare("avatar", "image/svg+xml", 10), "content_type", "invalid_choice"),
        (declare("avatar", "image/png", 2 * 1024 * 1024 + 1), "size_bytes", "out_of_range"),
        (declare("driver_id_card", "image/png", (10 << 20) + 1), "size_bytes", "out_of_range"),
        (declare("avatar", "image/png", 0), "size_bytes", "out_of_range"),
        (declare("selfie", "image/png", 10), "purpose", "invalid_format"),
        (declare("avatar", "", 10), "content_type", "too_short"),
        (json!({ "purpose": "avatar", "content_type": "image/png" }), "size_bytes", "required"),
        (
            json!({ "purpose": "avatar", "content_type": "image/png", "size_bytes": -1 }),
            "size_bytes",
            "invalid_format",
        ),
        (
            json!({ "purpose": "avatar", "content_type": "image/png", "size_bytes": 1, "etag": 1 }),
            "etag",
            "unknown_field",
        ),
    ];
    for (body, field, code) in cases {
        let response = request_upload(&app, &account, &body).await;
        let problem = response.problem(StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(problem, "validation_error", "{body}");
        assert_eq!(first_error(&response), (field.to_owned(), code.to_owned()), "{body}");
    }
    let limits = request_upload(&app, &account, &declare("avatar", "image/png", 3 << 20)).await;
    assert_eq!(limits.json()["errors"][0]["params"], json!({ "min": 1, "max": 2 * 1024 * 1024 }));
    let count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM uploads").fetch_one(app.pool()).await.unwrap();
    assert_eq!(count, 0, "nothing is recorded for invalid declarations");
}

#[tokio::test]
async fn uploads_need_a_signed_in_human() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let key = app.api_key(&admin, &["stop:write", "bus:read"]).await;
    let body = declare("stop_photo", "image/png", 10);

    let anonymous = app.post("/api/v1/uploads").json(&body).send().await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let service = app.post("/api/v1/uploads").api_key(&key).json(&body).send().await;
    assert_eq!(service.problem(StatusCode::FORBIDDEN), "forbidden");

    let attach = json!({ "upload_id": Uuid::now_v7() });
    let anonymous = app.put("/api/v1/me/avatar").json(&attach).send().await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let service = app.put("/api/v1/me/avatar").api_key(&key).json(&attach).send().await;
    assert_eq!(service.problem(StatusCode::FORBIDDEN), "forbidden");
    let anonymous = app.delete("/api/v1/me/avatar").send().await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let service = app.delete("/api/v1/me/avatar").api_key(&key).send().await;
    assert_eq!(service.problem(StatusCode::FORBIDDEN), "forbidden");
}

#[tokio::test]
async fn presigned_uploads_only_accept_the_declared_file() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let created = request_upload(&app, &account, &declare("avatar", "image/png", PNG.len() as u64))
        .await
        .expect(StatusCode::CREATED)
        .json();
    let id: Uuid = created["id"].as_str().unwrap().parse().unwrap();
    let key = object_key(&app, id).await;

    // Another type than the signed one.
    let mut other_type = created["upload"].clone();
    other_type["headers"]["content-type"] = json!("image/jpeg");
    assert!(app.send_presigned(&other_type, PNG.to_vec()).await.is_client_error());
    // A bigger file than declared.
    let bigger = [PNG, PNG].concat();
    let mut other_size = created["upload"].clone();
    other_size["headers"]["content-length"] = json!(bigger.len().to_string());
    assert!(app.send_presigned(&other_size, bigger).await.is_client_error());
    assert!(!exists(&app, &key).await);

    assert!(app.send_presigned(&created["upload"], PNG.to_vec()).await.is_success());
    assert!(exists(&app, &key).await);
    // Provisioning the bucket again is a no-op (`dz-cli storage create-bucket`).
    assert!(!app.storage().unwrap().create_bucket().await.unwrap());
}

#[tokio::test]
async fn avatars_are_attached_end_to_end() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let profile = app.get("/api/v1/me/profile").bearer(&account.access_token).send().await;
    assert_eq!(profile.expect(StatusCode::OK).json()["avatar_url"], Value::Null);

    let upload_id = app.upload(&account, "avatar", "image/png", PNG).await;
    let key = object_key(&app, upload_id).await;
    let info = app.storage().unwrap().head(&key).await.unwrap().expect("object stored in S3");
    assert_eq!(info.size_bytes, PNG.len() as u64);
    assert_eq!(info.content_type.as_deref(), Some("image/png"));

    let profile = set_avatar(&app, &account, upload_id).await.expect(StatusCode::OK).json();
    let avatar_url = profile["avatar_url"].as_str().expect("avatar_url").to_owned();
    assert!(avatar_url.contains(&key), "{avatar_url}");
    let (status, bytes) = app.download(&avatar_url).await;
    assert_eq!((status, bytes.as_slice()), (StatusCode::OK, PNG));

    // The same URL everywhere within the hour (stable ETags).
    let me = app.get("/api/v1/me").bearer(&account.access_token).send().await;
    assert_eq!(me.expect(StatusCode::OK).json()["profile"]["avatar_url"], avatar_url.as_str());
    let profile = app.get("/api/v1/me/profile").bearer(&account.access_token).send().await;
    assert_eq!(profile.expect(StatusCode::OK).json()["avatar_url"], avatar_url.as_str());

    let status: String = sqlx::query_scalar("SELECT status FROM uploads WHERE id = $1")
        .bind(upload_id)
        .fetch_one(app.pool())
        .await
        .unwrap();
    assert_eq!(status, "attached");
    // Nothing was replaced: no deletion job.
    assert_eq!(deletion_jobs(&app).await, Vec::<String>::new());
}

async fn deletion_jobs(app: &TestApp) -> Vec<String> {
    sqlx::query_scalar(
        "SELECT payload -> 'payload' ->> 'key' FROM jobs
         WHERE kind = 'storage_delete_object' AND status = 'queued' ORDER BY created_at",
    )
    .fetch_all(app.pool())
    .await
    .unwrap()
}

/// Makes the queued deletion jobs due, as if the presigned upload URLs had expired.
async fn make_deletions_due(app: &TestApp) -> u64 {
    sqlx::query(
        "UPDATE jobs SET run_at = now()
         WHERE kind = 'storage_delete_object' AND status = 'queued'",
    )
    .execute(app.pool())
    .await
    .unwrap()
    .rows_affected()
}

#[tokio::test]
async fn replacing_and_removing_the_avatar_deletes_old_objects_through_the_outbox() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Driver).await;
    let first = app.upload(&account, "avatar", "image/png", PNG).await;
    set_avatar(&app, &account, first).await.expect(StatusCode::OK);
    let first_key = object_key(&app, first).await;

    let second = app.upload(&account, "avatar", "image/webp", b"RIFF....WEBPVP8 ").await;
    let profile = set_avatar(&app, &account, second).await.expect(StatusCode::OK).json();
    let second_key = object_key(&app, second).await;
    assert!(profile["avatar_url"].as_str().unwrap().contains(&second_key));
    assert_eq!(deletion_jobs(&app).await, vec![first_key.clone()]);
    // Not before the presigned URL of the old object has expired.
    assert_eq!(app.run_jobs().await, 0);
    assert!(exists(&app, &first_key).await, "deleted after the commit, by the worker");

    assert_eq!(make_deletions_due(&app).await, 1);
    assert_eq!(app.run_jobs().await, 1);
    assert!(!exists(&app, &first_key).await);
    assert!(exists(&app, &second_key).await);

    let removed = app.delete("/api/v1/me/avatar").bearer(&account.access_token).send().await;
    removed.expect(StatusCode::NO_CONTENT);
    let profile = app.get("/api/v1/me/profile").bearer(&account.access_token).send().await;
    assert_eq!(profile.expect(StatusCode::OK).json()["avatar_url"], Value::Null);
    assert_eq!(deletion_jobs(&app).await, vec![second_key.clone()]);
    make_deletions_due(&app).await;
    assert_eq!(app.run_jobs().await, 1);
    assert!(!exists(&app, &second_key).await);

    // Idempotent: nothing left to delete.
    let again = app.delete("/api/v1/me/avatar").bearer(&account.access_token).send().await;
    again.expect(StatusCode::NO_CONTENT);
    assert_eq!(deletion_jobs(&app).await, Vec::<String>::new());
}

#[tokio::test]
async fn removed_objects_are_deleted_after_their_upload_url_expired() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let declared = declare("avatar", "image/png", PNG.len() as u64);
    let created = request_upload(&app, &account, &declared).await.expect(StatusCode::CREATED);
    let created = created.json();
    let id: Uuid = created["id"].as_str().unwrap().parse().unwrap();
    let key = object_key(&app, id).await;
    assert!(app.send_presigned(&created["upload"], PNG.to_vec()).await.is_success());
    set_avatar(&app, &account, id).await.expect(StatusCode::OK);
    let removed = app.delete("/api/v1/me/avatar").bearer(&account.access_token).send().await;
    removed.expect(StatusCode::NO_CONTENT);

    // The deletion waits for the expiry of the presigned URL (plus the clock-skew margin)...
    let (run_at, expires_at): (chrono::DateTime<chrono::Utc>, chrono::DateTime<chrono::Utc>) =
        sqlx::query_as(
            "SELECT j.run_at, u.expires_at
             FROM jobs j JOIN uploads u ON u.object_key = j.payload -> 'payload' ->> 'key'
             WHERE j.kind = 'storage_delete_object' AND u.id = $1",
        )
        .bind(id)
        .fetch_one(app.pool())
        .await
        .unwrap();
    assert_eq!(run_at - expires_at, chrono::Duration::from_std(PRESIGNED_CLOCK_SKEW).unwrap());
    assert_eq!(app.run_jobs().await, 0, "not due while the URL is valid");

    // ...so that the object the client may still upload with it is deleted too.
    assert!(app.send_presigned(&created["upload"], PNG.to_vec()).await.is_success());
    assert!(exists(&app, &key).await);
    assert_eq!(make_deletions_due(&app).await, 1);
    assert_eq!(app.run_jobs().await, 1);
    assert!(!exists(&app, &key).await);
    assert_eq!(deletion_jobs(&app).await, Vec::<String>::new());
}

#[tokio::test]
async fn claims_refuse_unusable_uploads() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let other = app.account(Role::Passenger).await;

    // Unknown and malformed ids.
    assert_invalid_upload(&set_avatar(&app, &account, Uuid::now_v7()).await);
    let malformed = app
        .put("/api/v1/me/avatar")
        .bearer(&account.access_token)
        .json(&json!({ "upload_id": "not-a-uuid" }))
        .send()
        .await;
    assert_eq!(malformed.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(malformed.json()["errors"][0]["field"], "upload_id");
    let unknown = app
        .put("/api/v1/me/avatar")
        .bearer(&account.access_token)
        .json(&json!({ "upload_id": Uuid::now_v7(), "avatar_key": "x" }))
        .send()
        .await;
    assert_eq!(unknown.problem(StatusCode::UNPROCESSABLE_ENTITY), "validation_error");
    assert_eq!(first_error(&unknown), ("avatar_key".into(), "unknown_field".into()));

    // Someone else's upload.
    let theirs = app.upload(&other, "avatar", "image/png", PNG).await;
    assert_invalid_upload(&set_avatar(&app, &account, theirs).await);

    // Another purpose.
    let document = app.upload(&account, "driver_id_card", "image/png", PNG).await;
    assert_invalid_upload(&set_avatar(&app, &account, document).await);

    // Declared but never uploaded.
    let missing = request_upload(&app, &account, &declare("avatar", "image/png", 10))
        .await
        .expect(StatusCode::CREATED)
        .json();
    let missing: Uuid = missing["id"].as_str().unwrap().parse().unwrap();
    assert_invalid_upload(&set_avatar(&app, &account, missing).await);

    // Expired.
    let expired = app.upload(&account, "avatar", "image/png", PNG).await;
    sqlx::query(
        "UPDATE uploads
         SET created_at = now() - interval '1 hour', expires_at = now() - interval '1 second'
         WHERE id = $1",
    )
    .bind(expired)
    .execute(app.pool())
    .await
    .unwrap();
    assert_invalid_upload(&set_avatar(&app, &account, expired).await);

    // An object that differs from the declaration (written behind the API's back) is refused
    // and deleted.
    let declared = request_upload(&app, &account, &declare("avatar", "image/png", 10))
        .await
        .expect(StatusCode::CREATED)
        .json();
    let mismatch: Uuid = declared["id"].as_str().unwrap().parse().unwrap();
    let key = object_key(&app, mismatch).await;
    let storage = app.storage().unwrap();
    let forged = storage.presign_put(&key, "image/png", PNG.len() as u64, Duration::from_secs(60));
    let headers: BTreeMap<_, _> = forged.headers.into_iter().collect();
    let forged = json!({ "method": forged.method, "url": forged.url, "headers": headers });
    assert!(app.send_presigned(&forged, PNG.to_vec()).await.is_success());
    assert!(exists(&app, &key).await);
    assert_invalid_upload(&set_avatar(&app, &account, mismatch).await);
    assert!(!exists(&app, &key).await, "mismatching object deleted");

    // Used twice: no longer pending.
    let used = app.upload(&account, "avatar", "image/png", PNG).await;
    set_avatar(&app, &account, used).await.expect(StatusCode::OK);
    assert_invalid_upload(&set_avatar(&app, &account, used).await);
}

#[tokio::test]
async fn a_concurrently_attached_upload_rolls_the_write_back() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let upload = app.upload(&account, "avatar", "image/png", PNG).await;
    let claimed = as_claimed(&app, upload).await;
    // Another request attached it between the claim and this write.
    sqlx::query("UPDATE uploads SET status = 'attached', attached_at = now() WHERE id = $1")
        .bind(upload)
        .execute(app.pool())
        .await
        .unwrap();
    let never = Job::StorageDeleteObject { key: "avatar/never".into() };
    let effects = WriteEffects::default().with_job(never);
    let user = UserId::from_uuid(account.id);
    let now = chrono::Utc::now();
    let result = app.infra.store.set_avatar(user, Some(&claimed), None, now, effects).await;
    assert!(matches!(result, Err(AppError::Conflict(ConflictKind::UploadAlreadyUsed))));

    // Nothing of the write survived: no avatar, no outbox job.
    let profile = app.get("/api/v1/me/profile").bearer(&account.access_token).send().await;
    assert_eq!(profile.expect(StatusCode::OK).json()["avatar_url"], Value::Null);
    assert_eq!(deletion_jobs(&app).await, Vec::<String>::new());

    // A stale expectation (the avatar changed meanwhile) is a conflict too.
    let fresh = app.upload(&account, "avatar", "image/png", PNG).await;
    let claimed = as_claimed(&app, fresh).await;
    let stale = app
        .infra
        .store
        .set_avatar(user, Some(&claimed), Some("avatar/previous"), now, WriteEffects::default())
        .await;
    assert!(matches!(stale, Err(AppError::Conflict(ConflictKind::StaleState))));
}

#[tokio::test]
async fn outbox_jobs_commit_with_the_write_and_follow_the_dedup_rule() {
    let app = TestApp::spawn().await;
    let effects = WriteEffects::default().with_job_options(
        Job::PurgeExpiredUploads,
        JobOptions { dedup_key: Some("outbox-test".into()), ..JobOptions::default() },
    );
    let mut tx = app.pool().begin().await.unwrap();
    dz_infra::pg::effects::persist(&mut tx, &effects).await.unwrap();
    tx.rollback().await.unwrap();
    let count = || async {
        sqlx::query_scalar::<_, i64>("SELECT count(*) FROM jobs WHERE dedup_key = 'outbox-test'")
            .fetch_one(app.pool())
            .await
            .unwrap()
    };
    assert_eq!(count().await, 0, "rolled back with the write");

    for _ in 0..2 {
        let mut tx = app.pool().begin().await.unwrap();
        dz_infra::pg::effects::persist(&mut tx, &effects).await.unwrap();
        tx.commit().await.unwrap();
    }
    assert_eq!(count().await, 1, "a pending job with the same key is not duplicated");
    let options = effects.jobs[0].options.clone();
    let outcome = app.infra.queue.enqueue(&Job::PurgeExpiredUploads, options).await;
    assert_eq!(outcome.unwrap(), EnqueueOutcome::Duplicate, "same rule as the queue");
}

#[tokio::test]
async fn the_purge_job_deletes_expired_pending_uploads_and_their_objects() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let stale = app.upload(&account, "avatar", "image/png", PNG).await;
    let recent = app.upload(&account, "avatar", "image/png", PNG).await;
    let attached = app.upload(&account, "avatar", "image/png", PNG).await;
    let fresh = app.upload(&account, "avatar", "image/png", PNG).await;
    set_avatar(&app, &account, attached).await.expect(StatusCode::OK);
    let keys = [
        object_key(&app, stale).await,
        object_key(&app, recent).await,
        object_key(&app, attached).await,
        object_key(&app, fresh).await,
    ];
    // `stale` expired more than an hour ago; `recent` less than an hour ago; `attached` too, but
    // it is in use.
    for (id, expired_for) in [(stale, "2 hours"), (recent, "10 minutes"), (attached, "2 hours")] {
        sqlx::query(
            "UPDATE uploads SET created_at = now() - interval '1 day',
                                expires_at = now() - $2::interval
             WHERE id = $1",
        )
        .bind(id)
        .bind(expired_for)
        .execute(app.pool())
        .await
        .unwrap();
    }

    let enqueued = app.infra.queue.enqueue(&Job::PurgeExpiredUploads, JobOptions::default()).await;
    assert!(matches!(enqueued.unwrap(), EnqueueOutcome::Enqueued(_)));
    assert_eq!(app.run_jobs().await, 1);

    let remaining: Vec<Uuid> = sqlx::query_scalar("SELECT id FROM uploads ORDER BY id")
        .fetch_all(app.pool())
        .await
        .unwrap();
    let mut expected = vec![recent, attached, fresh];
    expected.sort();
    assert_eq!(remaining, expected);
    assert!(!exists(&app, &keys[0]).await, "the expired object is deleted");
    for key in &keys[1..] {
        assert!(exists(&app, key).await, "{key} is kept");
    }
}

#[tokio::test]
async fn without_storage_uploads_and_avatars_are_unavailable() {
    let app = TestApp::builder().configure(|s| s.storage.endpoint = None).build().await;
    assert!(app.storage().is_none());
    let account = app.account(Role::Passenger).await;

    let upload = request_upload(&app, &account, &declare("avatar", "image/png", 10)).await;
    assert_eq!(upload.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
    assert_eq!(upload.header("retry-after"), Some("5"));
    let attach = set_avatar(&app, &account, Uuid::now_v7()).await;
    assert_eq!(attach.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
    let remove = app.delete("/api/v1/me/avatar").bearer(&account.access_token).send().await;
    assert_eq!(remove.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
    let localized = request_upload(&app, &account, &declare("avatar", "image/png", 10)).await;
    assert_eq!(localized.json()["title"], "Stockage indisponible");

    // An avatar recorded while storage was available has no URL now.
    sqlx::query("UPDATE profiles SET avatar_key = 'avatar/old/key' WHERE user_id = $1")
        .bind(account.id)
        .execute(app.pool())
        .await
        .unwrap();
    let me = app.get("/api/v1/me").bearer(&account.access_token).send().await;
    assert_eq!(me.expect(StatusCode::OK).json()["profile"]["avatar_url"], Value::Null);
}

#[tokio::test]
async fn upload_urls_are_never_replayed_by_idempotency_keys() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let send = || {
        app.post("/api/v1/uploads")
            .bearer(&account.access_token)
            .header("idempotency-key", "upload-once-0001")
            .json(&declare("avatar", "image/png", 10))
            .send()
    };
    let first = send().await.expect(StatusCode::CREATED);
    let retry = send().await.expect(StatusCode::CREATED);
    assert_eq!(retry.header("idempotent-replayed"), None);
    assert_ne!(first.json()["id"], retry.json()["id"]);
}

#[tokio::test]
async fn uploads_and_users_repository_round_trip() {
    let app = TestApp::spawn().await;
    let account = app.account(Role::Passenger).await;
    let id = app.upload(&account, "avatar", "image/png", PNG).await;
    let store = &app.infra.store;
    let upload = dz_app::ports::UploadRepository::find(&**store, UploadId::from_uuid(id)).await;
    let upload = upload.unwrap().expect("stored upload");
    assert_eq!(upload.owner_id, UserId::from_uuid(account.id));
    assert_eq!(upload.size_bytes as usize, PNG.len());
    assert!(upload.expires_at > upload.created_at);
    let by_key = dz_app::ports::UploadRepository::find_by_key(&**store, &upload.object_key).await;
    assert_eq!(by_key.unwrap(), Some(upload.clone()));
    let unknown = dz_app::ports::UploadRepository::find_by_key(&**store, "avatar/unknown").await;
    assert_eq!(unknown.unwrap(), None);
    // Deleting is limited to pending uploads.
    sqlx::query("UPDATE uploads SET status = 'attached', attached_at = now() WHERE id = $1")
        .bind(id)
        .execute(app.pool())
        .await
        .unwrap();
    let deleted =
        dz_app::ports::UploadRepository::delete_pending(&**store, &[UploadId::from_uuid(id)]).await;
    assert_eq!(deleted.unwrap(), 0);
    // The schema keeps status and attachment time consistent.
    let inconsistent = sqlx::query("UPDATE uploads SET attached_at = NULL WHERE id = $1")
        .bind(id)
        .execute(app.pool())
        .await
        .unwrap_err();
    assert!(inconsistent.to_string().contains("uploads_attached_consistent"), "{inconsistent}");
}

#[tokio::test]
async fn owners_can_follow_their_uploads() {
    let app = TestApp::spawn().await;
    let owner = app.account(Role::Passenger).await;
    let stranger = app.account(Role::Passenger).await;
    let admin = app.account(Role::Admin).await;
    let key = app.api_key(&admin, &["stop:write"]).await;

    let created = request_upload(&app, &owner, &declare("avatar", "image/png", PNG.len() as u64))
        .await
        .expect(StatusCode::CREATED);
    let location = created.header("location").unwrap().to_owned();
    let id = created.json()["id"].as_str().unwrap().to_owned();
    assert_eq!(location, format!("/api/v1/uploads/{id}"));

    let pending = app.get(&location).bearer(&owner.access_token).send().await.expect(StatusCode::OK);
    let body = pending.json();
    assert_eq!(body["status"], "pending");
    assert_eq!(body["purpose"], "avatar");
    assert!(body.get("upload").is_none(), "the presigned request is never shown again");
    assert_eq!(body["attached_at"], Value::Null);

    // Upload and attach it: the status follows.
    let uploaded = app.upload(&owner, "avatar", "image/png", PNG).await;
    set_avatar(&app, &owner, uploaded).await.expect(StatusCode::OK);
    let attached = app
        .get(&format!("/api/v1/uploads/{uploaded}"))
        .bearer(&owner.access_token)
        .send()
        .await
        .expect(StatusCode::OK)
        .json();
    assert_eq!(attached["status"], "attached");
    assert!(attached["attached_at"].is_string());

    // Other people's uploads do not exist for them; API keys own no uploads.
    let response = app.get(&location).bearer(&stranger.access_token).send().await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
    let response = app.get(&location).api_key(&key).send().await;
    assert_eq!(response.problem(StatusCode::FORBIDDEN), "forbidden");
    let response = app.get(&location).send().await;
    assert_eq!(response.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let missing = format!("/api/v1/uploads/{}", Uuid::now_v7());
    let response = app.get(&missing).bearer(&owner.access_token).send().await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
}
