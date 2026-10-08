//! Network catalogue against real PostgreSQL/PostGIS and S3 (RustFS): stops (nearby and
//! trigram search, photos), lines, ordered line stops (atomic and concurrent re-ordering),
//! routes and schedules — permissions, validation, visibility of inactive rows, conflicts,
//! audit and the constraints behind them.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::HashSet;
use std::time::Duration;

use axum::http::{Method, StatusCode};
use dz_app::AppError;
use dz_app::network::ports::{SchedulePatch, ScheduleRepository, StopPatch, StopRepository};
use dz_app::ports::WriteEffects;
use dz_domain::geo::GeoPoint;
use dz_domain::ids::{ScheduleId, StopId};
use dz_domain::network::TimeOfDay;
use dz_domain::user::Role;
use dz_domain::{ConflictKind, Violation};
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

/// Places in Algiers `(lat, lng)`.
const MARTYRS: (f64, f64) = (36.7856, 3.0603);
const GRANDE_POSTE: (f64, f64) = (36.7731, 3.0588);
const TAFOURAH: (f64, f64) = (36.7725, 3.0607);
const BAB_EZZOUAR: (f64, f64) = (36.7207, 3.1838);
const BEN_AKNOUN: (f64, f64) = (36.7570, 3.0130);

const GET: Method = Method::GET;
const POST: Method = Method::POST;
const PUT: Method = Method::PUT;
const PATCH: Method = Method::PATCH;
const DELETE: Method = Method::DELETE;

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

/// Sends `method uri` as `caller`, with a JSON body when given.
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

/// The `items` of a successful list.
async fn items(app: &TestApp, caller: As<'_>, uri: &str) -> Value {
    let response = call(app, caller, GET, uri, None).await;
    response.expect(StatusCode::OK).json()["items"].clone()
}

/// The ids of the `items` of a successful anonymous list.
async fn listed(app: &TestApp, uri: String) -> Vec<Uuid> {
    ids(&items(app, As::Anonymous, &uri).await)
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

fn ids(items: &Value) -> Vec<Uuid> {
    items.as_array().unwrap().iter().map(id_of).collect()
}

/// One field of every item.
fn column(items: &Value, field: &str) -> Vec<Value> {
    items.as_array().unwrap().iter().map(|item| item[field].clone()).collect()
}

fn stop_order(items: &Value) -> Vec<Uuid> {
    items.as_array().unwrap().iter().map(|item| id_of(&item["stop"])).collect()
}

fn positions(items: &Value) -> Vec<u64> {
    column(items, "position").iter().map(|p| p.as_u64().unwrap()).collect()
}

/// Haversine distance between two places, in metres.
fn distance(a: (f64, f64), b: (f64, f64)) -> f64 {
    GeoPoint::from_trusted(a.0, a.1).haversine_m(GeoPoint::from_trusted(b.0, b.1))
}

/// Asserts a distance computed by PostGIS against the haversine distance.
#[track_caller]
fn assert_close(measured: &Value, expected: f64) {
    let measured = measured.as_f64().expect("a distance");
    assert!((measured - expected).abs() < 0.006 * expected + 1.0, "{measured} vs {expected}");
}

fn stop_body(name: &str, (lat, lng): (f64, f64)) -> Value {
    json!({ "name": name, "location": { "lat": lat, "lng": lng } })
}

async fn create_stop(app: &TestApp, admin: &Account, name: &str, at: (f64, f64)) -> Uuid {
    let body = stop_body(name, at);
    let response = call(app, As::User(admin), POST, "/api/v1/stops", Some(body)).await;
    id_of(&response.expect(StatusCode::CREATED).json())
}

async fn create_line(app: &TestApp, admin: &Account, code: &str) -> Uuid {
    let body = json!({ "code": code, "name": format!("Ligne {code}") });
    let response = call(app, As::User(admin), POST, "/api/v1/lines", Some(body)).await;
    id_of(&response.expect(StatusCode::CREATED).json())
}

/// A successful `PATCH` as `admin`.
async fn patch(app: &TestApp, admin: &Account, uri: &str, body: Value) -> Value {
    call(app, As::User(admin), PATCH, uri, Some(body)).await.expect(StatusCode::OK).json()
}

async fn put_stops(app: &TestApp, admin: &Account, line: Uuid, stops: Value) -> TestResponse {
    let uri = format!("/api/v1/lines/{line}/stops");
    call(app, As::User(admin), PUT, &uri, Some(json!({ "stops": stops }))).await
}

fn entries(stops: &[Uuid]) -> Value {
    stops.iter().map(|id| json!({ "stop_id": id })).collect()
}

async fn audit_actions(app: &TestApp, resource_type: &str) -> Vec<String> {
    sqlx::query_scalar(
        "SELECT action FROM audit_log WHERE resource_type = $1 ORDER BY occurred_at, id",
    )
    .bind(resource_type)
    .fetch_all(app.pool())
    .await
    .unwrap()
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

// --- Stops ---------------------------------------------------------------------------------------

#[tokio::test]
async fn stops_are_created_read_updated_and_deleted() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let body = json!({
        "name": "  Place des Martyrs ",
        "location": { "lat": MARTYRS.0, "lng": MARTYRS.1 },
        "address": "Rue Bab Azoun",
        "wilaya": "Alger",
        "commune": "Casbah",
        "features": ["Shelter", "bench"],
    });
    let response = call(&app, As::User(&admin), POST, "/api/v1/stops", Some(body)).await;
    let response = response.expect(StatusCode::CREATED);
    let created = response.json();
    let path = format!("/api/v1/stops/{}", id_of(&created));
    assert_eq!(response.header("location"), Some(path.as_str()));
    assert_eq!(created["name"], "Place des Martyrs");
    assert_eq!(created["location"], json!({ "lat": MARTYRS.0, "lng": MARTYRS.1 }));
    assert_eq!(created["features"], json!(["shelter", "bench"]));
    assert_eq!(created["is_active"], true);
    assert_eq!(created["photo_url"], Value::Null);
    assert_eq!(created["description"], "");

    let fetched = app.get(&path).send().await.expect(StatusCode::OK);
    assert!(fetched.header("etag").is_some());
    assert_eq!(fetched.json(), created, "public read");

    let changes = json!({
        "name": "Martyrs",
        "location": { "lat": 36.786, "lng": 3.061 },
        "address": "",
    });
    let updated = patch(&app, &admin, &path, changes).await;
    assert_eq!(updated["name"], "Martyrs");
    assert_eq!(updated["address"], "");
    assert_eq!(updated["location"], json!({ "lat": 36.786, "lng": 3.061 }));
    assert_eq!(updated["wilaya"], "Alger", "absent fields are unchanged");
    assert_ne!(updated["updated_at"], created["updated_at"]);

    let deleted = call(&app, As::User(&admin), DELETE, &path, None).await;
    deleted.expect(StatusCode::NO_CONTENT);
    assert_eq!(app.get(&path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    let again = call(&app, As::User(&admin), DELETE, &path, None).await;
    assert_eq!(again.problem(StatusCode::NOT_FOUND), "not_found");
    let malformed = app.get("/api/v1/stops/not-a-uuid").send().await;
    assert_eq!(malformed.problem(StatusCode::NOT_FOUND), "not_found");
    assert_eq!(audit_actions(&app, "stop").await, ["stop.create", "stop.update", "stop.delete"]);
}

#[tokio::test]
async fn stop_input_is_validated() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let id = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let origin = json!({ "lat": 0.0, "lng": 0.0 });
    let cases = [
        (
            json!({ "name": "", "location": { "lat": 90.5, "lng": -181.0 } }),
            vec![
                ("name", "required"),
                ("location.lat", "out_of_range"),
                ("location.lng", "out_of_range"),
            ],
        ),
        (json!({ "location": origin }), vec![("name", "required")]),
        (json!({ "name": "x" }), vec![("location", "required")]),
        (json!({ "name": "x", "location": { "lat": 1.0 } }), vec![("location.lng", "required")]),
        (
            json!({ "name": "x", "location": { "lat": 1.0, "lng": 1.0, "alt": 3 } }),
            vec![("location.alt", "unknown_field")],
        ),
        (
            json!({ "name": "x", "location": { "lat": "north", "lng": 1.0 } }),
            vec![("location.lat", "invalid_format")],
        ),
        (json!({ "name": "x".repeat(101), "location": origin }), vec![("name", "too_long")]),
        (
            json!({
                "name": "x",
                "location": origin,
                "features": ["ok", "OK", "not ok"],
                "address": "a".repeat(256),
            }),
            vec![
                ("address", "too_long"),
                ("features[1]", "duplicate"),
                ("features[2]", "invalid_format"),
            ],
        ),
        (
            json!({ "name": "x", "location": origin, "photo_key": "k" }),
            vec![("photo_key", "unknown_field")],
        ),
    ];
    for (body, expected) in cases {
        let response = call(&app, As::User(&admin), POST, "/api/v1/stops", Some(body.clone()));
        let response = response.await;
        assert_eq!(errors(&response), pairs(&expected), "{body}");
    }
    let path = format!("/api/v1/stops/{id}");
    let body = json!({ "name": " ", "features": vec!["x"; 21] });
    let response = call(&app, As::User(&admin), PATCH, &path, Some(body)).await;
    assert_eq!(errors(&response), pairs(&[("name", "required"), ("features", "out_of_range")]));
    let missing = format!("/api/v1/stops/{}", Uuid::now_v7());
    let body = json!({ "is_active": false });
    let response = call(&app, As::User(&admin), PATCH, &missing, Some(body)).await;
    assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found");
    assert_eq!(audit_actions(&app, "stop").await, ["stop.create"], "nothing invalid is audited");
}

#[tokio::test]
async fn stop_writes_need_stop_write() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let driver = app.account(Role::Driver).await;
    let writer = app.api_key(&admin, &["stop:write"]).await;
    let lines_only = app.api_key(&admin, &["line:write"]).await;
    let body = stop_body("Tafourah", TAFOURAH);
    let id = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let path = format!("/api/v1/stops/{id}");

    let denied = [
        (As::Anonymous, StatusCode::UNAUTHORIZED, "authentication_required"),
        (As::User(&passenger), StatusCode::FORBIDDEN, "forbidden"),
        (As::User(&driver), StatusCode::FORBIDDEN, "forbidden"),
        (As::Key(&lines_only), StatusCode::FORBIDDEN, "forbidden"),
    ];
    for (caller, status, code) in denied {
        let create = call(&app, caller, POST, "/api/v1/stops", Some(body.clone())).await;
        assert_eq!(create.problem(status), code);
        let update = call(&app, caller, PATCH, &path, Some(json!({ "name": "x" }))).await;
        assert_eq!(update.problem(status), code);
        let delete = call(&app, caller, DELETE, &path, None).await;
        assert_eq!(delete.problem(status), code);
    }

    let key = As::Key(&writer);
    let created = call(&app, key, POST, "/api/v1/stops", Some(body)).await;
    let created = id_of(&created.expect(StatusCode::CREATED).json());
    let path = format!("/api/v1/stops/{created}");
    call(&app, key, PATCH, &path, Some(json!({ "name": "T" }))).await.expect(StatusCode::OK);
    call(&app, key, DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
    let actors: Vec<String> = sqlx::query_scalar(
        "SELECT DISTINCT actor_type FROM audit_log
         WHERE resource_type = 'stop' AND resource_id = $1",
    )
    .bind(created.to_string())
    .fetch_all(app.pool())
    .await
    .unwrap();
    assert_eq!(actors, ["service"], "API key writes are audited as the key");
}

#[tokio::test]
async fn inactive_stops_are_visible_to_stop_writers_only() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let writer = app.api_key(&admin, &["stop:write"]).await;
    let reader = app.api_key(&admin, &["catalog:read"]).await;
    let active = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let hidden = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    patch(&app, &admin, &format!("/api/v1/stops/{hidden}"), json!({ "is_active": false })).await;
    let hidden_path = format!("/api/v1/stops/{hidden}");
    let hidden_lines = format!("/api/v1/stops/{hidden}/lines");

    for caller in [As::Anonymous, As::User(&passenger), As::Key(&reader)] {
        assert_eq!(ids(&items(&app, caller, "/api/v1/stops").await), vec![active]);
        let one = call(&app, caller, GET, &hidden_path, None).await;
        assert_eq!(one.problem(StatusCode::NOT_FOUND), "not_found");
        let lines = call(&app, caller, GET, &hidden_lines, None).await;
        assert_eq!(lines.problem(StatusCode::NOT_FOUND), "not_found");
    }
    for caller in [As::User(&admin), As::Key(&writer)] {
        assert_eq!(ids(&items(&app, caller, "/api/v1/stops").await), vec![hidden, active]);
        let inactive = items(&app, caller, "/api/v1/stops?is_active=false").await;
        assert_eq!(ids(&inactive), vec![hidden]);
        let one = call(&app, caller, GET, &hidden_path, None).await;
        assert_eq!(one.expect(StatusCode::OK).json()["is_active"], false);
        call(&app, caller, GET, &hidden_lines, None).await.expect(StatusCode::OK);
    }
    let anonymous = app.get("/api/v1/stops?is_active=true").send().await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let filtered = call(&app, As::User(&passenger), GET, "/api/v1/stops?is_active=true", None);
    assert_eq!(filtered.await.problem(StatusCode::FORBIDDEN), "forbidden");
}

#[tokio::test]
async fn stops_are_searched_by_trigram_filtered_and_paginated() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let martyrs = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let poste = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let percent = create_stop(&app, &admin, "Cité 50% Logements", TAFOURAH).await;
    let ezzouar = create_stop(&app, &admin, "Bab Ezzouar", BAB_EZZOUAR).await;
    let areas = json!({ "wilaya": "Alger", "commune": "Bab Ezzouar" });
    patch(&app, &admin, &format!("/api/v1/stops/{ezzouar}"), areas).await;
    let areas = json!({ "wilaya": "Alger", "commune": "Alger Centre" });
    patch(&app, &admin, &format!("/api/v1/stops/{poste}"), areas).await;
    let line = create_line(&app, &admin, "L1").await;
    put_stops(&app, &admin, line, entries(&[poste, martyrs])).await.expect(StatusCode::OK);

    let stops = |query: &str| listed(&app, format!("/api/v1/stops?{query}"));
    assert_eq!(stops("q=MARTYR").await, vec![martyrs]);
    assert_eq!(stops("q=des%20mart").await, vec![martyrs]);
    assert_eq!(stops("q=ost").await, vec![poste]);
    assert_eq!(stops("q=50%25").await, vec![percent], "% is a literal, not a wildcard");
    assert_eq!(stops("q=__").await, Vec::<Uuid>::new(), "_ is a literal, not a wildcard");
    assert_eq!(stops("wilaya=alger").await, vec![ezzouar, poste]);
    assert_eq!(stops("wilaya=Alger&commune=bab%20ezzouar").await, vec![ezzouar]);
    assert_eq!(stops(&format!("line_id={line}")).await, vec![poste, martyrs]);
    assert_eq!(stops(&format!("line_id={line}&q=poste")).await, vec![poste]);

    let invalid = [
        ("q=a".to_owned(), ("q", "too_short")),
        (format!("q={}", "a".repeat(101)), ("q", "too_long")),
        ("near=1".to_owned(), ("near", "unknown_field")),
        ("limit=0".to_owned(), ("limit", "out_of_range")),
        ("cursor=bogus".to_owned(), ("cursor", "invalid_format")),
    ];
    for (query, expected) in invalid {
        let response = app.get(&format!("/api/v1/stops?{query}")).send().await;
        assert_eq!(errors(&response), pairs(&[expected]), "{query}");
    }

    let mut seen = Vec::new();
    let mut cursor: Option<String> = None;
    loop {
        let query = match &cursor {
            Some(c) => format!("limit=3&cursor={c}"),
            None => "limit=3".to_owned(),
        };
        let page = app.get(&format!("/api/v1/stops?{query}")).send().await;
        let page = page.expect(StatusCode::OK).json();
        seen.extend(ids(&page["items"]));
        match page["next_cursor"].as_str() {
            Some(next) => cursor = Some(next.to_owned()),
            None => break,
        }
    }
    assert_eq!(seen, vec![ezzouar, percent, poste, martyrs], "newest first, no repeats");
}

#[tokio::test]
async fn nearby_stops_are_ordered_by_distance_within_the_radius() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let poste = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let tafourah = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    let martyrs = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let ezzouar = create_stop(&app, &admin, "Bab Ezzouar", BAB_EZZOUAR).await;
    let closed = create_stop(&app, &admin, "Fermé", (36.7732, 3.0589)).await;
    patch(&app, &admin, &format!("/api/v1/stops/{closed}"), json!({ "is_active": false })).await;

    let center = (36.7730, 3.0590);
    let uri = |params: &str| {
        format!("/api/v1/stops/nearby?lat={}&lng={}{params}", center.0, center.1)
    };
    let found = items(&app, As::Anonymous, &uri("&radius_m=2000")).await;
    assert_eq!(ids(&found), vec![poste, tafourah, martyrs], "inactive and far stops excluded");
    let mut previous = 0.0;
    for (item, place) in found.as_array().unwrap().iter().zip([GRANDE_POSTE, TAFOURAH, MARTYRS]) {
        let measured = item["distance_m"].as_f64().unwrap();
        assert!(measured >= previous, "sorted by distance");
        assert_close(&item["distance_m"], distance(center, place));
        previous = measured;
    }
    assert_eq!(found[0]["name"], "Grande Poste", "items are full stops");

    let default_radius = items(&app, As::Anonymous, &uri("")).await;
    assert_eq!(ids(&default_radius), vec![poste, tafourah], "500 m by default");
    let closest = items(&app, As::Anonymous, &uri("&radius_m=2000&limit=1")).await;
    assert_eq!(ids(&closest), vec![poste]);
    let widest = items(&app, As::Anonymous, &uri("&radius_m=5000")).await;
    assert!(!ids(&widest).contains(&ezzouar), "Bab Ezzouar is ~13 km away");

    let invalid = [
        ("&radius_m=9", ("radius_m", "out_of_range")),
        ("&radius_m=5001", ("radius_m", "out_of_range")),
        ("&limit=0", ("limit", "out_of_range")),
        ("&limit=51", ("limit", "out_of_range")),
        ("&radius_m=wide", ("radius_m", "invalid_format")),
        ("&page=2", ("page", "unknown_field")),
    ];
    for (params, expected) in invalid {
        let response = app.get(&uri(params)).send().await;
        assert_eq!(errors(&response), pairs(&[expected]), "{params}");
    }
    let out_of_range = app.get("/api/v1/stops/nearby?lat=91&lng=0").send().await;
    assert_eq!(errors(&out_of_range), pairs(&[("lat", "out_of_range")]));
    let not_a_number = app.get("/api/v1/stops/nearby?lat=NaN&lng=inf").send().await;
    let expected = [("lat", "invalid_format"), ("lng", "invalid_format")];
    assert_eq!(errors(&not_a_number), pairs(&expected));
    let missing = app.get("/api/v1/stops/nearby?lng=3").send().await;
    assert_eq!(errors(&missing), pairs(&[("lat", "required")]));
}

#[tokio::test]
async fn stop_photos_are_attached_replaced_and_removed() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let stop_path = format!("/api/v1/stops/{stop}");
    let photo_path = format!("{stop_path}/photo");
    let attach = |upload: Uuid| {
        call(&app, As::User(&admin), PUT, &photo_path, Some(json!({ "upload_id": upload })))
    };
    let key_of = |upload: Uuid| format!("stop_photo/{upload}");

    let first = app.upload(&admin, "stop_photo", "image/png", PNG).await;
    let body = attach(first).await.expect(StatusCode::OK).json();
    let url = body["photo_url"].as_str().unwrap().to_owned();
    assert!(url.contains(&key_of(first)));
    assert_eq!(app.download(&url).await, (StatusCode::OK, PNG.to_vec()));
    let public = app.get(&stop_path).send().await.expect(StatusCode::OK);
    assert_eq!(public.json()["photo_url"], url.as_str());
    assert_eq!(deletion_jobs(&app).await, Vec::<String>::new());

    assert_eq!(errors(&attach(first).await), pairs(&[("upload_id", "invalid_upload")]));
    let avatar = app.upload(&admin, "avatar", "image/png", PNG).await;
    assert_eq!(errors(&attach(avatar).await), pairs(&[("upload_id", "invalid_upload")]));

    let second = app.upload(&admin, "stop_photo", "image/png", PNG).await;
    attach(second).await.expect(StatusCode::OK);
    assert_eq!(deletion_jobs(&app).await, vec![key_of(first)], "the replaced photo");

    let removed = call(&app, As::User(&admin), DELETE, &photo_path, None).await;
    removed.expect(StatusCode::NO_CONTENT);
    assert_eq!(deletion_jobs(&app).await, vec![key_of(first), key_of(second)]);
    assert_eq!(app.get(&stop_path).send().await.json()["photo_url"], Value::Null);
    let again = call(&app, As::User(&admin), DELETE, &photo_path, None).await;
    again.expect(StatusCode::NO_CONTENT);
    assert_eq!(deletion_jobs(&app).await.len(), 2, "removing twice is a no-op");

    let third = app.upload(&admin, "stop_photo", "image/png", PNG).await;
    attach(third).await.expect(StatusCode::OK);
    let deleted = call(&app, As::User(&admin), DELETE, &stop_path, None).await;
    deleted.expect(StatusCode::NO_CONTENT);
    let expected = vec![key_of(first), key_of(second), key_of(third)];
    assert_eq!(deletion_jobs(&app).await, expected, "a deleted stop's photo too");
    assert_eq!(
        audit_actions(&app, "stop").await,
        [
            "stop.create",
            "stop.photo.set",
            "stop.photo.set",
            "stop.photo.remove",
            "stop.photo.set",
            "stop.delete",
        ]
    );
}

#[tokio::test]
async fn stop_photos_need_a_signed_in_stop_writer_and_storage() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let driver = app.account(Role::Driver).await;
    let writer = app.api_key(&admin, &["stop:write"]).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let path = format!("/api/v1/stops/{stop}/photo");
    let body = || Some(json!({ "upload_id": Uuid::now_v7() }));

    let anonymous = call(&app, As::Anonymous, PUT, &path, body()).await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let not_admin = call(&app, As::User(&driver), PUT, &path, body()).await;
    assert_eq!(not_admin.problem(StatusCode::FORBIDDEN), "forbidden");
    let key = call(&app, As::Key(&writer), PUT, &path, body()).await;
    assert_eq!(key.problem(StatusCode::FORBIDDEN), "forbidden", "API keys own no uploads");
    call(&app, As::Key(&writer), DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
    let not_admin = call(&app, As::User(&driver), DELETE, &path, None).await;
    assert_eq!(not_admin.problem(StatusCode::FORBIDDEN), "forbidden");
    let anonymous = call(&app, As::Anonymous, DELETE, &path, None).await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let missing = format!("/api/v1/stops/{}/photo", Uuid::now_v7());
    let unknown = call(&app, As::User(&admin), DELETE, &missing, None).await;
    assert_eq!(unknown.problem(StatusCode::NOT_FOUND), "not_found");
    let missing = call(&app, As::User(&admin), PUT, &missing, body()).await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    let unknown_upload = call(&app, As::User(&admin), PUT, &path, body()).await;
    assert_eq!(errors(&unknown_upload), pairs(&[("upload_id", "invalid_upload")]));

    let app = TestApp::builder().configure(|s| s.storage.endpoint = None).build().await;
    let admin = app.account(Role::Admin).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let path = format!("/api/v1/stops/{stop}/photo");
    let put = call(&app, As::User(&admin), PUT, &path, body()).await;
    assert_eq!(put.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
    let delete = call(&app, As::User(&admin), DELETE, &path, None).await;
    assert_eq!(delete.problem(StatusCode::SERVICE_UNAVAILABLE), "storage_unavailable");
    let read = app.get(&format!("/api/v1/stops/{stop}")).send().await;
    assert_eq!(read.expect(StatusCode::OK).json()["photo_url"], Value::Null);
}

#[tokio::test]
async fn stops_served_by_a_line_cannot_be_deleted() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let line = create_line(&app, &admin, "L1").await;
    put_stops(&app, &admin, line, entries(&[stop])).await.expect(StatusCode::OK);
    let path = format!("/api/v1/stops/{stop}");
    let refused = call(&app, As::User(&admin), DELETE, &path, None).await;
    assert_eq!(refused.problem(StatusCode::CONFLICT), "stop_in_use");
    put_stops(&app, &admin, line, json!([])).await.expect(StatusCode::OK);
    call(&app, As::User(&admin), DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
}

#[tokio::test]
async fn lines_of_a_stop_are_ordered_by_code_and_hide_inactive_lines() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    for code in ["L3", "L1", "L2", "L4"] {
        let line = create_line(&app, &admin, code).await;
        if code != "L4" {
            put_stops(&app, &admin, line, entries(&[stop])).await.expect(StatusCode::OK);
        }
        if code == "L2" {
            let path = format!("/api/v1/lines/{line}");
            patch(&app, &admin, &path, json!({ "is_active": false })).await;
        }
    }
    let path = format!("/api/v1/stops/{stop}/lines");
    let public = items(&app, As::Anonymous, &path).await;
    assert_eq!(column(&public, "code"), [json!("L1"), json!("L3")]);
    assert_eq!(public[0]["stops_count"], 1);
    let all = items(&app, As::User(&admin), &path).await;
    assert_eq!(column(&all, "code"), [json!("L1"), json!("L2"), json!("L3")]);
    let missing = app.get(&format!("/api/v1/stops/{}/lines", Uuid::now_v7())).send().await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
}

// --- Lines ---------------------------------------------------------------------------------------

#[tokio::test]
async fn lines_are_created_updated_and_codes_are_unique() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let body = json!({
        "code": "l1-bis",
        "name": "Martyrs – Bab Ezzouar",
        "color": "#1e88e5",
        "frequency_minutes": 12,
        "fare_dza": 30,
    });
    let response = call(&app, As::User(&admin), POST, "/api/v1/lines", Some(body)).await;
    let response = response.expect(StatusCode::CREATED);
    let line = response.json();
    let id = id_of(&line);
    let path = format!("/api/v1/lines/{id}");
    assert_eq!(response.header("location"), Some(path.as_str()));
    assert_eq!(line["code"], "L1-BIS");
    assert_eq!(line["color"], "#1E88E5");
    assert_eq!((&line["frequency_minutes"], &line["fare_dza"]), (&json!(12), &json!(30)));
    assert_eq!((&line["stops_count"], &line["has_route"]), (&json!(0), &json!(false)));
    assert_eq!(app.get(&path).send().await.expect(StatusCode::OK).json(), line);

    let duplicate = json!({ "code": "L1-bis", "name": "Autre" });
    let duplicate = call(&app, As::User(&admin), POST, "/api/v1/lines", Some(duplicate)).await;
    assert_eq!(duplicate.problem(StatusCode::CONFLICT), "line_code_taken");

    let changes = json!({ "frequency_minutes": null, "fare_dza": 50, "name": "L1 bis" });
    let updated = patch(&app, &admin, &path, changes).await;
    assert_eq!(updated["frequency_minutes"], Value::Null);
    assert_eq!((&updated["fare_dza"], &updated["name"]), (&json!(50), &json!("L1 bis")));
    assert_eq!(updated["color"], "#1E88E5");
    let immutable = call(&app, As::User(&admin), PATCH, &path, Some(json!({ "code": "L9" })));
    assert_eq!(errors(&immutable.await), pairs(&[("code", "unknown_field")]));

    let deactivated = patch(&app, &admin, &path, json!({ "is_active": false })).await;
    assert_eq!(deactivated["is_active"], false);
    assert_eq!(app.get(&path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    assert_eq!(listed(&app, "/api/v1/lines".into()).await, Vec::<Uuid>::new());
    let inactive = items(&app, As::User(&admin), "/api/v1/lines?is_active=false").await;
    assert_eq!(ids(&inactive), vec![id]);
    assert_eq!(audit_actions(&app, "line").await, ["line.create", "line.update", "line.update"]);
}

#[tokio::test]
async fn line_input_and_permissions_are_checked() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let stops_only = app.api_key(&admin, &["stop:write"]).await;
    let writer = app.api_key(&admin, &["line:write"]).await;
    let cases = [
        (
            json!({
                "code": "L 1",
                "name": "",
                "color": "blue",
                "frequency_minutes": 0,
                "fare_dza": -1,
            }),
            vec![
                ("code", "invalid_format"),
                ("name", "required"),
                ("color", "invalid_format"),
                ("frequency_minutes", "out_of_range"),
                ("fare_dza", "out_of_range"),
            ],
        ),
        (json!({ "code": "A".repeat(21), "name": "x" }), vec![("code", "too_long")]),
        (json!({ "name": "x" }), vec![("code", "required")]),
        (
            json!({ "code": "L1", "name": "x", "frequency_minutes": 1441 }),
            vec![("frequency_minutes", "out_of_range")],
        ),
        (json!({ "code": "L1", "name": "x", "route": [] }), vec![("route", "unknown_field")]),
    ];
    for (body, expected) in cases {
        let response = call(&app, As::User(&admin), POST, "/api/v1/lines", Some(body.clone()));
        let response = response.await;
        assert_eq!(errors(&response), pairs(&expected), "{body}");
    }

    let body = || Some(json!({ "code": "L1", "name": "Ligne 1" }));
    let denied = [
        (As::Anonymous, StatusCode::UNAUTHORIZED),
        (As::User(&passenger), StatusCode::FORBIDDEN),
        (As::Key(&stops_only), StatusCode::FORBIDDEN),
    ];
    for (caller, status) in denied {
        assert_eq!(call(&app, caller, POST, "/api/v1/lines", body()).await.status, status);
    }
    let created = call(&app, As::Key(&writer), POST, "/api/v1/lines", body()).await;
    let id = id_of(&created.expect(StatusCode::CREATED).json());
    let path = format!("/api/v1/lines/{id}");
    for (caller, status) in denied {
        let update = call(&app, caller, PATCH, &path, Some(json!({ "name": "x" }))).await;
        assert_eq!(update.status, status);
        assert_eq!(call(&app, caller, DELETE, &path, None).await.status, status);
    }

    let key = As::Key(&writer);
    let bad = json!({ "color": "#12345", "fare_dza": "free" });
    let bad = call(&app, key, PATCH, &path, Some(bad)).await;
    assert_eq!(errors(&bad), pairs(&[("fare_dza", "invalid_format")]), "serde errors first");
    let bad = call(&app, key, PATCH, &path, Some(json!({ "color": "#12345", "name": "" }))).await;
    assert_eq!(errors(&bad), pairs(&[("name", "required"), ("color", "invalid_format")]));
    let missing = format!("/api/v1/lines/{}", Uuid::now_v7());
    let update = call(&app, key, PATCH, &missing, Some(json!({ "name": "x" }))).await;
    assert_eq!(update.problem(StatusCode::NOT_FOUND), "not_found");
    let delete = call(&app, key, DELETE, &missing, None).await;
    assert_eq!(delete.problem(StatusCode::NOT_FOUND), "not_found");
}

#[tokio::test]
async fn lines_are_searched_by_code_and_name_and_filtered_by_stop() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let l1 = create_line(&app, &admin, "L1").await;
    let body = json!({ "code": "B12", "name": "Bab Ezzouar Express" });
    let express = call(&app, As::User(&admin), POST, "/api/v1/lines", Some(body)).await;
    let express = id_of(&express.expect(StatusCode::CREATED).json());
    put_stops(&app, &admin, l1, entries(&[stop])).await.expect(StatusCode::OK);

    let found = |query: &str| listed(&app, format!("/api/v1/lines?{query}"));
    assert_eq!(found("q=b12").await, vec![express]);
    assert_eq!(found("q=b12%20bab").await, vec![express], "code and name are searched together");
    assert_eq!(found("q=EXPRESS").await, vec![express]);
    assert_eq!(found("q=ligne").await, vec![l1]);
    assert_eq!(found(&format!("stop_id={stop}")).await, vec![l1]);
    assert_eq!(found("").await, vec![express, l1]);
    assert_eq!(found("limit=1").await, vec![express]);
    let short = app.get("/api/v1/lines?q=x").send().await;
    assert_eq!(errors(&short), pairs(&[("q", "too_short")]));
    let filtered = app.get("/api/v1/lines?is_active=true").send().await;
    assert_eq!(filtered.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let filtered = call(&app, As::User(&passenger), GET, "/api/v1/lines?is_active=true", None);
    assert_eq!(filtered.await.problem(StatusCode::FORBIDDEN), "forbidden");
}

#[tokio::test]
async fn stop_lists_are_replaced_atomically_and_round_trip() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let a = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let b = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let c = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/stops");

    let body = json!([
        { "stop_id": a },
        { "stop_id": b, "time_from_previous_s": 240 },
        { "stop_id": c },
    ]);
    let replaced = put_stops(&app, &admin, line, body).await.expect(StatusCode::OK).json();
    let list = &replaced["items"];
    assert_eq!(stop_order(list), vec![a, b, c]);
    assert_eq!(positions(list), [0, 1, 2]);
    assert_eq!(column(list, "time_from_previous_s"), [Value::Null, json!(240), Value::Null]);
    assert_eq!(list[0]["distance_from_previous_m"], Value::Null);
    assert_close(&list[1]["distance_from_previous_m"], distance(MARTYRS, GRANDE_POSTE));
    assert_close(&list[2]["distance_from_previous_m"], distance(GRANDE_POSTE, TAFOURAH));
    let summary = json!({
        "id": b,
        "name": "Grande Poste",
        "location": { "lat": GRANDE_POSTE.0, "lng": GRANDE_POSTE.1 },
        "is_active": true,
    });
    assert_eq!(list[1]["stop"], summary);
    assert_eq!(app.get(&path).send().await.json(), replaced, "GET returns what PUT stored");
    let line_body = app.get(&format!("/api/v1/lines/{line}")).send().await.json();
    assert_eq!(line_body["stops_count"], 3);

    // Any permutation can be stored in one request (legacy L-22).
    let reversed = put_stops(&app, &admin, line, entries(&[c, b, a])).await;
    let reversed = reversed.expect(StatusCode::OK).json();
    assert_eq!(stop_order(&reversed["items"]), vec![c, b, a]);
    assert_eq!(app.get(&path).send().await.json(), reversed);

    let unknown = Uuid::now_v7();
    let invalid = [
        (
            json!([
                { "stop_id": a, "time_from_previous_s": 5 },
                { "stop_id": b, "time_from_previous_s": -1 },
                { "stop_id": a },
            ]),
            vec![
                ("stops[1].time_from_previous_s", "out_of_range"),
                ("stops[2].stop_id", "duplicate"),
                ("stops[0].time_from_previous_s", "not_allowed"),
            ],
        ),
        (entries(&[a, unknown]), vec![("stops[1].stop_id", "unknown_reference")]),
        (json!([{ "stop_id": a, "position": 3 }]), vec![("stops[0].position", "unknown_field")]),
        (json!([{ "stop_id": "nope" }]), vec![("stops[0].stop_id", "invalid_format")]),
        (
            json!([{ "stop_id": a }, { "stop_id": b, "time_from_previous_s": 86_401 }]),
            vec![("stops[1].time_from_previous_s", "out_of_range")],
        ),
    ];
    for (stops, expected) in invalid {
        let response = put_stops(&app, &admin, line, stops.clone()).await;
        assert_eq!(errors(&response), pairs(&expected), "{stops}");
    }
    let too_many: Vec<Uuid> = (0..201).map(|_| Uuid::now_v7()).collect();
    let response = put_stops(&app, &admin, line, entries(&too_many)).await;
    assert_eq!(errors(&response), pairs(&[("stops", "out_of_range")]));
    assert_eq!(app.get(&path).send().await.json(), reversed, "failed requests change nothing");

    let missing = put_stops(&app, &admin, Uuid::now_v7(), entries(&[a])).await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    let passenger = app.account(Role::Passenger).await;
    let empty = || Some(json!({ "stops": [] }));
    let denied = call(&app, As::User(&passenger), PUT, &path, empty()).await;
    assert_eq!(denied.problem(StatusCode::FORBIDDEN), "forbidden");
    let anonymous = call(&app, As::Anonymous, PUT, &path, empty()).await;
    assert_eq!(anonymous.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let emptied = put_stops(&app, &admin, line, json!([])).await.expect(StatusCode::OK).json();
    assert_eq!(emptied["items"], json!([]));
    assert_eq!(
        audit_actions(&app, "line").await,
        ["line.create", "line.stops.replace", "line.stops.replace", "line.stops.replace"]
    );
}

#[tokio::test]
async fn stops_are_inserted_and_removed_with_shifts() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let a = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let b = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let c = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    let d = create_stop(&app, &admin, "Bab Ezzouar", BAB_EZZOUAR).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/stops");
    let add = |body: Value| call(&app, As::User(&admin), POST, &path, Some(body));

    let first = add(json!({ "stop_id": b })).await.expect(StatusCode::CREATED);
    assert_eq!(first.header("location"), Some(path.as_str()));
    add(json!({ "stop_id": d, "time_from_previous_s": 900 })).await.expect(StatusCode::CREATED);
    add(json!({ "stop_id": a, "position": 0 })).await.expect(StatusCode::CREATED);
    let inserted = add(json!({ "stop_id": c, "position": 2, "time_from_previous_s": 60 })).await;
    let list = inserted.expect(StatusCode::CREATED).json()["items"].clone();
    assert_eq!(stop_order(&list), vec![a, b, c, d]);
    let times = column(&list, "time_from_previous_s");
    assert_eq!(times, [Value::Null, Value::Null, json!(60), Value::Null], "d's time is unknown");
    let distances: Vec<bool> =
        column(&list, "distance_from_previous_m").iter().map(Value::is_number).collect();
    assert_eq!(distances, [false, true, true, true]);

    let already = add(json!({ "stop_id": b })).await;
    assert_eq!(already.problem(StatusCode::CONFLICT), "stop_already_on_line");
    let e = create_stop(&app, &admin, "Ben Aknoun", BEN_AKNOUN).await;
    let invalid = [
        (json!({ "stop_id": e, "position": 5 }), ("position", "out_of_range")),
        (json!({ "stop_id": e, "position": -1 }), ("position", "out_of_range")),
        (
            json!({ "stop_id": e, "position": 0, "time_from_previous_s": 30 }),
            ("time_from_previous_s", "not_allowed"),
        ),
        (json!({ "stop_id": Uuid::now_v7() }), ("stop_id", "unknown_reference")),
        (json!({ "position": 1 }), ("stop_id", "required")),
    ];
    for (body, expected) in invalid {
        assert_eq!(errors(&add(body.clone()).await), pairs(&[expected]), "{body}");
    }
    let out_of_range = add(json!({ "stop_id": e, "position": 5 })).await.json();
    assert_eq!(out_of_range["errors"][0]["params"], json!({ "min": 0, "max": 4 }));

    let remove = |stop: Uuid| {
        let (app, admin, uri) = (&app, &admin, format!("{path}/{stop}"));
        async move { call(app, As::User(admin), DELETE, &uri, None).await }
    };
    remove(c).await.expect(StatusCode::NO_CONTENT);
    let after = items(&app, As::Anonymous, &path).await;
    assert_eq!(stop_order(&after), vec![a, b, d]);
    assert_eq!(positions(&after), [0, 1, 2], "positions are compacted");
    assert_close(&after[2]["distance_from_previous_m"], distance(GRANDE_POSTE, BAB_EZZOUAR));
    remove(a).await.expect(StatusCode::NO_CONTENT);
    let after = items(&app, As::Anonymous, &path).await;
    assert_eq!(stop_order(&after), vec![b, d]);
    assert_eq!(after[0]["distance_from_previous_m"], Value::Null, "b is first now");
    assert_eq!(after[0]["time_from_previous_s"], Value::Null);

    assert_eq!(remove(a).await.problem(StatusCode::NOT_FOUND), "not_found", "not on the line");
    let malformed = call(&app, As::User(&admin), DELETE, &format!("{path}/nope"), None).await;
    assert_eq!(malformed.problem(StatusCode::NOT_FOUND), "not_found");
    let passenger = app.account(Role::Passenger).await;
    let denied = call(&app, As::User(&passenger), DELETE, &format!("{path}/{b}"), None).await;
    assert_eq!(denied.problem(StatusCode::FORBIDDEN), "forbidden");
    let denied = call(&app, As::Anonymous, DELETE, &format!("{path}/{b}"), None).await;
    assert_eq!(denied.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let denied = call(&app, As::Anonymous, POST, &path, Some(json!({ "stop_id": e }))).await;
    assert_eq!(denied.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let denied = call(&app, As::User(&passenger), POST, &path, Some(json!({ "stop_id": e }))).await;
    assert_eq!(denied.problem(StatusCode::FORBIDDEN), "forbidden");
    let missing = format!("/api/v1/lines/{}/stops", Uuid::now_v7());
    let missing = call(&app, As::User(&admin), POST, &missing, Some(json!({ "stop_id": e }))).await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    assert_eq!(
        audit_actions(&app, "line").await,
        [
            "line.create",
            "line.stops.add",
            "line.stops.add",
            "line.stops.add",
            "line.stops.add",
            "line.stops.remove",
            "line.stops.remove",
        ]
    );
}

#[tokio::test]
async fn removing_a_middle_stop_merges_known_segment_times() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let a = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let b = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let c = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    let line = create_line(&app, &admin, "L1").await;
    let stops = json!([
        { "stop_id": a },
        { "stop_id": b, "time_from_previous_s": 120 },
        { "stop_id": c, "time_from_previous_s": 45 },
    ]);
    put_stops(&app, &admin, line, stops).await.expect(StatusCode::OK);
    let removed = format!("/api/v1/lines/{line}/stops/{b}");
    call(&app, As::User(&admin), DELETE, &removed, None).await.expect(StatusCode::NO_CONTENT);
    let list = items(&app, As::Anonymous, &format!("/api/v1/lines/{line}/stops")).await;
    assert_eq!(list[1]["time_from_previous_s"], 165);
}

#[tokio::test]
async fn inactive_stops_stay_on_their_lines_and_moves_update_distances() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let a = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let b = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let line = create_line(&app, &admin, "L1").await;
    let other = create_line(&app, &admin, "L2").await;
    put_stops(&app, &admin, line, entries(&[a, b])).await.expect(StatusCode::OK);
    put_stops(&app, &admin, other, entries(&[b, a])).await.expect(StatusCode::OK);
    patch(&app, &admin, &format!("/api/v1/stops/{b}"), json!({ "is_active": false })).await;

    let list = items(&app, As::Anonymous, &format!("/api/v1/lines/{line}/stops")).await;
    assert_eq!(stop_order(&list), vec![a, b], "buses pass inactive stops");
    assert_eq!(list[1]["stop"]["is_active"], false);

    // Moving a stop recomputes the distances of every line serving it.
    let moved = (36.7856, 3.0703);
    let location = json!({ "location": { "lat": moved.0, "lng": moved.1 } });
    patch(&app, &admin, &format!("/api/v1/stops/{b}"), location).await;
    for line in [line, other] {
        let list = items(&app, As::Anonymous, &format!("/api/v1/lines/{line}/stops")).await;
        assert_close(&list[1]["distance_from_previous_m"], distance(MARTYRS, moved));
    }
}

/// How many stored distances of the lines serving `stop` differ from the geodesic distance
/// between their consecutive stops.
async fn stale_distances(app: &TestApp, stop: Uuid) -> i64 {
    sqlx::query_scalar(
        "SELECT count(*) FROM (
             SELECT ls.distance_from_previous_m AS stored,
                    ST_Distance(s.location, lag(s.location) OVER (
                        PARTITION BY ls.line_id ORDER BY ls.position
                    ))::real AS expected
             FROM line_stops ls
             JOIN stops s ON s.id = ls.stop_id
             WHERE ls.line_id IN (SELECT line_id FROM line_stops WHERE stop_id = $1)
         ) d
         WHERE stored IS DISTINCT FROM expected",
    )
    .bind(stop)
    .fetch_one(app.pool())
    .await
    .unwrap()
}

#[tokio::test]
async fn a_move_racing_with_a_line_gaining_the_stop_recomputes_that_line() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let a = create_stop(&app, &admin, "Place des Martyrs", MARTYRS).await;
    let moving = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let c = create_stop(&app, &admin, "Tafourah", TAFOURAH).await;
    let serving = create_line(&app, &admin, "L1").await;
    let gaining = create_line(&app, &admin, "L2").await;
    put_stops(&app, &admin, serving, entries(&[a, moving])).await.expect(StatusCode::OK);
    put_stops(&app, &admin, gaining, entries(&[a, c])).await.expect(StatusCode::OK);

    // A stop-list writer appends the stop to L2 (same statements and lock order as
    // `add_stop`) and holds its transaction open, distances computed from the old location.
    let mut writer = app.pool().begin().await.unwrap();
    sqlx::query("UPDATE lines SET updated_at = now() WHERE id = $1")
        .bind(gaining)
        .execute(&mut *writer)
        .await
        .unwrap();
    sqlx::query("SELECT id FROM stops WHERE id = $1 FOR SHARE")
        .bind(moving)
        .execute(&mut *writer)
        .await
        .unwrap();
    sqlx::query("INSERT INTO line_stops (line_id, stop_id, position) VALUES ($1, $2, 2)")
        .bind(gaining)
        .bind(moving)
        .execute(&mut *writer)
        .await
        .unwrap();
    sqlx::query(
        "UPDATE line_stops ls SET distance_from_previous_m = d.distance
         FROM (
             SELECT l.stop_id, ST_Distance(s.location, lag(s.location) OVER (
                        ORDER BY l.position
                    ))::real AS distance
             FROM line_stops l JOIN stops s ON s.id = l.stop_id
             WHERE l.line_id = $1
         ) d
         WHERE ls.line_id = $1 AND ls.stop_id = d.stop_id",
    )
    .bind(gaining)
    .execute(&mut *writer)
    .await
    .unwrap();

    // The move reads the lines serving the stop (L1 only), then waits for the stop row.
    let moved = (36.7856, 3.0703);
    let patch = StopPatch {
        location: Some(GeoPoint::from_trusted(moved.0, moved.1)),
        ..StopPatch::default()
    };
    let (store, id, now) = (&*app.infra.store, StopId::from_uuid(moving), chrono::Utc::now());
    let move_stop = StopRepository::update(store, id, patch, now, WriteEffects::default());
    let mut mover = std::pin::pin!(move_stop);
    let blocked = tokio::time::timeout(Duration::from_millis(500), &mut mover).await;
    assert!(blocked.is_err(), "the move waits for the writer's share lock");
    writer.commit().await.unwrap();
    mover.await.unwrap();

    // Both lines, including the one that gained the stop meanwhile, use the new location.
    assert_eq!(stale_distances(&app, moving).await, 0);
    let list = items(&app, As::Anonymous, &format!("/api/v1/lines/{gaining}/stops")).await;
    assert_eq!(stop_order(&list), vec![a, c, moving]);
    assert_close(&list[2]["distance_from_previous_m"], distance(TAFOURAH, moved));
    let list = items(&app, As::Anonymous, &format!("/api/v1/lines/{serving}/stops")).await;
    assert_close(&list[1]["distance_from_previous_m"], distance(MARTYRS, moved));
}

#[tokio::test]
async fn concurrent_changes_to_a_line_are_serialized() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let places = [MARTYRS, GRANDE_POSTE, TAFOURAH, BAB_EZZOUAR, BEN_AKNOUN, (36.75, 3.05)];
    let mut stops = Vec::new();
    for (i, place) in places.into_iter().enumerate() {
        stops.push(create_stop(&app, &admin, &format!("Stop {i}"), place).await);
    }
    let all: HashSet<Uuid> = stops.iter().copied().collect();
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/stops");

    // Ten whole-list replacements with different orders race each other: each one either
    // wins entirely or is entirely overwritten, and positions stay contiguous.
    let orders: Vec<Vec<Uuid>> = (0..10)
        .map(|i| {
            let mut order = stops.clone();
            order.rotate_left(i % stops.len());
            if i % 2 == 1 {
                order.reverse();
            }
            order
        })
        .collect();
    let replacements = orders.iter().map(|order| put_stops(&app, &admin, line, entries(order)));
    for response in join_all(replacements).await {
        response.expect(StatusCode::OK);
    }
    let list = items(&app, As::Anonymous, &path).await;
    assert!(orders.contains(&stop_order(&list)), "the final list is one of the submitted lists");
    assert_eq!(positions(&list), (0..6).collect::<Vec<u64>>());

    // Concurrent insertions of distinct stops at the front all succeed, without gaps, and the
    // distances follow the final order.
    put_stops(&app, &admin, line, json!([])).await.expect(StatusCode::OK);
    let inserts = stops.iter().map(|id| {
        let body = json!({ "stop_id": id, "position": 0 });
        call(&app, As::User(&admin), POST, &path, Some(body))
    });
    for response in join_all(inserts).await {
        response.expect(StatusCode::CREATED);
    }
    let list = items(&app, As::Anonymous, &path).await;
    assert_eq!(stop_order(&list).into_iter().collect::<HashSet<_>>(), all);
    assert_eq!(positions(&list), (0..6).collect::<Vec<u64>>());
    let firsts: Vec<bool> =
        column(&list, "distance_from_previous_m").iter().map(Value::is_null).collect();
    assert_eq!(firsts, [true, false, false, false, false, false]);

    // Racing insertions of the same stop: exactly one wins.
    put_stops(&app, &admin, line, json!([])).await.expect(StatusCode::OK);
    let same = (0..5).map(|_| {
        call(&app, As::User(&admin), POST, &path, Some(json!({ "stop_id": stops[0] })))
    });
    let statuses: Vec<StatusCode> = join_all(same).await.into_iter().map(|r| r.status).collect();
    let count = |status| statuses.iter().filter(|s| **s == status).count();
    assert_eq!((count(StatusCode::CREATED), count(StatusCode::CONFLICT)), (1, 4), "{statuses:?}");
}

#[tokio::test]
async fn routes_are_geojson_line_strings() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/route");
    assert_eq!(app.get(&path).send().await.problem(StatusCode::NOT_FOUND), "not_found", "unset");

    let route = json!({
        "type": "LineString",
        "coordinates": [[3.0603, 36.7856], [3.0588, 36.7731], [3.0607, 36.7725]],
    });
    let set = |body: &Value| call(&app, As::User(&admin), PUT, &path, Some(body.clone()));
    assert_eq!(set(&route).await.expect(StatusCode::OK).json(), route);
    assert_eq!(app.get(&path).send().await.expect(StatusCode::OK).json(), route);
    let line_body = app.get(&format!("/api/v1/lines/{line}")).send().await.json();
    assert_eq!(line_body["has_route"], true);

    let two = [[3.0, 36.0], [3.1, 36.1]];
    let broken = [[3.0, 36.0], [3.0, 36.0], [190.0, 95.0]];
    let invalid = [
        (json!({ "type": "Point", "coordinates": two }), vec![("type", "invalid_format")]),
        (json!({ "coordinates": two }), vec![("type", "required")]),
        (
            json!({ "type": "LineString", "coordinates": [[3.0, 36.0]] }),
            vec![("coordinates", "out_of_range")],
        ),
        (
            json!({ "type": "LineString", "coordinates": broken }),
            vec![
                ("coordinates[1]", "duplicate"),
                ("coordinates[2][0]", "out_of_range"),
                ("coordinates[2][1]", "out_of_range"),
            ],
        ),
        (
            json!({ "type": "LineString", "coordinates": [[3.0, 36.0, 12.0], [3.1]] }),
            vec![("coordinates[0]", "invalid_format"), ("coordinates[1]", "invalid_format")],
        ),
    ];
    for (body, expected) in invalid {
        assert_eq!(errors(&set(&body).await), pairs(&expected), "{body}");
    }
    let points = |n: i32| -> Vec<[f64; 2]> {
        (0..n).map(|i| [3.0 + f64::from(i) * 1e-5, 36.7]).collect()
    };
    let longest = json!({ "type": "LineString", "coordinates": points(10_000) });
    set(&longest).await.expect(StatusCode::OK);
    let too_long = json!({ "type": "LineString", "coordinates": points(10_001) });
    assert_eq!(errors(&set(&too_long).await), pairs(&[("coordinates", "out_of_range")]));

    let denied = call(&app, As::User(&passenger), PUT, &path, Some(route.clone())).await;
    assert_eq!(denied.problem(StatusCode::FORBIDDEN), "forbidden", "legacy L-04");
    let denied = call(&app, As::Anonymous, PUT, &path, Some(route.clone())).await;
    assert_eq!(denied.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let denied = call(&app, As::Anonymous, DELETE, &path, None).await;
    assert_eq!(denied.problem(StatusCode::UNAUTHORIZED), "authentication_required");
    let denied = call(&app, As::User(&passenger), DELETE, &path, None).await;
    assert_eq!(denied.problem(StatusCode::FORBIDDEN), "forbidden");
    let missing = format!("/api/v1/lines/{}/route", Uuid::now_v7());
    let unknown = call(&app, As::User(&admin), DELETE, &missing, None).await;
    assert_eq!(unknown.problem(StatusCode::NOT_FOUND), "not_found");
    let missing = call(&app, As::User(&admin), PUT, &missing, Some(route.clone())).await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");

    call(&app, As::User(&admin), DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
    assert_eq!(app.get(&path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    call(&app, As::User(&admin), DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
    assert_eq!(
        audit_actions(&app, "line").await,
        ["line.create", "line.route.set", "line.route.set", "line.route.delete"],
        "removing a missing route is not audited"
    );

    set(&route).await.expect(StatusCode::OK);
    patch(&app, &admin, &format!("/api/v1/lines/{line}"), json!({ "is_active": false })).await;
    assert_eq!(app.get(&path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    call(&app, As::User(&admin), GET, &path, None).await.expect(StatusCode::OK);
}

#[tokio::test]
async fn inactive_lines_hide_their_stops_route_and_schedules() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let reader = app.api_key(&admin, &["catalog:read"]).await;
    let schedules_key = app.api_key(&admin, &["schedule:write"]).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let line = create_line(&app, &admin, "L1").await;
    put_stops(&app, &admin, line, entries(&[stop])).await.expect(StatusCode::OK);
    patch(&app, &admin, &format!("/api/v1/lines/{line}"), json!({ "is_active": false })).await;
    let paths = [
        format!("/api/v1/lines/{line}"),
        format!("/api/v1/lines/{line}/stops"),
        format!("/api/v1/lines/{line}/schedules"),
    ];
    for path in &paths {
        for caller in [As::Anonymous, As::Key(&reader)] {
            let response = call(&app, caller, GET, path, None).await;
            assert_eq!(response.problem(StatusCode::NOT_FOUND), "not_found", "{path}");
        }
        call(&app, As::User(&admin), GET, path, None).await.expect(StatusCode::OK);
    }
    let schedules = call(&app, As::Key(&schedules_key), GET, &paths[2], None).await;
    schedules.expect(StatusCode::OK);
    let lines = items(&app, As::Anonymous, &format!("/api/v1/stops/{stop}/lines")).await;
    assert_eq!(lines, json!([]));

    // Filtering the stop list by the hidden line does not reveal its stops either.
    let line_writer = app.api_key(&admin, &["line:write"]).await;
    let served = format!("/api/v1/stops?line_id={line}");
    for caller in [As::Anonymous, As::Key(&reader), As::Key(&schedules_key)] {
        assert_eq!(items(&app, caller, &served).await, json!([]));
    }
    for caller in [As::User(&admin), As::Key(&line_writer)] {
        assert_eq!(ids(&items(&app, caller, &served).await), vec![stop]);
    }
}

#[tokio::test]
async fn deleting_a_line_cascades_and_is_refused_while_buses_are_assigned() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let stop = create_stop(&app, &admin, "Grande Poste", GRANDE_POSTE).await;
    let line = create_line(&app, &admin, "L1").await;
    put_stops(&app, &admin, line, entries(&[stop])).await.expect(StatusCode::OK);
    let schedules = format!("/api/v1/lines/{line}/schedules");
    let body = schedule(1, "06:00", "09:00");
    call(&app, As::User(&admin), POST, &schedules, Some(body)).await.expect(StatusCode::CREATED);

    // Bus assignments arrive with M2 WP4 (`bus_line_assignments.line_id … ON DELETE RESTRICT`).
    // A stand-in table with the same foreign key exercises the `line_in_use` mapping of the
    // constraint name now.
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS bus_line_assignments (
             line_id uuid NOT NULL,
             CONSTRAINT bus_line_assignments_line_id_fkey
                 FOREIGN KEY (line_id) REFERENCES lines (id) ON DELETE RESTRICT
         )",
    )
    .execute(app.pool())
    .await
    .unwrap();
    sqlx::query("INSERT INTO bus_line_assignments (line_id) VALUES ($1)")
        .bind(line)
        .execute(app.pool())
        .await
        .unwrap();
    let path = format!("/api/v1/lines/{line}");
    let refused = call(&app, As::User(&admin), DELETE, &path, None).await;
    assert_eq!(refused.problem(StatusCode::CONFLICT), "line_in_use");
    app.get(&path).send().await.expect(StatusCode::OK);

    sqlx::query("DELETE FROM bus_line_assignments").execute(app.pool()).await.unwrap();
    call(&app, As::User(&admin), DELETE, &path, None).await.expect(StatusCode::NO_CONTENT);
    let stops: i64 = sqlx::query_scalar("SELECT count(*) FROM line_stops WHERE line_id = $1")
        .bind(line)
        .fetch_one(app.pool())
        .await
        .unwrap();
    let schedules: i64 = sqlx::query_scalar("SELECT count(*) FROM schedules WHERE line_id = $1")
        .bind(line)
        .fetch_one(app.pool())
        .await
        .unwrap();
    assert_eq!((stops, schedules), (0, 0), "cascaded");
    app.get(&format!("/api/v1/stops/{stop}")).send().await.expect(StatusCode::OK);
    let actions = audit_actions(&app, "line").await;
    assert_eq!(actions.last().map(String::as_str), Some("line.delete"));
}

// --- Schedules -----------------------------------------------------------------------------------

fn schedule(day: i64, start: &str, end: &str) -> Value {
    json!({ "day_of_week": day, "start_time": start, "end_time": end, "frequency_minutes": 10 })
}

fn with(mut body: Value, field: &str, value: Value) -> Value {
    body[field] = value;
    body
}

#[tokio::test]
async fn schedules_are_validated_and_may_not_overlap() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/schedules");
    let create = |body: Value| call(&app, As::User(&admin), POST, &path, Some(body));
    let update = |uri: String, body: Value| {
        let (app, admin) = (&app, &admin);
        async move { call(app, As::User(admin), PATCH, &uri, Some(body)).await }
    };

    let created = create(schedule(1, "06:00", "09:00")).await.expect(StatusCode::CREATED);
    let morning = created.json();
    let location = format!("/api/v1/schedules/{}", id_of(&morning));
    assert_eq!(created.header("location"), Some(location.as_str()));
    assert_eq!(morning["line_id"], line.to_string());
    assert_eq!(morning["day_of_week"], 1);
    assert_eq!((&morning["start_time"], &morning["end_time"]), (&json!("06:00"), &json!("09:00")));
    assert_eq!((&morning["frequency_minutes"], &morning["is_active"]), (&json!(10), &json!(true)));
    assert_eq!(app.get(&location).send().await.expect(StatusCode::OK).json(), morning);

    create(schedule(1, "09:00", "12:00")).await.expect(StatusCode::CREATED);
    create(schedule(2, "07:00", "08:00")).await.expect(StatusCode::CREATED);
    let overlap = create(schedule(1, "08:59", "09:30")).await;
    assert_eq!(overlap.problem(StatusCode::CONFLICT), "schedule_overlap");
    let inactive = with(schedule(1, "07:00", "08:00"), "is_active", json!(false));
    let inactive = create(inactive).await.expect(StatusCode::CREATED).json();
    let other_line = create_line(&app, &admin, "L2").await;
    let other_path = format!("/api/v1/lines/{other_line}/schedules");
    let body = Some(schedule(1, "06:00", "09:00"));
    call(&app, As::User(&admin), POST, &other_path, body).await.expect(StatusCode::CREATED);

    let invalid = [
        (
            schedule(8, "9:00", "08:00"),
            vec![("day_of_week", "out_of_range"), ("start_time", "invalid_format")],
        ),
        (
            schedule(0, "24:00", "08:00"),
            vec![("day_of_week", "out_of_range"), ("start_time", "invalid_format")],
        ),
        (schedule(3, "10:00", "10:00"), vec![("end_time", "must_be_after")]),
        (schedule(3, "11:00", "10:00"), vec![("end_time", "must_be_after")]),
        (
            with(schedule(3, "10:00", "11:00"), "frequency_minutes", json!(1441)),
            vec![("frequency_minutes", "out_of_range")],
        ),
        (
            json!({ "day_of_week": 3, "start_time": "10:00", "end_time": "11:00" }),
            vec![("frequency_minutes", "required")],
        ),
        (
            with(schedule(3, "10:00", "11:00"), "line_id", json!(line)),
            vec![("line_id", "unknown_field")],
        ),
    ];
    for (body, expected) in invalid {
        assert_eq!(errors(&create(body.clone()).await), pairs(&expected), "{body}");
    }
    let params = create(schedule(3, "10:00", "09:00")).await.json();
    assert_eq!(params["errors"][0]["params"], json!({ "field": "start_time" }));

    // Updates follow the same rules.
    let inactive_path = format!("/api/v1/schedules/{}", id_of(&inactive));
    let activate = update(inactive_path.clone(), json!({ "is_active": true })).await;
    assert_eq!(activate.problem(StatusCode::CONFLICT), "schedule_overlap");
    let earlier = json!({ "start_time": "05:00", "end_time": "06:00", "is_active": true });
    let moved = patch(&app, &admin, &inactive_path, earlier).await;
    assert_eq!((&moved["start_time"], &moved["is_active"]), (&json!("05:00"), &json!(true)));
    let backwards = update(inactive_path.clone(), json!({ "start_time": "07:00" })).await;
    assert_eq!(errors(&backwards), pairs(&[("end_time", "must_be_after")]));
    let bad = json!({ "day_of_week": 9, "frequency_minutes": 0 });
    let bad = update(inactive_path.clone(), bad).await;
    let expected = [("day_of_week", "out_of_range"), ("frequency_minutes", "out_of_range")];
    assert_eq!(errors(&bad), pairs(&expected));
    let immutable = update(inactive_path.clone(), json!({ "line_id": other_line })).await;
    assert_eq!(errors(&immutable), pairs(&[("line_id", "unknown_field")]));
    let missing_line = format!("/api/v1/lines/{}/schedules", Uuid::now_v7());
    let body = Some(schedule(1, "06:00", "07:00"));
    let missing_line = call(&app, As::User(&admin), POST, &missing_line, body).await;
    assert_eq!(missing_line.problem(StatusCode::NOT_FOUND), "not_found");
    let missing = format!("/api/v1/schedules/{}", Uuid::now_v7());
    let missing = update(missing, json!({ "is_active": false })).await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");
    let actions = audit_actions(&app, "schedule").await;
    assert_eq!(actions.iter().filter(|a| *a == "schedule.create").count(), 5);
    assert_eq!(actions.iter().filter(|a| *a == "schedule.update").count(), 1);
}

#[tokio::test]
async fn schedules_are_listed_in_order_with_visibility_and_permissions() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let passenger = app.account(Role::Passenger).await;
    let writer = app.api_key(&admin, &["schedule:write"]).await;
    let line_key = app.api_key(&admin, &["line:write"]).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/schedules");
    let create = |body: Value| async {
        let response = call(&app, As::Key(&writer), POST, &path, Some(body)).await;
        id_of(&response.expect(StatusCode::CREATED).json())
    };
    let tuesday = create(schedule(2, "06:00", "09:00")).await;
    let monday_late = create(schedule(1, "17:00", "20:00")).await;
    let monday = create(schedule(1, "06:00", "09:00")).await;
    let hidden = create(with(schedule(1, "07:00", "08:00"), "is_active", json!(false))).await;

    let public = items(&app, As::Anonymous, &path).await;
    assert_eq!(ids(&public), vec![monday, monday_late, tuesday]);
    let all = items(&app, As::User(&admin), &path).await;
    assert_eq!(ids(&all), vec![monday, hidden, monday_late, tuesday]);
    let hidden_path = format!("/api/v1/schedules/{hidden}");
    assert_eq!(app.get(&hidden_path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    call(&app, As::Key(&writer), GET, &hidden_path, None).await.expect(StatusCode::OK);
    app.get(&format!("/api/v1/schedules/{monday}")).send().await.expect(StatusCode::OK);
    let missing = app.get(&format!("/api/v1/lines/{}/schedules", Uuid::now_v7())).send().await;
    assert_eq!(missing.problem(StatusCode::NOT_FOUND), "not_found");

    let body = || Some(schedule(3, "06:00", "07:00"));
    let monday_path = format!("/api/v1/schedules/{monday}");
    let change = || Some(json!({ "is_active": false }));
    let denied = [
        (As::Anonymous, StatusCode::UNAUTHORIZED),
        (As::User(&passenger), StatusCode::FORBIDDEN),
        (As::Key(&line_key), StatusCode::FORBIDDEN),
    ];
    for (caller, status) in denied {
        assert_eq!(call(&app, caller, POST, &path, body()).await.status, status);
        assert_eq!(call(&app, caller, PATCH, &monday_path, change()).await.status, status);
        assert_eq!(call(&app, caller, DELETE, &monday_path, None).await.status, status);
    }

    let key = As::Key(&writer);
    call(&app, key, DELETE, &monday_path, None).await.expect(StatusCode::NO_CONTENT);
    assert_eq!(app.get(&monday_path).send().await.problem(StatusCode::NOT_FOUND), "not_found");
    let again = call(&app, key, DELETE, &monday_path, None).await;
    assert_eq!(again.problem(StatusCode::NOT_FOUND), "not_found");
    let actions = audit_actions(&app, "schedule").await;
    assert_eq!(actions.last().map(String::as_str), Some("schedule.delete"));
}

#[tokio::test]
async fn schedule_constraints_are_mapped_by_the_repository() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    let line = create_line(&app, &admin, "L1").await;
    let path = format!("/api/v1/lines/{line}/schedules");
    let create = |body: Value| call(&app, As::User(&admin), POST, &path, Some(body));
    let first = create(schedule(1, "06:00", "09:00")).await.expect(StatusCode::CREATED).json();
    let first = ScheduleId::from_uuid(id_of(&first));
    let second = create(schedule(1, "10:00", "12:00")).await.expect(StatusCode::CREATED).json();
    let second = ScheduleId::from_uuid(id_of(&second));
    let store = &*app.infra.store;
    let time = |raw| Some(TimeOfDay::parse(raw).unwrap());
    let update = |id, patch| {
        ScheduleRepository::update(store, id, patch, chrono::Utc::now(), WriteEffects::default())
    };

    // What a concurrent change could produce despite the use-case's checks: the database has
    // the last word, and its constraints come back as typed errors.
    let backwards = SchedulePatch { start: time("10:00"), ..SchedulePatch::default() };
    match update(first, backwards).await.unwrap_err() {
        AppError::Validation(v) => {
            let got: Vec<_> =
                v.iter().map(|f| (f.field.to_string(), f.violation.clone())).collect();
            let must_be_after = Violation::MustBeAfter { field: "start_time".into() };
            assert_eq!(got, vec![("end_time".to_owned(), must_be_after)]);
        }
        other => panic!("expected a validation error, got {other:?}"),
    }
    let overlapping =
        SchedulePatch { start: time("08:00"), end: time("11:00"), ..SchedulePatch::default() };
    let err = update(second, overlapping).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::ScheduleOverlap)), "{err:?}");
    let deactivate = SchedulePatch { is_active: Some(false), ..SchedulePatch::default() };
    let err = update(ScheduleId::generate(), deactivate).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("schedule")));

    // Concurrent creations of overlapping schedules: the exclusion constraint lets one in.
    let racing = (0..5).map(|i| create(schedule(4, &format!("0{}:00", 5 + i % 2), "09:00")));
    let statuses: Vec<StatusCode> = join_all(racing).await.into_iter().map(|r| r.status).collect();
    let count = |status| statuses.iter().filter(|s| **s == status).count();
    assert_eq!((count(StatusCode::CREATED), count(StatusCode::CONFLICT)), (1, 4), "{statuses:?}");
}
