//! Network catalogue use-cases against the in-memory ports: validation, visibility,
//! authorization, audit, photos with their outbox jobs, stop ordering and schedules.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use dz_domain::authz::{Actor, Permission, PermissionSet};
use dz_domain::ids::{ApiKeyId, LineId, ScheduleId, SessionId, StopId, UploadId, UserId};
use dz_domain::network::{Line, LineStop, Schedule};
use dz_domain::upload::{UploadPurpose, UploadStatus};
use dz_domain::user::Role;
use dz_domain::{ConflictKind, DenyReason};

use super::*;
use crate::error::{AppError, AuthFailure};
use crate::jobs::Job;
use crate::pagination::PageRequest;
use crate::ports::{AuditFilter, AuditRepository, Clock, RequestMeta};
use crate::testing::Fakes;

/// Coordinates around Algiers.
const MARTYRS: (f64, f64) = (36.7856, 3.0603);
const GRANDE_POSTE: (f64, f64) = (36.7731, 3.0588);
const TAFOURAH: (f64, f64) = (36.7725, 3.0607);
const BAB_EZZOUAR: (f64, f64) = (36.7207, 3.1838);

struct Network {
    f: Fakes,
    stops: StopService,
    lines: LineService,
    schedules: ScheduleService,
}

fn network() -> Network {
    let f = Fakes::default();
    let stops = StopService::new(f.store.clone(), f.uploads(), f.clock.clone());
    let lines = LineService::new(f.store.clone(), f.store.clone(), f.clock.clone());
    let schedules = ScheduleService::new(f.store.clone(), f.store.clone(), f.clock.clone());
    Network { f, stops, lines, schedules }
}

fn user(role: Role) -> Actor {
    Actor::User { id: UserId::generate(), role, session_id: SessionId::generate() }
}

fn service(scopes: &[Permission]) -> Actor {
    Actor::Service { key_id: ApiKeyId::generate(), scopes: PermissionSet::of(scopes) }
}

fn meta() -> RequestMeta {
    RequestMeta::default()
}

fn codes(err: AppError) -> Vec<(String, &'static str)> {
    match err {
        AppError::Validation(v) => {
            v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
        }
        other => panic!("expected a validation error, got {other:?}"),
    }
}

fn stop_input(name: &str, (lat, lng): (f64, f64)) -> CreateStopInput {
    CreateStopInput { name: name.into(), location: (lat, lng), ..CreateStopInput::default() }
}

async fn audit_actions(n: &Network) -> Vec<String> {
    let page = PageRequest { limit: 100, after: None };
    let entries = AuditRepository::list(&*n.f.store, &AuditFilter::default(), page).await.unwrap();
    let mut actions: Vec<String> = entries.items.into_iter().map(|e| e.action).collect();
    actions.reverse();
    actions
}

impl Network {
    async fn stop(&self, name: &str, at: (f64, f64)) -> StopId {
        let view = self.stops.create(&user(Role::Admin), stop_input(name, at), &meta()).await;
        view.unwrap().stop.id
    }

    async fn line(&self, code: &str) -> Line {
        let name = format!("Ligne {code}");
        let input = CreateLineInput { code: code.into(), name, ..CreateLineInput::default() };
        self.lines.create(&user(Role::Admin), input, &meta()).await.unwrap()
    }

    async fn replace(
        &self,
        line: LineId,
        stops: &[(StopId, Option<i64>)],
    ) -> AppResult<Vec<LineStop>> {
        self.lines.replace_stops(&user(Role::Admin), line, stops.to_vec(), &meta()).await
    }
}

fn order(stops: &[LineStop]) -> Vec<StopId> {
    stops.iter().map(|s| s.stop.id).collect()
}

// --- Stops ---------------------------------------------------------------------------------------

#[tokio::test]
async fn stops_are_validated_normalized_and_audited() {
    let n = network();
    let admin = user(Role::Admin);
    let input = CreateStopInput {
        name: "  Place des Martyrs ".into(),
        location: MARTYRS,
        address: Some(" Rue Bab Azoun ".into()),
        wilaya: Some("Alger".into()),
        features: Some(vec!["Shelter".into(), "bench".into()]),
        ..CreateStopInput::default()
    };
    let view = n.stops.create(&admin, input, &meta()).await.unwrap();
    let stop = &view.stop;
    assert_eq!(stop.name.as_str(), "Place des Martyrs");
    assert_eq!((stop.location.lat(), stop.location.lng()), MARTYRS);
    let texts = (stop.address.as_str(), stop.wilaya.as_str(), stop.commune.as_str());
    assert_eq!(texts, ("Rue Bab Azoun", "Alger", ""));
    assert_eq!(stop.features.as_slice(), ["shelter".to_owned(), "bench".to_owned()]);
    assert!(stop.is_active && stop.photo_key.is_none() && view.photo_url.is_none());
    assert_eq!((stop.created_at, stop.updated_at), (n.f.clock.now(), n.f.clock.now()));
    assert_eq!(audit_actions(&n).await, ["stop.create"]);

    let bad = CreateStopInput {
        name: " ".into(),
        location: (91.0, f64::NAN),
        description: Some("x".repeat(2001)),
        features: Some(vec!["ok".into(), "not ok".into()]),
        ..CreateStopInput::default()
    };
    assert_eq!(
        codes(n.stops.create(&admin, bad, &meta()).await.unwrap_err()),
        vec![
            ("name".into(), "required"),
            ("location.lat".into(), "out_of_range"),
            ("location.lng".into(), "invalid_format"),
            ("description".into(), "too_long"),
            ("features[1]".into(), "invalid_format"),
        ]
    );
    assert_eq!(n.f.store.audit_len(), 1, "invalid input is not audited");
}

#[tokio::test]
async fn only_stop_writers_manage_stops() {
    let n = network();
    let input = || stop_input("Tafourah", TAFOURAH);
    let denied = [
        (user(Role::Passenger), AppError::Forbidden(DenyReason::MissingPermission)),
        (user(Role::Driver), AppError::Forbidden(DenyReason::MissingPermission)),
        (service(&[Permission::LineWrite]), AppError::Forbidden(DenyReason::MissingPermission)),
        (Actor::Anonymous, AppError::Unauthenticated(AuthFailure::Missing)),
    ];
    for (actor, expected) in denied {
        let err = n.stops.create(&actor, input(), &meta()).await.unwrap_err();
        assert_eq!(format!("{err:?}"), format!("{expected:?}"));
    }
    let key = service(&[Permission::StopWrite]);
    let stop = n.stops.create(&key, input(), &meta()).await.unwrap().stop;
    let update = UpdateStopInput { is_active: Some(false), ..UpdateStopInput::default() };
    n.stops.update(&key, stop.id, update, &meta()).await.unwrap();
    n.stops.delete(&key, stop.id, &meta()).await.unwrap();
}

#[tokio::test]
async fn inactive_stops_are_visible_to_writers_only() {
    let n = network();
    let admin = user(Role::Admin);
    let passenger = user(Role::Passenger);
    let active = n.stop("Grande Poste", GRANDE_POSTE).await;
    let hidden = n.stop("Tafourah", TAFOURAH).await;
    let update = UpdateStopInput { is_active: Some(false), ..UpdateStopInput::default() };
    n.stops.update(&admin, hidden, update, &meta()).await.unwrap();

    let ids = |page: crate::pagination::Page<StopView>| {
        page.items.into_iter().map(|v| v.stop.id).collect::<Vec<_>>()
    };
    let page = PageRequest::default();
    let public = n.stops.list(&Actor::Anonymous, StopListQuery::default(), page).await.unwrap();
    assert_eq!(ids(public), vec![active]);
    let all = n.stops.list(&admin, StopListQuery::default(), page).await.unwrap();
    assert_eq!(ids(all), vec![hidden, active], "newest first");
    let inactive = StopListQuery { is_active: Some(false), ..StopListQuery::default() };
    assert_eq!(ids(n.stops.list(&admin, inactive.clone(), page).await.unwrap()), vec![hidden]);
    let err = n.stops.list(&passenger, inactive.clone(), page).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(DenyReason::MissingPermission)));
    let err = n.stops.list(&Actor::Anonymous, inactive, page).await.unwrap_err();
    assert!(matches!(err, AppError::Unauthenticated(AuthFailure::Missing)));

    assert!(matches!(n.stops.get(&passenger, hidden).await, Err(AppError::NotFound("stop"))));
    assert!(!n.stops.get(&admin, hidden).await.unwrap().stop.is_active);
    assert!(n.stops.get(&Actor::Anonymous, active).await.is_ok());
    let nearby = NearbyQuery { lat: TAFOURAH.0, lng: TAFOURAH.1, ..NearbyQuery::default() };
    let found = n.stops.nearby(&admin, nearby).await.unwrap();
    let found: Vec<StopId> = found.iter().map(|s| s.view.stop.id).collect();
    assert_eq!(found, vec![active], "active only");
}

#[tokio::test]
async fn stop_lists_are_filtered_and_searched() {
    let n = network();
    let admin = user(Role::Admin);
    let martyrs = n.stop("Place des Martyrs", MARTYRS).await;
    let poste = n.stop("Grande Poste", GRANDE_POSTE).await;
    let update = UpdateStopInput { wilaya: Some("Alger".into()), ..UpdateStopInput::default() };
    n.stops.update(&admin, poste, update, &meta()).await.unwrap();
    let line = n.line("L1").await;
    n.replace(line.id, &[(martyrs, None)]).await.unwrap();

    let list = |query: StopListQuery| async {
        let page = n.stops.list(&Actor::Anonymous, query, PageRequest::default()).await?;
        AppResult::Ok(page.items.into_iter().map(|v| v.stop.id).collect::<Vec<_>>())
    };
    let q = |q: &str| StopListQuery { q: Some(q.into()), ..StopListQuery::default() };
    assert_eq!(list(q("MARTYR")).await.unwrap(), vec![martyrs]);
    assert_eq!(list(q("  poste ")).await.unwrap(), vec![poste]);
    assert_eq!(list(q("zz")).await.unwrap(), Vec::<StopId>::new());
    assert_eq!(codes(list(q(" a ")).await.unwrap_err()), vec![("q".into(), "too_short")]);
    assert_eq!(codes(list(q(&"a".repeat(101))).await.unwrap_err()), vec![("q".into(), "too_long")]);
    let wilaya = StopListQuery { wilaya: Some("alger".into()), ..StopListQuery::default() };
    assert_eq!(list(wilaya).await.unwrap(), vec![poste]);
    let served = StopListQuery { line_id: Some(line.id), ..StopListQuery::default() };
    assert_eq!(list(served.clone()).await.unwrap(), vec![martyrs]);

    // An inactive line serves no stop, except for line writers.
    let update = UpdateLineInput { is_active: Some(false), ..UpdateLineInput::default() };
    n.lines.update(&admin, line.id, update, &meta()).await.unwrap();
    assert_eq!(list(served.clone()).await.unwrap(), Vec::<StopId>::new());
    let page = n.stops.list(&admin, served, PageRequest::default()).await.unwrap();
    let ids: Vec<StopId> = page.items.into_iter().map(|v| v.stop.id).collect();
    assert_eq!(ids, vec![martyrs]);
}

#[tokio::test]
async fn nearby_stops_are_sorted_bounded_and_validated() {
    let n = network();
    let poste = n.stop("Grande Poste", GRANDE_POSTE).await;
    let tafourah = n.stop("Tafourah", TAFOURAH).await;
    let martyrs = n.stop("Place des Martyrs", MARTYRS).await;
    n.stop("Bab Ezzouar", BAB_EZZOUAR).await;
    let around = |radius_m, limit| NearbyQuery {
        lat: GRANDE_POSTE.0,
        lng: GRANDE_POSTE.1 + 0.0001,
        radius_m,
        limit,
    };
    let found = n.stops.nearby(&Actor::Anonymous, around(Some(2000), None)).await.unwrap();
    let ids: Vec<StopId> = found.iter().map(|s| s.view.stop.id).collect();
    assert_eq!(ids, vec![poste, tafourah, martyrs]);
    assert!(found.windows(2).all(|w| w[0].distance_m <= w[1].distance_m));
    assert!(found[0].distance_m < 20.0, "{}", found[0].distance_m);
    let closest = n.stops.nearby(&Actor::Anonymous, around(Some(2000), Some(1))).await.unwrap();
    assert_eq!(closest.len(), 1);
    let default_radius = n.stops.nearby(&Actor::Anonymous, around(None, None)).await.unwrap();
    assert_eq!(default_radius.len(), 2, "500 m by default");

    let bad = NearbyQuery { lat: 95.0, lng: 3.0, radius_m: Some(9), limit: Some(51) };
    assert_eq!(
        codes(n.stops.nearby(&Actor::Anonymous, bad).await.unwrap_err()),
        vec![
            ("lat".into(), "out_of_range"),
            ("radius_m".into(), "out_of_range"),
            ("limit".into(), "out_of_range"),
        ]
    );
    let too_far = NearbyQuery { radius_m: Some(5001), ..around(None, None) };
    assert!(n.stops.nearby(&Actor::Anonymous, too_far).await.is_err());
}

#[tokio::test]
async fn stop_updates_are_partial_and_empty_updates_are_not_audited() {
    let n = network();
    let admin = user(Role::Admin);
    let id = n.stop("Tafourah", TAFOURAH).await;
    n.f.clock.advance(std::time::Duration::from_secs(60));
    let unchanged = n.stops.update(&admin, id, UpdateStopInput::default(), &meta()).await.unwrap();
    assert_eq!(unchanged.stop.updated_at, unchanged.stop.created_at);
    let update = UpdateStopInput {
        name: Some("Tafourah – Grande Poste".into()),
        location: Some(GRANDE_POSTE),
        description: Some(String::new()),
        features: Some(vec![]),
        ..UpdateStopInput::default()
    };
    let stop = n.stops.update(&admin, id, update, &meta()).await.unwrap().stop;
    assert_eq!(stop.name.as_str(), "Tafourah – Grande Poste");
    assert_eq!((stop.location.lat(), stop.location.lng()), GRANDE_POSTE);
    assert_eq!(stop.updated_at, n.f.clock.now());
    assert_eq!(audit_actions(&n).await, ["stop.create", "stop.update"]);

    let bad = UpdateStopInput {
        name: Some(String::new()),
        location: Some((0.0, 181.0)),
        ..UpdateStopInput::default()
    };
    assert_eq!(
        codes(n.stops.update(&admin, id, bad, &meta()).await.unwrap_err()),
        vec![("name".into(), "required"), ("location.lng".into(), "out_of_range")]
    );
    let activate = UpdateStopInput { is_active: Some(true), ..UpdateStopInput::default() };
    let missing = n.stops.update(&admin, StopId::generate(), activate, &meta()).await;
    assert!(matches!(missing, Err(AppError::NotFound("stop"))));
}

#[tokio::test]
async fn stops_in_use_cannot_be_deleted() {
    let n = network();
    let admin = user(Role::Admin);
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let line = n.line("L1").await;
    n.replace(line.id, &[(stop, None)]).await.unwrap();
    let err = n.stops.delete(&admin, stop, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::StopInUse)));
    n.replace(line.id, &[]).await.unwrap();
    n.stops.delete(&admin, stop, &meta()).await.unwrap();
    assert!(matches!(n.stops.get(&admin, stop).await, Err(AppError::NotFound("stop"))));
    assert!(matches!(n.stops.delete(&admin, stop, &meta()).await, Err(AppError::NotFound("stop"))));
    assert_eq!(audit_actions(&n).await.last().map(String::as_str), Some("stop.delete"));
}

#[tokio::test]
async fn stop_photos_are_claimed_replaced_and_deleted_by_jobs() {
    let n = network();
    let admin = user(Role::Admin);
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let upload = |actor: &Actor| {
        let uploads = n.f.uploads();
        let actor = actor.clone();
        let storage = n.f.storage.clone();
        async move {
            let requested = uploads.request(&actor, UploadPurpose::StopPhoto, "image/png", 10);
            let requested = requested.await.unwrap();
            storage.put(&requested.upload.object_key, 10, "image/png");
            requested.upload
        }
    };

    let first = upload(&admin).await;
    let view = n.stops.set_photo(&admin, stop, first.id, &meta()).await.unwrap();
    assert_eq!(view.stop.photo_key.as_deref(), Some(first.object_key.as_str()));
    assert!(view.photo_url.unwrap().contains(&first.object_key));
    assert_eq!(n.f.store.upload(first.id).unwrap().status, UploadStatus::Attached);
    assert!(n.f.store.drain_outbox().is_empty(), "nothing replaced");

    let reused = n.stops.set_photo(&admin, stop, first.id, &meta()).await.unwrap_err();
    assert_eq!(codes(reused), vec![("upload_id".into(), "invalid_upload")]);
    let second = upload(&admin).await;
    n.stops.set_photo(&admin, stop, second.id, &meta()).await.unwrap();
    let jobs = n.f.store.drain_outbox();
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0].job, Job::StorageDeleteObject { key: first.object_key.clone() });

    n.stops.remove_photo(&admin, stop, &meta()).await.unwrap();
    let jobs = n.f.store.drain_outbox();
    assert_eq!(jobs[0].job, Job::StorageDeleteObject { key: second.object_key.clone() });
    n.stops.remove_photo(&admin, stop, &meta()).await.unwrap();
    assert!(n.f.store.drain_outbox().is_empty(), "removing twice is a no-op");

    let third = upload(&admin).await;
    n.stops.set_photo(&admin, stop, third.id, &meta()).await.unwrap();
    n.stops.delete(&admin, stop, &meta()).await.unwrap();
    let jobs = n.f.store.drain_outbox();
    assert_eq!(jobs[0].job, Job::StorageDeleteObject { key: third.object_key.clone() });
    assert_eq!(
        audit_actions(&n).await,
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
async fn stop_photos_need_a_human_writer_and_storage() {
    let n = network();
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let key = service(&[Permission::StopWrite]);
    let err = n.stops.set_photo(&key, stop, UploadId::generate(), &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(DenyReason::MissingPermission)));
    n.stops.remove_photo(&key, stop, &meta()).await.unwrap();
    let driver = user(Role::Driver);
    let err = n.stops.set_photo(&driver, stop, UploadId::generate(), &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(_)));
    let admin = user(Role::Admin);
    let err = n.stops.set_photo(&admin, StopId::generate(), UploadId::generate(), &meta()).await;
    assert!(matches!(err, Err(AppError::NotFound("stop"))));

    let without =
        StopService::new(n.f.store.clone(), n.f.uploads_without_storage(), n.f.clock.clone());
    let err = without.set_photo(&admin, stop, UploadId::generate(), &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Unavailable("storage")));
    let err = without.remove_photo(&admin, stop, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Unavailable("storage")));
}

#[tokio::test]
async fn lines_of_a_stop_are_sorted_by_code_and_hide_inactive_lines() {
    let n = network();
    let admin = user(Role::Admin);
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let other = n.stop("Tafourah", TAFOURAH).await;
    for code in ["L3", "L1", "L2"] {
        let line = n.line(code).await;
        n.replace(line.id, &[(other, None), (stop, Some(90))]).await.unwrap();
        if code == "L2" {
            let update = UpdateLineInput { is_active: Some(false), ..UpdateLineInput::default() };
            n.lines.update(&admin, line.id, update, &meta()).await.unwrap();
        }
    }
    let codes_of =
        |lines: Vec<Line>| lines.into_iter().map(|l| l.code.to_string()).collect::<Vec<_>>();
    assert_eq!(codes_of(n.stops.lines(&Actor::Anonymous, stop).await.unwrap()), ["L1", "L3"]);
    assert_eq!(codes_of(n.stops.lines(&admin, stop).await.unwrap()), ["L1", "L2", "L3"]);
    let missing = n.stops.lines(&Actor::Anonymous, StopId::generate()).await;
    assert!(matches!(missing, Err(AppError::NotFound("stop"))));
}

// --- Lines ---------------------------------------------------------------------------------------

#[tokio::test]
async fn lines_are_validated_and_codes_are_unique_ignoring_case() {
    let n = network();
    let admin = user(Role::Admin);
    let input = CreateLineInput {
        code: " l1-bis ".into(),
        name: "Martyrs – Bab Ezzouar".into(),
        color: Some("#ff8800".into()),
        frequency_minutes: Some(12),
        fare_dza: Some(0),
        ..CreateLineInput::default()
    };
    let line = n.lines.create(&admin, input, &meta()).await.unwrap();
    assert_eq!((line.code.as_str(), line.color.as_str()), ("L1-BIS", "#FF8800"));
    assert_eq!(line.frequency_minutes.map(|f| f.minutes()), Some(12));
    assert_eq!(line.fare_dza.map(|f| f.dzd()), Some(0));
    assert!(line.is_active && !line.has_route && line.stops_count == 0);

    let duplicate =
        CreateLineInput { code: "L1-bis".into(), name: "Autre".into(), ..Default::default() };
    let err = n.lines.create(&admin, duplicate, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::LineCodeTaken)));

    let bad = CreateLineInput {
        code: "L 2".into(),
        name: String::new(),
        color: Some("red".into()),
        frequency_minutes: Some(0),
        fare_dza: Some(-5),
        ..CreateLineInput::default()
    };
    assert_eq!(
        codes(n.lines.create(&admin, bad, &meta()).await.unwrap_err()),
        vec![
            ("code".into(), "invalid_format"),
            ("name".into(), "required"),
            ("color".into(), "invalid_format"),
            ("frequency_minutes".into(), "out_of_range"),
            ("fare_dza".into(), "out_of_range"),
        ]
    );
    let default_color = n.line("L2").await;
    assert_eq!(default_color.color.as_str(), "#000000");
    assert_eq!(audit_actions(&n).await, ["line.create", "line.create"]);
}

#[tokio::test]
async fn line_updates_clear_nullable_fields_and_toggle_activity() {
    let n = network();
    let admin = user(Role::Admin);
    let input = CreateLineInput {
        code: "L1".into(),
        name: "Ligne 1".into(),
        frequency_minutes: Some(10),
        fare_dza: Some(30),
        ..CreateLineInput::default()
    };
    let line = n.lines.create(&admin, input, &meta()).await.unwrap();
    let update = UpdateLineInput {
        frequency_minutes: Some(None),
        fare_dza: Some(Some(50)),
        is_active: Some(false),
        ..UpdateLineInput::default()
    };
    let updated = n.lines.update(&admin, line.id, update, &meta()).await.unwrap();
    assert_eq!(updated.frequency_minutes, None);
    assert_eq!(updated.fare_dza.map(|f| f.dzd()), Some(50));
    assert!(!updated.is_active);
    let hidden = n.lines.get(&Actor::Anonymous, line.id).await;
    assert!(matches!(hidden, Err(AppError::NotFound("line"))));
    assert!(n.lines.get(&admin, line.id).await.is_ok());

    let bad = UpdateLineInput {
        color: Some("#12345".into()),
        fare_dza: Some(Some(-1)),
        ..UpdateLineInput::default()
    };
    assert_eq!(
        codes(n.lines.update(&admin, line.id, bad, &meta()).await.unwrap_err()),
        vec![("color".into(), "invalid_format"), ("fare_dza".into(), "out_of_range")]
    );
    let passenger = user(Role::Passenger);
    let err = n.lines.update(&passenger, line.id, UpdateLineInput::default(), &meta()).await;
    assert!(matches!(err, Err(AppError::Forbidden(_))));
}

#[tokio::test]
async fn stop_lists_are_replaced_atomically_with_validation() {
    let n = network();
    let (a, b, c) = (
        n.stop("Place des Martyrs", MARTYRS).await,
        n.stop("Grande Poste", GRANDE_POSTE).await,
        n.stop("Tafourah", TAFOURAH).await,
    );
    let line = n.line("L1").await;
    let stops = n.replace(line.id, &[(a, None), (b, Some(240)), (c, None)]).await.unwrap();
    assert_eq!(order(&stops), vec![a, b, c]);
    assert_eq!(stops.iter().map(|s| s.position).collect::<Vec<_>>(), vec![0, 1, 2]);
    assert_eq!(stops[0].distance_from_previous_m, None);
    let ab = stops[1].distance_from_previous_m.unwrap();
    assert!((1_300.0..1_500.0).contains(&ab), "{ab}");
    assert_eq!(stops[1].time_from_previous_s, Some(240));
    assert_eq!(n.lines.get(&Actor::Anonymous, line.id).await.unwrap().stops_count, 3);

    let reversed = n.replace(line.id, &[(c, None), (b, None), (a, Some(300))]).await.unwrap();
    assert_eq!(order(&reversed), vec![c, b, a]);
    assert_eq!(n.lines.stops(&Actor::Anonymous, line.id).await.unwrap(), reversed);

    let unknown = StopId::generate();
    let err = n.replace(line.id, &[(a, Some(5)), (b, Some(-1)), (a, None)]).await.unwrap_err();
    assert_eq!(
        codes(err),
        vec![
            ("stops[1].time_from_previous_s".into(), "out_of_range"),
            ("stops[2].stop_id".into(), "duplicate"),
            ("stops[0].time_from_previous_s".into(), "not_allowed"),
        ]
    );
    let err = n.replace(line.id, &[(a, None), (unknown, None)]).await.unwrap_err();
    assert_eq!(codes(err), vec![("stops[1].stop_id".into(), "unknown_reference")]);
    let too_many: Vec<(StopId, Option<i64>)> =
        (0..201).map(|_| (StopId::generate(), None)).collect();
    let err = n.replace(line.id, &too_many).await.unwrap_err();
    assert_eq!(codes(err), vec![("stops".into(), "out_of_range")]);
    let missing = n.replace(LineId::generate(), &[(a, None)]).await;
    assert!(matches!(missing, Err(AppError::NotFound("line"))));
    let current = n.lines.stops(&Actor::Anonymous, line.id).await.unwrap();
    assert_eq!(order(&current), vec![c, b, a], "unchanged");
    assert!(n.replace(line.id, &[]).await.unwrap().is_empty());
    assert_eq!(
        audit_actions(&n).await.iter().filter(|a| *a == "line.stops.replace").count(),
        3,
        "only successful replacements are audited"
    );
}

#[tokio::test]
async fn stops_are_inserted_and_removed_with_shifts() {
    let n = network();
    let admin = user(Role::Admin);
    let (a, b, c, d) = (
        n.stop("Place des Martyrs", MARTYRS).await,
        n.stop("Grande Poste", GRANDE_POSTE).await,
        n.stop("Tafourah", TAFOURAH).await,
        n.stop("Bab Ezzouar", BAB_EZZOUAR).await,
    );
    let line = n.line("L1").await.id;
    let add = |stop_id, position, time_from_previous_s| AddLineStopInput {
        stop_id,
        position,
        time_from_previous_s,
    };
    n.lines.add_stop(&admin, line, add(b, None, None), &meta()).await.unwrap();
    n.lines.add_stop(&admin, line, add(d, None, Some(600)), &meta()).await.unwrap();
    let stops = n.lines.add_stop(&admin, line, add(a, Some(0), None), &meta()).await.unwrap();
    assert_eq!(order(&stops), vec![a, b, d]);
    let stops = n.lines.add_stop(&admin, line, add(c, Some(2), Some(60)), &meta()).await.unwrap();
    assert_eq!(order(&stops), vec![a, b, c, d]);
    assert_eq!(
        n.f.store
            .line_stop_entries(line)
            .iter()
            .map(|e| e.time_from_previous_s)
            .collect::<Vec<_>>(),
        vec![None, None, Some(60), None],
        "the stop after an insertion loses its (now unknown) segment time"
    );

    let err = n.lines.add_stop(&admin, line, add(b, None, None), &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::StopAlreadyOnLine)));
    let e = n.stop("Ben Aknoun", (36.7570, 3.0130)).await;
    let err = n.lines.add_stop(&admin, line, add(e, Some(5), None), &meta()).await.unwrap_err();
    assert_eq!(codes(err), vec![("position".into(), "out_of_range")]);
    let err = n.lines.add_stop(&admin, line, add(e, Some(0), Some(30)), &meta()).await.unwrap_err();
    assert_eq!(codes(err), vec![("time_from_previous_s".into(), "not_allowed")]);
    let err = n.lines.add_stop(&admin, line, add(StopId::generate(), None, None), &meta()).await;
    assert_eq!(codes(err.unwrap_err()), vec![("stop_id".into(), "unknown_reference")]);
    let empty = n.line("L2").await.id;
    let err = n.lines.add_stop(&admin, empty, add(e, None, Some(30)), &meta()).await.unwrap_err();
    assert_eq!(codes(err), vec![("time_from_previous_s".into(), "not_allowed")], "first stop");

    let stops = n.lines.remove_stop(&admin, line, b, &meta()).await.unwrap();
    assert_eq!(order(&stops), vec![a, c, d]);
    assert_eq!(stops.iter().map(|s| s.position).collect::<Vec<_>>(), vec![0, 1, 2]);
    let stops = n.lines.remove_stop(&admin, line, a, &meta()).await.unwrap();
    assert_eq!(order(&stops), vec![c, d]);
    assert_eq!((stops[0].distance_from_previous_m, stops[0].time_from_previous_s), (None, None));
    assert!(stops[1].distance_from_previous_m.unwrap() > 10_000.0);
    let err = n.lines.remove_stop(&admin, line, a, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("line_stop")));
}

#[tokio::test]
async fn removing_a_stop_merges_known_segment_times() {
    let n = network();
    let (a, b, c) = (
        n.stop("Place des Martyrs", MARTYRS).await,
        n.stop("Grande Poste", GRANDE_POSTE).await,
        n.stop("Tafourah", TAFOURAH).await,
    );
    let line = n.line("L1").await.id;
    n.replace(line, &[(a, None), (b, Some(120)), (c, Some(45))]).await.unwrap();
    let stops = n.lines.remove_stop(&user(Role::Admin), line, b, &meta()).await.unwrap();
    assert_eq!(stops[1].time_from_previous_s, Some(165));
}

#[tokio::test]
async fn routes_are_validated_and_hidden_with_their_line() {
    let n = network();
    let admin = user(Role::Admin);
    let line = n.line("L1").await.id;
    let err = n.lines.route(&Actor::Anonymous, line).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("route")));
    let positions = [[3.0603, 36.7856], [3.0588, 36.7731], [3.0607, 36.7725]];
    let route = n.lines.set_route(&admin, line, &positions, &meta()).await.unwrap();
    assert_eq!(route.points().len(), 3);
    assert_eq!(n.lines.route(&Actor::Anonymous, line).await.unwrap(), route);
    assert!(n.lines.get(&Actor::Anonymous, line).await.unwrap().has_route);

    let err = n.lines.set_route(&admin, line, &[[3.0, 36.0]], &meta()).await.unwrap_err();
    assert_eq!(codes(err), vec![("coordinates".into(), "out_of_range")]);
    let broken = [[3.0, 36.0], [3.0, 36.0], [181.0, 0.0]];
    let err = n.lines.set_route(&admin, line, &broken, &meta()).await;
    assert_eq!(
        codes(err.unwrap_err()),
        vec![("coordinates[1]".into(), "duplicate"), ("coordinates[2][0]".into(), "out_of_range")]
    );
    let err = n.lines.set_route(&admin, LineId::generate(), &positions, &meta()).await;
    assert!(matches!(err, Err(AppError::NotFound("line"))));

    n.lines.delete_route(&admin, line, &meta()).await.unwrap();
    assert!(matches!(n.lines.route(&admin, line).await, Err(AppError::NotFound("route"))));
    n.lines.delete_route(&admin, line, &meta()).await.unwrap();
    assert_eq!(
        audit_actions(&n).await,
        ["line.create", "line.route.set", "line.route.delete"],
        "removing a missing route is not audited"
    );
    let err = n.lines.set_route(&user(Role::Driver), line, &positions, &meta()).await;
    assert!(matches!(err, Err(AppError::Forbidden(_))), "legacy L-04");
}

#[tokio::test]
async fn deleting_a_line_cascades_its_stops_and_schedules() {
    let n = network();
    let admin = user(Role::Admin);
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let line = n.line("L1").await.id;
    n.replace(line, &[(stop, None)]).await.unwrap();
    let input = schedule_input(1, "06:00", "09:00");
    let schedule = n.schedules.create(&admin, line, input, &meta()).await.unwrap();
    n.lines.delete(&admin, line, &meta()).await.unwrap();
    assert!(matches!(n.lines.get(&admin, line).await, Err(AppError::NotFound("line"))));
    let gone = n.schedules.get(&admin, schedule.id).await;
    assert!(matches!(gone, Err(AppError::NotFound("schedule"))));
    n.stops.delete(&admin, stop, &meta()).await.unwrap();
    assert!(matches!(n.lines.delete(&admin, line, &meta()).await, Err(AppError::NotFound("line"))));
}

#[tokio::test]
async fn line_lists_search_code_and_name_and_filter_by_stop() {
    let n = network();
    let admin = user(Role::Admin);
    let stop = n.stop("Grande Poste", GRANDE_POSTE).await;
    let l1 = n.line("L1").await;
    let name = "Bab Ezzouar Express".into();
    let input = CreateLineInput { code: "B12".into(), name, ..CreateLineInput::default() };
    let b12 = n.lines.create(&admin, input, &meta()).await.unwrap();
    n.replace(l1.id, &[(stop, None)]).await.unwrap();
    let list = |query: LineListQuery| async {
        let page = n.lines.list(&Actor::Anonymous, query, PageRequest::default()).await.unwrap();
        page.items.into_iter().map(|l| l.id).collect::<Vec<_>>()
    };
    let q = |q: &str| LineListQuery { q: Some(q.into()), ..LineListQuery::default() };
    assert_eq!(list(q("b12")).await, vec![b12.id]);
    assert_eq!(list(q("express")).await, vec![b12.id]);
    assert_eq!(list(q("ligne")).await, vec![l1.id]);
    assert_eq!(list(LineListQuery::default()).await, vec![b12.id, l1.id]);
    let serving = LineListQuery { stop_id: Some(stop), ..LineListQuery::default() };
    assert_eq!(list(serving).await, vec![l1.id]);
}

// --- Schedules -----------------------------------------------------------------------------------

fn schedule_input(day: i64, start: &str, end: &str) -> CreateScheduleInput {
    CreateScheduleInput {
        day_of_week: day,
        start_time: start.into(),
        end_time: end.into(),
        frequency_minutes: 10,
        is_active: None,
    }
}

#[tokio::test]
async fn schedules_are_validated_and_may_not_overlap() {
    let n = network();
    let admin = user(Role::Admin);
    let line = n.line("L1").await.id;
    let request = meta();
    let create = |input| n.schedules.create(&admin, line, input, &request);
    let morning = create(schedule_input(1, "06:00", "09:00")).await.unwrap();
    assert_eq!((morning.day.iso(), morning.window.start().to_string()), (1, "06:00".to_owned()));
    create(schedule_input(1, "09:00", "12:00")).await.expect("adjacent windows do not overlap");
    create(schedule_input(2, "07:00", "08:00")).await.expect("another day");
    let err = create(schedule_input(1, "08:59", "09:30")).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::ScheduleOverlap)));
    let inactive =
        CreateScheduleInput { is_active: Some(false), ..schedule_input(1, "07:00", "08:00") };
    let inactive = create(inactive).await.expect("inactive schedules do not conflict");

    let err = create(schedule_input(8, "9:00", "08:00")).await.unwrap_err();
    assert_eq!(
        codes(err),
        vec![("day_of_week".into(), "out_of_range"), ("start_time".into(), "invalid_format")]
    );
    let err = create(schedule_input(3, "10:00", "10:00")).await.unwrap_err();
    assert_eq!(codes(err), vec![("end_time".into(), "must_be_after")]);
    let bad_frequency =
        CreateScheduleInput { frequency_minutes: 1441, ..schedule_input(3, "10:00", "11:00") };
    let err = create(bad_frequency).await.unwrap_err();
    assert_eq!(codes(err), vec![("frequency_minutes".into(), "out_of_range")]);
    let input = schedule_input(4, "06:00", "07:00");
    let missing = n.schedules.create(&admin, LineId::generate(), input, &meta()).await;
    assert!(matches!(missing, Err(AppError::NotFound("line"))));

    // Activating the inactive schedule would make it overlap the morning one.
    let activate = UpdateScheduleInput { is_active: Some(true), ..UpdateScheduleInput::default() };
    let err = n.schedules.update(&admin, inactive.id, activate, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Conflict(ConflictKind::ScheduleOverlap)));
    let earlier = UpdateScheduleInput {
        start_time: Some("05:00".into()),
        end_time: Some("06:00".into()),
        is_active: Some(true),
        ..UpdateScheduleInput::default()
    };
    let moved = n.schedules.update(&admin, inactive.id, earlier, &meta()).await.unwrap();
    assert!(moved.is_active);
    assert_eq!(moved.window.end().to_string(), "06:00");
    let backwards = UpdateScheduleInput { start_time: Some("07:00".into()), ..Default::default() };
    let err = n.schedules.update(&admin, moved.id, backwards, &meta()).await.unwrap_err();
    assert_eq!(codes(err), vec![("end_time".into(), "must_be_after")]);
    let actions = audit_actions(&n).await;
    assert_eq!(actions.iter().filter(|a| *a == "schedule.create").count(), 4);
    assert_eq!(actions.last().map(String::as_str), Some("schedule.update"));
}

#[tokio::test]
async fn schedules_are_listed_in_order_with_visibility_rules() {
    let n = network();
    let admin = user(Role::Admin);
    let line = n.line("L1").await.id;
    let request = meta();
    let create = |input| n.schedules.create(&admin, line, input, &request);
    let tuesday = create(schedule_input(2, "06:00", "09:00")).await.unwrap();
    let monday_late = create(schedule_input(1, "17:00", "20:00")).await.unwrap();
    let monday = create(schedule_input(1, "06:00", "09:00")).await.unwrap();
    let hidden =
        CreateScheduleInput { is_active: Some(false), ..schedule_input(1, "07:00", "08:00") };
    let hidden = create(hidden).await.unwrap();

    let ids = |s: Vec<Schedule>| s.into_iter().map(|s| s.id).collect::<Vec<_>>();
    let public = n.schedules.list_for_line(&Actor::Anonymous, line).await.unwrap();
    assert_eq!(ids(public), vec![monday.id, monday_late.id, tuesday.id]);
    let all = n.schedules.list_for_line(&admin, line).await.unwrap();
    assert_eq!(ids(all), vec![monday.id, hidden.id, monday_late.id, tuesday.id]);
    let err = n.schedules.get(&Actor::Anonymous, hidden.id).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("schedule")));
    assert!(n.schedules.get(&admin, hidden.id).await.is_ok());
    assert!(n.schedules.get(&Actor::Anonymous, monday.id).await.is_ok());

    let deactivate = UpdateLineInput { is_active: Some(false), ..UpdateLineInput::default() };
    n.lines.update(&admin, line, deactivate, &meta()).await.unwrap();
    let err = n.schedules.list_for_line(&Actor::Anonymous, line).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("line")));
    let err = n.schedules.get(&Actor::Anonymous, monday.id).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("schedule")), "the line is inactive");
    let key = service(&[Permission::ScheduleWrite]);
    assert_eq!(n.schedules.list_for_line(&key, line).await.unwrap().len(), 4);

    n.schedules.delete(&admin, monday.id, &meta()).await.unwrap();
    let err = n.schedules.delete(&admin, monday.id, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("schedule")));
    let err = n.schedules.delete(&user(Role::Passenger), tuesday.id, &meta()).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(_)));
    let err = n.schedules.get(&Actor::Anonymous, ScheduleId::generate()).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("schedule")));
}
