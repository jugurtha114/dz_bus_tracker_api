//! Driver use-cases against the in-memory ports: applications, the driver's own profile,
//! reviews through the state machine, visibility, outbox jobs and the notification jobs.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::Lang;
use dz_domain::authz::{Actor, Permission, PermissionSet};
use dz_domain::driver::{Driver, DriverStatus, DriverStatusChange, NationalIdNumber, StatusReason};
use dz_domain::ids::{ApiKeyId, DriverId, SessionId, UploadId, UserId};
use dz_domain::upload::{UploadPurpose, UploadStatus};
use dz_domain::user::{Email, PersonName, Role};

use super::ports::{AccountSummary, DriverFilter, DriverPatch, DriverRecord, NewDriver};
use super::*;
use crate::jobs::{JobRunner, JobSettings};
use crate::ports::{AuditActor, EmailMessage, NewUser, OutboxJob, UserRepository};
use crate::testing::{Fakes, InMemoryStore};

const PNG: &str = "image/png";
const ID_CARD: &str = "123456789012345678";

async fn user_with(f: &Fakes, role: Role, lang: Lang) -> Actor {
    let id = UserId::generate();
    let new = NewUser {
        id,
        email: Email::parse(&format!("{id}@example.dz")).unwrap(),
        password_hash: "plain$x".into(),
        role,
        first_name: PersonName::parse("Amine").unwrap(),
        last_name: PersonName::parse("Benali").unwrap(),
        phone_number: None,
        language: lang,
        created_at: f.clock.now(),
    };
    UserRepository::insert(&*f.store, new).await.unwrap();
    Actor::User { id, role, session_id: SessionId::generate() }
}

async fn user(f: &Fakes, role: Role) -> Actor {
    user_with(f, role, Lang::Fr).await
}

async fn role_of(f: &Fakes, actor: &Actor) -> Role {
    UserRepository::find(&*f.store, uid(actor)).await.unwrap().unwrap().role
}

fn service(f: &Fakes) -> DriverService {
    DriverService::new(f.store.clone(), f.uploads(), f.clock.clone())
}

fn uid(actor: &Actor) -> UserId {
    actor.user_id().unwrap()
}

fn codes(err: AppError) -> Vec<(String, &'static str)> {
    match err {
        AppError::Validation(v) => {
            v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
        }
        other => panic!("expected a validation error, got {other:?}"),
    }
}

fn conflict(err: AppError) -> ConflictKind {
    match err {
        AppError::Conflict(kind) => kind,
        other => panic!("expected a conflict, got {other:?}"),
    }
}

/// Requests an upload and stores its object as the client would.
async fn uploaded(f: &Fakes, actor: &Actor, purpose: UploadPurpose) -> UploadId {
    let requested = f.uploads().request(actor, purpose, PNG, 100).await.unwrap();
    f.storage.put(&requested.upload.object_key, 100, PNG);
    requested.upload.id
}

async fn application(f: &Fakes, actor: &Actor, id_card: &str, licence: &str) -> ApplyInput {
    ApplyInput {
        phone_number: "0555123456".into(),
        id_card_number: id_card.into(),
        id_card_photo_upload_id: uploaded(f, actor, UploadPurpose::DriverIdCard).await,
        driver_license_number: licence.into(),
        driver_license_photo_upload_id: uploaded(f, actor, UploadPurpose::DriverLicense).await,
        years_of_experience: 7,
    }
}

/// A passenger with a pending application.
async fn applicant(f: &Fakes, id_card: &str, licence: &str) -> (Actor, DriverView) {
    let actor = user(f, Role::Passenger).await;
    let input = application(f, &actor, id_card, licence).await;
    let view = service(f).apply(&actor, input).await.unwrap();
    (actor, view)
}

fn kinds(jobs: &[OutboxJob]) -> Vec<&'static str> {
    jobs.iter().map(|j| j.job.kind()).collect()
}

async fn review(f: &Fakes, admin: &Actor, id: DriverId, review: Review) -> AppResult<DriverView> {
    service(f).review(admin, id, review, &RequestMeta::default()).await
}

/// An approval of the profile `id` as it is now, as sent by a reviewer who just read it.
async fn approval(f: &Fakes, id: DriverId) -> Review {
    let current = DriverRepository::find(&*f.store, id).await.unwrap().unwrap();
    Review::Approve { expected_updated_at: current.driver.updated_at }
}

async fn history(f: &Fakes, actor: &Actor, id: DriverId) -> Vec<DriverStatusChange> {
    service(f).status_history(actor, id, PageRequest::default()).await.unwrap().items
}

fn runner(f: &Fakes) -> JobRunner {
    JobRunner {
        users: f.store.clone(),
        sessions: f.store.clone(),
        resets: f.store.clone(),
        uploads: f.store.clone(),
        drivers: f.store.clone(),
        storage: Some(f.storage.clone()),
        mailer: f.mailer.clone(),
        queue: f.queue.clone(),
        clock: f.clock.clone(),
        settings: JobSettings {
            password_reset_ttl: Duration::from_secs(3600),
            password_reset_url: "https://app.example/reset".into(),
            auth_retention: Duration::from_secs(86_400),
            job_retention: Duration::from_secs(86_400),
            upload_purge_grace: Duration::from_secs(3600),
        },
    }
}

#[tokio::test]
async fn an_application_creates_a_pending_profile_for_the_caller_atomically() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let input = application(&f, &actor, " 1234 5678 9012 3456 78", "dz-42").await;
    let (id_card_upload, licence_upload) =
        (input.id_card_photo_upload_id, input.driver_license_photo_upload_id);
    let view = service(&f).apply(&actor, input).await.unwrap();

    let driver = &view.record.driver;
    assert_eq!(driver.user_id, uid(&actor), "bound to the caller (L-02)");
    assert_eq!(view.record.user.id, uid(&actor));
    assert_eq!(driver.status, DriverStatus::Pending);
    let numbers = (driver.id_card_number.as_str(), driver.driver_license_number.as_str());
    assert_eq!(numbers, (ID_CARD, "DZ-42"));
    assert_eq!(driver.phone_number.as_str(), "+213555123456");
    assert_eq!(driver.years_of_experience.years(), 7);
    assert!(!driver.is_available, "only approved drivers are available");
    assert_eq!(driver.rating(), None);
    assert_eq!(driver.status_changed_at, f.clock.now());
    let documents = [
        (id_card_upload, &driver.id_card_photo_key),
        (licence_upload, &driver.driver_license_photo_key),
    ];
    for (upload, key) in documents {
        let stored = f.store.upload(upload).unwrap();
        assert_eq!(stored.status, UploadStatus::Attached);
        assert_eq!(&stored.object_key, key);
    }
    let url = view.id_card_photo_url.as_deref().unwrap();
    assert!(url.contains(&driver.id_card_photo_key), "documents are presigned for the owner");
    assert!(view.driver_license_photo_url.is_some());

    let entries = history(&f, &actor, driver.id).await;
    assert_eq!(entries.len(), 1);
    assert_eq!((entries[0].from, entries[0].to), (None, DriverStatus::Pending));
    assert_eq!(entries[0].changed_by, Some(uid(&actor)));

    let jobs = f.store.drain_outbox();
    assert_eq!(kinds(&jobs), ["driver_status_changed", "driver_review_requested"]);
    let told = Job::DriverStatusChanged { driver_id: driver.id, status: DriverStatus::Pending };
    assert_eq!(jobs[0].job, told);
    // No dedup key: a running job may be dropping a stale request (see `notifications`).
    assert_eq!(jobs[1].options.dedup_key, None, "every review request is delivered");
    assert_eq!(f.store.audit_len(), 0, "self-service is recorded in the history, not audited");
}

#[tokio::test]
async fn applications_are_validated_and_documents_checked_together() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let drivers = service(&f);
    let bad = ApplyInput {
        phone_number: "0215123456".into(),
        id_card_number: "12345".into(),
        id_card_photo_upload_id: UploadId::generate(),
        driver_license_number: "AB 12".into(),
        driver_license_photo_upload_id: UploadId::generate(),
        years_of_experience: 61,
    };
    assert_eq!(
        codes(drivers.apply(&actor, bad).await.unwrap_err()),
        vec![
            ("phone_number".into(), "invalid_phone"),
            ("id_card_number".into(), "invalid_format"),
            ("driver_license_number".into(), "invalid_format"),
            ("years_of_experience".into(), "out_of_range"),
        ]
    );

    // Unknown uploads, or uploads for the wrong purpose, are reported on both fields at once.
    let mut input = application(&f, &actor, ID_CARD, "L-1").await;
    std::mem::swap(&mut input.id_card_photo_upload_id, &mut input.driver_license_photo_upload_id);
    assert_eq!(
        codes(drivers.apply(&actor, input.clone()).await.unwrap_err()),
        vec![
            ("id_card_photo_upload_id".into(), "invalid_upload"),
            ("driver_license_photo_upload_id".into(), "invalid_upload"),
        ]
    );
    // Someone else's upload is unusable too.
    let other = user(&f, Role::Passenger).await;
    input.id_card_photo_upload_id = uploaded(&f, &other, UploadPurpose::DriverIdCard).await;
    input.driver_license_photo_upload_id = uploaded(&f, &actor, UploadPurpose::DriverLicense).await;
    assert_eq!(
        codes(drivers.apply(&actor, input).await.unwrap_err()),
        vec![("id_card_photo_upload_id".into(), "invalid_upload")]
    );
    assert!(f.store.find_by_user(uid(&actor)).await.unwrap().is_none(), "nothing was created");
}

#[tokio::test]
async fn only_humans_with_driver_apply_can_apply_and_only_once() {
    let f = Fakes::default();
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let again = application(&f, &actor, "111111111111111111", "L-2").await;
    let err = service(&f).apply(&actor, again).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::DriverProfileExists);

    // The documents of another applicant must be their own.
    let other = user(&f, Role::Passenger).await;
    let same_card = application(&f, &other, ID_CARD, "L-2").await;
    let err = service(&f).apply(&other, same_card).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::IdCardTaken);
    let same_licence = application(&f, &other, "111111111111111111", "l-1").await;
    let err = service(&f).apply(&other, same_licence).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::LicenseTaken, "licence numbers ignore case");

    let admin = user(&f, Role::Admin).await;
    let input = application(&f, &other, "222222222222222222", "L-3").await;
    let err = service(&f).apply(&admin, input.clone()).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(_)));
    let err = service(&f).apply(&Actor::Anonymous, input.clone()).await.unwrap_err();
    assert!(matches!(err, AppError::Unauthenticated(_)));
    let key = Actor::Service {
        key_id: ApiKeyId::generate(),
        scopes: PermissionSet::of(Permission::ALL),
    };
    assert!(matches!(service(&f).apply(&key, input.clone()).await, Err(AppError::Forbidden(_))));

    let without = DriverService::new(f.store.clone(), f.uploads_without_storage(), f.clock.clone());
    let err = without.apply(&other, input).await.unwrap_err();
    assert!(matches!(err, AppError::Unavailable("storage")));
    assert_eq!(view.record.driver.status, DriverStatus::Pending);
}

#[tokio::test]
async fn every_review_follows_the_transition_table() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    f.store.drain_outbox();
    let reject = || Review::Reject { reason: "Blurry scan".into() };
    let suspend = || Review::Suspend { reason: "Complaints".into() };

    // pending: reinstate and suspend are refused.
    for refused in [Review::Reinstate, suspend()] {
        let err = review(&f, &admin, id, refused).await.unwrap_err();
        assert_eq!(conflict(err), ConflictKind::InvalidTransition);
    }
    // pending → rejected (with its reason) → pending (reapply) → approved.
    let rejected = review(&f, &admin, id, reject()).await.unwrap().record.driver;
    let explained = (rejected.status, rejected.status_reason.as_str());
    assert_eq!(explained, (DriverStatus::Rejected, "Blurry scan"));
    for refused in [approval(&f, id).await, reject(), suspend(), Review::Reinstate] {
        let err = review(&f, &admin, id, refused).await.unwrap_err();
        assert_eq!(conflict(err), ConflictKind::InvalidTransition);
    }
    let reapplied = service(&f).reapply(&actor).await.unwrap().record.driver;
    assert_eq!((reapplied.status, reapplied.status_reason.as_str()), (DriverStatus::Pending, ""));
    let err = service(&f).reapply(&actor).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::InvalidTransition, "only from rejected");

    let approved = review(&f, &admin, id, approval(&f, id).await).await.unwrap().record;
    assert_eq!(approved.driver.status, DriverStatus::Approved);
    assert_eq!(role_of(&f, &actor).await, Role::Driver, "approval makes the applicant a driver");
    for refused in [approval(&f, id).await, reject(), Review::Reinstate] {
        let err = review(&f, &admin, id, refused).await.unwrap_err();
        assert_eq!(conflict(err), ConflictKind::InvalidTransition);
    }

    // approved → suspended → approved.
    service(&f).set_availability(&actor, true).await.unwrap();
    let suspended = review(&f, &admin, id, suspend()).await.unwrap().record.driver;
    assert_eq!(suspended.status, DriverStatus::Suspended);
    assert!(!suspended.is_available, "suspension takes the driver off duty");
    assert_eq!(role_of(&f, &actor).await, Role::Driver, "role kept");
    for refused in [approval(&f, id).await, reject(), suspend()] {
        let err = review(&f, &admin, id, refused).await.unwrap_err();
        assert_eq!(conflict(err), ConflictKind::InvalidTransition);
    }
    let reinstated = review(&f, &admin, id, Review::Reinstate).await.unwrap().record.driver;
    let cleared = (reinstated.status, reinstated.status_reason.as_str());
    assert_eq!(cleared, (DriverStatus::Approved, ""));
    assert!(!reinstated.is_available, "the driver turns availability on again");

    let entries = history(&f, &admin, id).await;
    let steps: Vec<_> = entries.iter().rev().map(|e| (e.from, e.to)).collect();
    use DriverStatus as S;
    assert_eq!(
        steps,
        [
            (None, S::Pending),
            (Some(S::Pending), S::Rejected),
            (Some(S::Rejected), S::Pending),
            (Some(S::Pending), S::Approved),
            (Some(S::Approved), S::Suspended),
            (Some(S::Suspended), S::Approved),
        ]
    );
    let authors: Vec<_> = entries.iter().rev().map(|e| e.changed_by).collect();
    let (driver, reviewer) = (Some(uid(&actor)), Some(uid(&admin)));
    assert_eq!(authors, [driver, reviewer, driver, reviewer, reviewer, reviewer]);
    assert_eq!(entries[1].reason, "Complaints");

    // Reviews are audited; the driver is told about each change; reviewers about re-applying.
    assert_eq!(f.store.audit_len(), 4);
    let jobs = f.store.drain_outbox();
    assert_eq!(
        kinds(&jobs),
        [
            "driver_status_changed",
            "driver_status_changed",
            "driver_review_requested",
            "driver_status_changed",
            "driver_status_changed",
            "driver_status_changed",
        ]
    );
}

#[tokio::test]
async fn reviews_are_audited_validated_and_never_self_reviews() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;

    for reason in ["", "   ", &"x".repeat(1001)] {
        let err = review(&f, &admin, id, Review::Reject { reason: reason.into() }).await;
        let code = if reason.len() > 1000 { "too_long" } else { "required" };
        assert_eq!(codes(err.unwrap_err()), vec![("reason".into(), code)]);
    }
    let unknown = Review::Approve { expected_updated_at: f.clock.now() };
    let err = review(&f, &admin, DriverId::generate(), unknown).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("driver")));
    let err = review(&f, &actor, id, approval(&f, id).await).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(_)), "applicants cannot review");
    // An applicant promoted to administrator meanwhile cannot approve themself.
    f.store.set_role(uid(&actor), Role::Admin);
    let promoted =
        Actor::User { id: uid(&actor), role: Role::Admin, session_id: SessionId::generate() };
    let err = review(&f, &promoted, id, approval(&f, id).await).await.unwrap_err();
    assert!(matches!(err, AppError::Forbidden(DenyReason::InvalidState)));
    // Approval keeps any role other than passenger.
    review(&f, &admin, id, approval(&f, id).await).await.unwrap();
    assert_eq!(role_of(&f, &actor).await, Role::Admin);

    let meta = RequestMeta { request_id: Some("req-1".into()), ..RequestMeta::default() };
    let reason = Review::Suspend { reason: " Expired licence ".into() };
    service(&f).review(&admin, id, reason, &meta).await.unwrap();
    let entries = crate::ports::AuditRepository::list(
        &*f.store,
        &crate::ports::AuditFilter::default(),
        PageRequest::default(),
    )
    .await
    .unwrap()
    .items;
    let last = &entries[0];
    assert_eq!((last.action.as_str(), last.resource_type.as_str()), ("driver.suspend", "driver"));
    assert_eq!(last.resource_id.as_deref(), Some(id.to_string().as_str()));
    assert_eq!(last.actor, AuditActor::User(uid(&admin)));
    assert_eq!(last.request_id.as_deref(), Some("req-1"));
    assert_eq!(
        last.details,
        json!({ "from": "approved", "to": "suspended", "reason": "Expired licence" })
    );
}

#[tokio::test]
async fn new_documents_send_an_approved_profile_back_to_review() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    review(&f, &admin, id, approval(&f, id).await).await.unwrap();
    service(&f).set_availability(&actor, true).await.unwrap();
    f.store.drain_outbox();
    let drivers = service(&f);

    // Not a document: no review.
    let phone = UpdateDriverInput {
        phone_number: Some("0661 00 11 22".into()),
        years_of_experience: Some(8),
        ..UpdateDriverInput::default()
    };
    let updated = drivers.update_me(&actor, phone).await.unwrap().record.driver;
    assert_eq!(updated.status, DriverStatus::Approved);
    let contact = (updated.phone_number.as_str(), updated.years_of_experience.years());
    assert_eq!(contact, ("+213661001122", 8));
    assert!(updated.is_available);
    assert!(f.store.drain_outbox().is_empty());

    // Same values: nothing changes.
    let same = UpdateDriverInput {
        id_card_number: Some(ID_CARD.into()),
        driver_license_number: Some("l-1".into()),
        ..UpdateDriverInput::default()
    };
    let unchanged = drivers.update_me(&actor, same).await.unwrap().record.driver;
    assert_eq!(unchanged, updated);

    // A new licence photo: back to pending, off duty, old object deleted later.
    let old_key = updated.driver_license_photo_key.clone();
    let photo = uploaded(&f, &actor, UploadPurpose::DriverLicense).await;
    let input = UpdateDriverInput {
        driver_license_photo_upload_id: Some(photo),
        ..UpdateDriverInput::default()
    };
    let pending = drivers.update_me(&actor, input).await.unwrap().record.driver;
    assert_eq!(pending.status, DriverStatus::Pending);
    assert!(!pending.is_available);
    assert_ne!(pending.driver_license_photo_key, old_key);
    assert_eq!(f.store.upload(photo).unwrap().status, UploadStatus::Attached);
    let jobs = f.store.drain_outbox();
    assert_eq!(
        kinds(&jobs),
        ["driver_status_changed", "driver_review_requested", "storage_delete_object"]
    );
    assert_eq!(jobs[2].job, Job::StorageDeleteObject { key: old_key });
    assert!(jobs[2].options.run_at.is_some(), "deferred until the presigned URL expired");
    let latest = &history(&f, &actor, id).await[0];
    assert_eq!((latest.from, latest.to), (Some(DriverStatus::Approved), DriverStatus::Pending));
    assert_eq!(latest.changed_by, Some(uid(&actor)));

    // Still pending: reviewers are told about the new documents, without a status change.
    let input = UpdateDriverInput {
        id_card_number: Some("999999999999999999".into()),
        ..UpdateDriverInput::default()
    };
    drivers.update_me(&actor, input).await.unwrap();
    assert_eq!(kinds(&f.store.drain_outbox()), ["driver_review_requested"]);

    // Rejected and suspended profiles keep their status (the driver re-applies or waits).
    review(&f, &admin, id, Review::Reject { reason: "No".into() }).await.unwrap();
    f.store.drain_outbox();
    let input =
        UpdateDriverInput { id_card_number: Some(ID_CARD.into()), ..UpdateDriverInput::default() };
    let rejected = drivers.update_me(&actor, input).await.unwrap().record.driver;
    let kept = (rejected.status, rejected.id_card_number.as_str());
    assert_eq!(kept, (DriverStatus::Rejected, ID_CARD));
    assert!(f.store.drain_outbox().is_empty());
    assert_eq!(history(&f, &actor, id).await.len(), 4, "no status change, no history entry");
}

#[tokio::test]
async fn profile_updates_are_validated_and_conflict_on_taken_documents() {
    let f = Fakes::default();
    let (actor, _) = applicant(&f, ID_CARD, "L-1").await;
    let (_, other) = applicant(&f, "111111111111111111", "L-2").await;
    let drivers = service(&f);
    let bad = UpdateDriverInput {
        phone_number: Some("12".into()),
        years_of_experience: Some(-1),
        id_card_number: Some("".into()),
        driver_license_number: Some("x".repeat(21)),
        ..UpdateDriverInput::default()
    };
    assert_eq!(
        codes(drivers.update_me(&actor, bad).await.unwrap_err()),
        vec![
            ("phone_number".into(), "invalid_phone"),
            ("years_of_experience".into(), "out_of_range"),
            ("id_card_number".into(), "required"),
            ("driver_license_number".into(), "too_long"),
        ]
    );
    let taken = other.record.driver.id_card_number.as_str().to_owned();
    let input = UpdateDriverInput { id_card_number: Some(taken), ..UpdateDriverInput::default() };
    let err = drivers.update_me(&actor, input).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::IdCardTaken);
    let input = UpdateDriverInput {
        driver_license_number: Some("l-2".into()),
        ..UpdateDriverInput::default()
    };
    let err = drivers.update_me(&actor, input).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::LicenseTaken);
    let input = UpdateDriverInput {
        id_card_photo_upload_id: Some(UploadId::generate()),
        ..UpdateDriverInput::default()
    };
    assert_eq!(
        codes(drivers.update_me(&actor, input).await.unwrap_err()),
        vec![("id_card_photo_upload_id".into(), "invalid_upload")]
    );

    let stranger = user(&f, Role::Passenger).await;
    let err = drivers.update_me(&stranger, UpdateDriverInput::default()).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("driver")), "no profile yet");
    assert!(matches!(drivers.me(&stranger).await, Err(AppError::NotFound("driver"))));
    assert!(matches!(drivers.reapply(&stranger).await, Err(AppError::NotFound("driver"))));
}

#[tokio::test]
async fn only_approved_drivers_can_be_available() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let drivers = service(&f);
    let err = drivers.set_availability(&actor, true).await.unwrap_err();
    assert!(matches!(err, AppError::InvalidState(_)));
    let id = view.record.driver.id;
    review(&f, &admin, id, approval(&f, id).await).await.unwrap();
    assert!(drivers.set_availability(&actor, true).await.unwrap().record.driver.is_available);
    assert!(!drivers.set_availability(&actor, false).await.unwrap().record.driver.is_available);
    let stranger = user(&f, Role::Passenger).await;
    let err = drivers.set_availability(&stranger, true).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("driver")));
}

#[tokio::test]
async fn profiles_are_visible_to_their_driver_and_reviewers_only() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let (_, second) = applicant(&f, "111111111111111111", "L-2").await;
    let id = view.record.driver.id;
    let drivers = service(&f);

    assert_eq!(drivers.get(&actor, id).await.unwrap().record.driver.id, id);
    assert_eq!(drivers.get(&admin, id).await.unwrap().record.driver.id, id);
    assert_eq!(drivers.me(&actor).await.unwrap().record.driver.id, id);
    for outsider in [user(&f, Role::Passenger).await, user(&f, Role::Driver).await] {
        assert!(matches!(drivers.get(&outsider, id).await, Err(AppError::NotFound("driver"))));
        let page = PageRequest::default();
        let err = drivers.status_history(&outsider, id, page).await.unwrap_err();
        assert!(matches!(err, AppError::NotFound("driver")), "existence is not revealed");
        let err = drivers.list(&outsider, DriverListQuery::default(), page).await.unwrap_err();
        assert!(matches!(err, AppError::Forbidden(_)));
    }
    let err = drivers.get(&Actor::Anonymous, id).await.unwrap_err();
    assert!(matches!(err, AppError::Unauthenticated(_)));
    let err = drivers.get(&admin, DriverId::generate()).await.unwrap_err();
    assert!(matches!(err, AppError::NotFound("driver")));

    let second_id = second.record.driver.id;
    review(&f, &admin, second_id, approval(&f, second_id).await).await.unwrap();
    let page = PageRequest::parse(Some(1), None).unwrap();
    let first = drivers.list(&admin, DriverListQuery::default(), page).await.unwrap();
    assert_eq!(first.items.len(), 1);
    let cursor = first.next_cursor.unwrap().encode();
    let next = PageRequest::parse(Some(1), Some(&cursor)).unwrap();
    let rest = drivers.list(&admin, DriverListQuery::default(), next).await.unwrap();
    let mut seen = vec![first.items[0].record.driver.id, rest.items[0].record.driver.id];
    seen.sort();
    let mut expected = vec![id, second.record.driver.id];
    expected.sort();
    assert_eq!(seen, expected);
    let approved =
        DriverListQuery { status: Some(DriverStatus::Approved), ..DriverListQuery::default() };
    let only = drivers.list(&admin, approved, PageRequest::default()).await.unwrap().items;
    assert_eq!(only.len(), 1);
    assert_eq!(only[0].record.driver.id, second.record.driver.id);
    let available = DriverListQuery { is_available: Some(true), ..DriverListQuery::default() };
    let none = drivers.list(&admin, available, PageRequest::default()).await.unwrap();
    assert!(none.items.is_empty());
}

/// What happens to the profile just before the first status change of [`Racing`].
enum Rival {
    /// Another reviewer (this user) rejects the profile.
    Rejects(UserId),
    /// The applicant replaces their identity card number a second later (the profile stays
    /// pending, with a new `updated_at`).
    ChangesDocuments,
}

/// A repository whose first status change loses a race against a [`Rival`] change, made after
/// the use-case read the profile and before its compare-and-set.
struct Racing {
    store: Arc<InMemoryStore>,
    rival: Rival,
    /// Status changes attempted through this repository.
    attempts: AtomicUsize,
}

impl Racing {
    fn new(store: Arc<InMemoryStore>, rival: Rival) -> Self {
        Self { store, rival, attempts: AtomicUsize::new(0) }
    }

    async fn rival_change(&self, id: DriverId, change: &StatusChange) -> AppResult<()> {
        match &self.rival {
            Rival::Rejects(reviewer) => {
                let rival = StatusChange {
                    id: DriverStatusChangeId::generate(),
                    from: change.from,
                    to: DriverStatus::Rejected,
                    reason: Some(StatusReason::parse("Rival decision").unwrap()),
                    changed_by: Some(*reviewer),
                    at: change.at,
                    expected_updated_at: None,
                };
                self.store.transition(id, rival, WriteEffects::default()).await?;
            }
            Rival::ChangesDocuments => {
                let store = &*self.store;
                let current = DriverRepository::find(store, id).await?.unwrap().driver;
                let number = NationalIdNumber::parse("999999999999999999").unwrap();
                let patch = DriverPatch { id_card_number: Some(number), ..DriverPatch::default() };
                let at = change.at + chrono::TimeDelta::seconds(1);
                let effects = WriteEffects::default();
                DriverRepository::update_profile(store, &current, patch, None, at, effects).await?;
            }
        }
        Ok(())
    }
}

#[async_trait]
impl DriverRepository for Racing {
    async fn insert(&self, driver: NewDriver, effects: WriteEffects) -> AppResult<DriverRecord> {
        DriverRepository::insert(&*self.store, driver, effects).await
    }
    async fn find(&self, id: DriverId) -> AppResult<Option<DriverRecord>> {
        DriverRepository::find(&*self.store, id).await
    }
    async fn find_by_user(&self, user_id: UserId) -> AppResult<Option<DriverRecord>> {
        self.store.find_by_user(user_id).await
    }
    async fn list(&self, filter: DriverFilter, page: PageRequest) -> AppResult<Page<DriverRecord>> {
        DriverRepository::list(&*self.store, filter, page).await
    }
    async fn update_profile(
        &self,
        expected: &Driver,
        patch: DriverPatch,
        change: Option<StatusChange>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        DriverRepository::update_profile(&*self.store, expected, patch, change, at, effects).await
    }
    async fn transition(
        &self,
        id: DriverId,
        change: StatusChange,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        if self.attempts.fetch_add(1, Ordering::SeqCst) == 0 {
            self.rival_change(id, &change).await?;
        }
        self.store.transition(id, change, effects).await
    }
    async fn set_availability(
        &self,
        id: DriverId,
        available: bool,
        at: DateTime<Utc>,
    ) -> AppResult<DriverRecord> {
        self.store.set_availability(id, available, at).await
    }
    async fn status_history(
        &self,
        id: DriverId,
        page: PageRequest,
    ) -> AppResult<Page<DriverStatusChange>> {
        self.store.status_history(id, page).await
    }
    async fn reviewers(&self) -> AppResult<Vec<AccountSummary>> {
        self.store.reviewers().await
    }
}

#[tokio::test]
async fn a_review_overtaken_by_another_is_re_evaluated() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let rival = user(&f, Role::Admin).await;
    let (_, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    f.store.drain_outbox();
    let racing = Arc::new(Racing::new(f.store.clone(), Rival::Rejects(uid(&rival))));
    let drivers = DriverService::new(racing.clone(), f.uploads(), f.clock.clone());
    let approve = approval(&f, id).await;
    let err = drivers.review(&admin, id, approve, &RequestMeta::default()).await;
    assert_eq!(conflict(err.unwrap_err()), ConflictKind::InvalidTransition, "now rejected");
    let current = DriverRepository::find(&*f.store, id).await.unwrap().unwrap();
    assert_eq!(current.driver.status, DriverStatus::Rejected);
    assert_eq!(f.store.audit_len(), 0, "the lost approval left nothing behind");
    assert!(f.store.drain_outbox().is_empty());
    assert_eq!(racing.attempts.load(Ordering::SeqCst), 1, "re-evaluated, not retried");
}

#[tokio::test]
async fn approvals_apply_only_to_the_reviewed_documents() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    let drivers = service(&f);
    // The reviewer examines the application…
    let reviewed = drivers.get(&admin, id).await.unwrap().record.driver;
    // …then the applicant replaces the identity card scan: the profile stays pending.
    f.clock.advance(Duration::from_secs(60));
    let photo = uploaded(&f, &actor, UploadPurpose::DriverIdCard).await;
    let input =
        UpdateDriverInput { id_card_photo_upload_id: Some(photo), ..UpdateDriverInput::default() };
    let swapped = drivers.update_me(&actor, input).await.unwrap().record.driver;
    assert_eq!(swapped.status, DriverStatus::Pending);
    assert_ne!(swapped.id_card_photo_key, reviewed.id_card_photo_key);
    assert_ne!(swapped.updated_at, reviewed.updated_at);
    f.store.drain_outbox();

    // Approving what was reviewed would approve a scan nobody saw: refused, nothing changes.
    // A version the profile never had is refused too.
    let unknown = swapped.updated_at + chrono::TimeDelta::seconds(1);
    for expected_updated_at in [reviewed.updated_at, unknown] {
        let stale = Review::Approve { expected_updated_at };
        let err = review(&f, &admin, id, stale).await.unwrap_err();
        assert_eq!(conflict(err), ConflictKind::StaleState);
    }
    let current = DriverRepository::find(&*f.store, id).await.unwrap().unwrap().driver;
    assert_eq!(current, swapped, "the profile is untouched");
    assert_eq!(role_of(&f, &actor).await, Role::Passenger);
    assert_eq!(history(&f, &admin, id).await.len(), 1, "no status change recorded");
    assert_eq!(f.store.audit_len(), 0, "nothing audited");
    assert!(f.store.drain_outbox().is_empty(), "nobody notified");

    // Once the current documents are reviewed, the approval applies to them.
    let fresh = drivers.get(&admin, id).await.unwrap().record.driver;
    let approve = Review::Approve { expected_updated_at: fresh.updated_at };
    let approved = review(&f, &admin, id, approve).await.unwrap().record.driver;
    assert_eq!(approved.status, DriverStatus::Approved);
    assert_eq!(approved.id_card_photo_key, swapped.id_card_photo_key);
    assert_eq!(role_of(&f, &actor).await, Role::Driver);
    assert_eq!(f.store.audit_len(), 1);
    assert_eq!(kinds(&f.store.drain_outbox()), ["driver_status_changed"]);
}

#[tokio::test]
async fn an_approval_overtaken_by_new_documents_is_refused_without_retrying() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let (actor, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    f.store.drain_outbox();
    let racing = Arc::new(Racing::new(f.store.clone(), Rival::ChangesDocuments));
    let drivers = DriverService::new(racing.clone(), f.uploads(), f.clock.clone());
    // The profile is unchanged when the approval reads it: only the write can see the change.
    let approve = approval(&f, id).await;
    let err = drivers.review(&admin, id, approve, &RequestMeta::default()).await.unwrap_err();
    assert_eq!(conflict(err), ConflictKind::StaleState);
    assert_eq!(racing.attempts.load(Ordering::SeqCst), 1, "never retried on new documents");
    let current = DriverRepository::find(&*f.store, id).await.unwrap().unwrap().driver;
    let documents = (current.status, current.id_card_number.as_str());
    assert_eq!(documents, (DriverStatus::Pending, "999999999999999999"));
    assert_eq!(role_of(&f, &actor).await, Role::Passenger);
    assert_eq!(history(&f, &admin, id).await.len(), 1, "no status change recorded");
    assert_eq!(f.store.audit_len(), 0, "the refused approval left nothing behind");
    assert!(f.store.drain_outbox().is_empty());
}

#[tokio::test]
async fn drivers_are_mailed_their_status_in_their_language() {
    let f = Fakes::default();
    let admin = user(&f, Role::Admin).await;
    let actor = user_with(&f, Role::Passenger, Lang::Ar).await;
    let input = application(&f, &actor, ID_CARD, "L-1").await;
    let id = service(&f).apply(&actor, input).await.unwrap().record.driver.id;
    review(&f, &admin, id, Review::Reject { reason: "Scan illisible".into() }).await.unwrap();
    let runner = runner(&f);

    // The pending notification was overtaken by the rejection: dropped.
    let told = |status| Job::DriverStatusChanged { driver_id: id, status };
    runner.run(&told(DriverStatus::Pending)).await.unwrap();
    assert!(f.mailer.sent.lock().unwrap().is_empty());
    runner.run(&told(DriverStatus::Rejected)).await.unwrap();
    let sent = f.mailer.sent.lock().unwrap().clone();
    assert_eq!(sent.len(), 1);
    assert_eq!(sent[0].to, format!("{}@example.dz", uid(&actor)));
    assert_eq!(sent[0].lang, Lang::Ar);
    assert!(sent[0].text_body.contains("Scan illisible"), "the reason is explained");
    // Unknown drivers are ignored (nothing to retry).
    let unknown = DriverId::generate();
    let job = Job::DriverStatusChanged { driver_id: unknown, status: DriverStatus::Approved };
    runner.run(&job).await.unwrap();
    assert_eq!(f.mailer.sent.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn active_reviewers_are_mailed_pending_profiles() {
    let f = Fakes::default();
    let first = user_with(&f, Role::Admin, Lang::En).await;
    let second = user_with(&f, Role::Admin, Lang::Fr).await;
    let retired = user(&f, Role::Admin).await;
    f.store.set_active(uid(&retired), false);
    user(&f, Role::Driver).await;
    let (_, view) = applicant(&f, ID_CARD, "L-1").await;
    let id = view.record.driver.id;
    let runner = runner(&f);

    runner.run(&Job::DriverReviewRequested { driver_id: id }).await.unwrap();
    let sent = f.mailer.sent.lock().unwrap().clone();
    let mut recipients: Vec<_> = sent.iter().map(|m| (m.to.clone(), m.lang)).collect();
    recipients.sort_by(|a, b| a.0.cmp(&b.0));
    let mut expected = vec![
        (format!("{}@example.dz", uid(&first)), Lang::En),
        (format!("{}@example.dz", uid(&second)), Lang::Fr),
    ];
    expected.sort_by(|a, b| a.0.cmp(&b.0));
    assert_eq!(recipients, expected, "active administrators only");
    let shown = id.to_string();
    let named = |m: &EmailMessage| m.text_body.contains("Amine Benali");
    assert!(sent.iter().all(|m| named(m) && m.text_body.contains(&shown)));

    // Reviewed meanwhile: nobody is bothered.
    review(&f, &first, id, approval(&f, id).await).await.unwrap();
    runner.run(&Job::DriverReviewRequested { driver_id: id }).await.unwrap();
    assert_eq!(f.mailer.sent.lock().unwrap().len(), 2);
}
