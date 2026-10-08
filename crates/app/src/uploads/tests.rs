//! Upload, claim, avatar and storage-job use-cases against the in-memory ports.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::sync::atomic::Ordering;
use std::time::Duration;

use dz_domain::authz::{Actor, Permission, PermissionSet};
use dz_domain::ids::{ApiKeyId, SessionId, UploadId, UserId};
use dz_domain::upload::{UploadPurpose, UploadStatus};
use dz_domain::user::{Email, PersonName, Role};
use chrono::{DateTime, Utc};
use dz_domain::{ConflictKind, DenyReason, Lang};

use super::*;
use crate::account::AccountService;
use crate::jobs::{JobRunner, JobSettings};
use crate::ports::{NewUser, OutboxJob, UserRepository, WriteEffects};
use crate::testing::Fakes;

const PNG: &str = "image/png";

async fn user(f: &Fakes, role: Role) -> Actor {
    let id = UserId::generate();
    let new = NewUser {
        id,
        email: Email::parse(&format!("{id}@example.dz")).unwrap(),
        password_hash: "plain$x".into(),
        role,
        first_name: PersonName::parse("Test").unwrap(),
        last_name: PersonName::parse("User").unwrap(),
        phone_number: None,
        language: Lang::Fr,
        created_at: f.clock.now(),
    };
    UserRepository::insert(&*f.store, new).await.unwrap();
    Actor::User { id, role, session_id: SessionId::generate() }
}

fn codes(err: AppError) -> Vec<(String, &'static str)> {
    match err {
        AppError::Validation(v) => {
            v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
        }
        other => panic!("expected a validation error, got {other:?}"),
    }
}

/// Requests an upload and stores its object as the client would.
async fn uploaded(f: &Fakes, actor: &Actor, purpose: UploadPurpose, size: u64) -> UploadId {
    let requested = f.uploads().request(actor, purpose, PNG, size).await.unwrap();
    f.storage.put(&requested.upload.object_key, size, PNG);
    requested.upload.id
}

/// The outbox entry deleting `key` once a presigned URL expiring at `expires_at` is unusable.
fn deferred_deletion(key: &str, expires_at: DateTime<Utc>) -> OutboxJob {
    let run_at = expires_at + chrono_duration(PRESIGNED_CLOCK_SKEW);
    OutboxJob {
        job: Job::StorageDeleteObject { key: key.to_owned() },
        options: JobOptions { run_at: Some(run_at), ..JobOptions::default() },
    }
}

fn runner(f: &Fakes) -> JobRunner {
    JobRunner {
        users: f.store.clone(),
        sessions: f.store.clone(),
        resets: f.store.clone(),
        uploads: f.store.clone(),
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
async fn requesting_an_upload_presigns_a_server_generated_key() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let owner = actor.user_id().unwrap();
    let requested = f.uploads().request(&actor, UploadPurpose::Avatar, " Image/PNG", 1234).await;
    let RequestedUpload { upload, presigned } = requested.unwrap();
    assert_eq!(upload.object_key, format!("avatar/{}", upload.id));
    assert_eq!(upload.owner_id, owner, "ownership is recorded in the row, not in the key");
    assert_eq!((upload.content_type.as_str(), upload.size_bytes), (PNG, 1234));
    assert_eq!(upload.status, UploadStatus::Pending);
    assert_eq!(upload.created_at, f.clock.now());
    assert_eq!(upload.expires_at, f.clock.now() + chrono::Duration::seconds(900));
    assert_eq!(presigned.expires_at, upload.expires_at);
    assert_eq!(presigned.method, "PUT");
    assert_eq!(
        presigned.headers,
        vec![("content-type", PNG.to_owned()), ("content-length", "1234".to_owned())]
    );
    assert_eq!(f.store.upload(upload.id), Some(upload));
}

#[tokio::test]
async fn upload_requests_are_validated_per_purpose() {
    let f = Fakes::default();
    let driver = user(&f, Role::Driver).await;
    let uploads = f.uploads();
    let err = uploads.request(&driver, UploadPurpose::Avatar, "application/pdf", 0).await;
    assert_eq!(
        codes(err.unwrap_err()),
        vec![("content_type".into(), "invalid_choice"), ("size_bytes".into(), "out_of_range")]
    );
    let too_big = uploads.request(&driver, UploadPurpose::BusPhoto, PNG, 5 * 1024 * 1024 + 1).await;
    assert_eq!(codes(too_big.unwrap_err()), vec![("size_bytes".into(), "out_of_range")]);
    let pdf = uploads.request(&driver, UploadPurpose::DriverLicense, "application/pdf", 10).await;
    assert!(pdf.is_ok());
}

#[tokio::test]
async fn upload_requests_are_authorized() {
    let f = Fakes::default();
    let uploads = f.uploads();
    let passenger = user(&f, Role::Passenger).await;
    let admin = user(&f, Role::Admin).await;
    let service = Actor::Service {
        key_id: ApiKeyId::generate(),
        scopes: PermissionSet::of(&[Permission::StopWrite]),
    };
    let cases = [
        (&Actor::Anonymous, UploadPurpose::Avatar, "authentication"),
        (&service, UploadPurpose::StopPhoto, "forbidden"),
        (&passenger, UploadPurpose::StopPhoto, "forbidden"),
        (&admin, UploadPurpose::DriverIdCard, "forbidden"),
    ];
    for (actor, purpose, expected) in cases {
        let err = uploads.request(actor, purpose, PNG, 10).await.unwrap_err();
        let got = match err {
            AppError::Unauthenticated(_) => "authentication",
            AppError::Forbidden(DenyReason::MissingPermission) => "forbidden",
            other => panic!("unexpected {other:?}"),
        };
        assert_eq!(got, expected, "{actor:?} × {purpose}");
    }
    assert!(uploads.request(&admin, UploadPurpose::StopPhoto, PNG, 10).await.is_ok());
}

#[tokio::test]
async fn without_storage_uploads_are_unavailable_and_urls_absent() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let uploads = f.uploads_without_storage();
    assert!(!uploads.enabled());
    let err = uploads.request(&actor, UploadPurpose::Avatar, PNG, 10).await.unwrap_err();
    assert!(matches!(err, AppError::Unavailable("storage")));
    let owner = actor.user_id().unwrap();
    let claim = uploads.claim(owner, UploadId::generate(), UploadPurpose::Avatar, "upload_id");
    assert!(matches!(claim.await, Err(AppError::Unavailable("storage"))));
    assert_eq!(uploads.download_url(Some("avatar/x/y")), None);
    assert!(f.uploads().download_url(Some("avatar/x/y")).is_some());
    assert_eq!(f.uploads().download_url(None), None);
}

#[tokio::test]
async fn claims_check_owner_purpose_expiry_and_the_stored_object() {
    let f = Fakes::default();
    let uploads = f.uploads();
    let actor = user(&f, Role::Driver).await;
    let owner = actor.user_id().unwrap();
    let other = user(&f, Role::Driver).await.user_id().unwrap();
    let invalid = vec![("photo".to_owned(), "invalid_upload")];
    let claim = |owner, id, purpose| uploads.claim(owner, id, purpose, "photo");

    let id = uploaded(&f, &actor, UploadPurpose::BusPhoto, 100).await;
    for (who, purpose) in [(other, UploadPurpose::BusPhoto), (owner, UploadPurpose::Avatar)] {
        assert_eq!(codes(claim(who, id, purpose).await.unwrap_err()), invalid);
    }
    let unknown = claim(owner, UploadId::generate(), UploadPurpose::BusPhoto).await;
    assert_eq!(codes(unknown.unwrap_err()), invalid);
    let claimed = claim(owner, id, UploadPurpose::BusPhoto).await.unwrap();
    assert_eq!(claimed.object_key, f.store.upload(id).unwrap().object_key);

    // Never uploaded.
    let requested = uploads.request(&actor, UploadPurpose::BusPhoto, PNG, 100).await.unwrap();
    let missing = claim(owner, requested.upload.id, UploadPurpose::BusPhoto).await;
    assert_eq!(codes(missing.unwrap_err()), invalid);

    // Expired.
    let id = uploaded(&f, &actor, UploadPurpose::BusPhoto, 100).await;
    f.clock.advance(Duration::from_secs(901));
    assert_eq!(codes(claim(owner, id, UploadPurpose::BusPhoto).await.unwrap_err()), invalid);
}

#[tokio::test]
async fn an_object_that_differs_from_its_declaration_is_rejected_and_deleted() {
    let f = Fakes::default();
    let uploads = f.uploads();
    let actor = user(&f, Role::Passenger).await;
    let owner = actor.user_id().unwrap();
    for (size, content_type) in [(99, PNG), (100, "image/jpeg")] {
        let requested = uploads.request(&actor, UploadPurpose::Avatar, PNG, 100).await.unwrap();
        let key = requested.upload.object_key;
        f.storage.put(&key, size, content_type);
        let err = uploads.claim(owner, requested.upload.id, UploadPurpose::Avatar, "upload_id");
        assert_eq!(codes(err.await.unwrap_err()), vec![("upload_id".into(), "invalid_upload")]);
        assert_eq!(f.storage.object(&key), None, "mismatching object is deleted");
    }
}

#[tokio::test]
async fn storage_outages_surface_as_unavailable() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let id = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    f.storage.failing.store(true, Ordering::SeqCst);
    let owner = actor.user_id().unwrap();
    let err = f.uploads().claim(owner, id, UploadPurpose::Avatar, "upload_id").await;
    assert!(matches!(err, Err(AppError::Unavailable("storage"))));
}

#[tokio::test]
async fn avatars_are_attached_replaced_and_removed_with_outbox_jobs() {
    let f = Fakes::default();
    let accounts = AccountService::new(f.store.clone(), f.uploads(), f.clock.clone());
    let actor = user(&f, Role::Passenger).await;

    let first = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    let view = accounts.set_avatar(&actor, first).await.unwrap();
    let first_key = f.store.upload(first).unwrap().object_key;
    assert_eq!(view.profile.avatar_key.as_deref(), Some(first_key.as_str()));
    assert!(view.avatar_url.as_deref().is_some_and(|u| u.contains(&first_key)));
    assert_eq!(f.store.upload(first).unwrap().status, UploadStatus::Attached);
    assert!(f.store.drain_outbox().is_empty(), "nothing to delete for a first avatar");

    // An attached upload cannot be used again: it is no longer pending.
    let again = accounts.set_avatar(&actor, first).await;
    assert_eq!(codes(again.unwrap_err()), vec![("upload_id".into(), "invalid_upload")]);

    // The replaced object is deleted once its presigned URL has expired, so that it cannot be
    // uploaded again after its deletion.
    let first_expiry = f.store.upload(first).unwrap().expires_at;
    f.clock.advance(Duration::from_secs(60));
    let second = uploaded(&f, &actor, UploadPurpose::Avatar, 20).await;
    accounts.set_avatar(&actor, second).await.unwrap();
    assert_eq!(f.store.drain_outbox(), vec![deferred_deletion(&first_key, first_expiry)]);

    let second = f.store.upload(second).unwrap();
    accounts.remove_avatar(&actor).await.unwrap();
    let deletion = deferred_deletion(&second.object_key, second.expires_at);
    assert!(deletion.options.run_at >= Some(f.clock.now() + chrono::Duration::seconds(900)));
    assert_eq!(f.store.drain_outbox(), vec![deletion]);
    let (_, view) = accounts.me(&actor).await.unwrap();
    assert_eq!((view.profile.avatar_key, view.avatar_url), (None, None));
    // Removing again is a no-op.
    accounts.remove_avatar(&actor).await.unwrap();
    assert!(f.store.drain_outbox().is_empty());

    // The deletion job removes the replaced object.
    runner(&f).run(&Job::StorageDeleteObject { key: first_key.clone() }).await.unwrap();
    assert_eq!(f.storage.object(&first_key), None);
    assert_eq!(*f.storage.deleted.lock().unwrap(), vec![first_key]);
}

#[tokio::test]
async fn deletions_wait_until_no_presigned_upload_url_is_valid() {
    let f = Fakes::default();
    let uploads = f.uploads();
    let actor = user(&f, Role::Passenger).await;
    let skew = chrono_duration(PRESIGNED_CLOCK_SKEW);
    let run_at = |effects: &WriteEffects| effects.jobs.last().unwrap().options.run_at.unwrap();

    // Effects already collected are kept.
    let id = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    let upload = f.store.upload(id).unwrap();
    let effects = WriteEffects::default().with_job(Job::PurgeExpiredUploads);
    let effects = uploads.with_deletion(effects, &upload.object_key).await.unwrap();
    assert_eq!(effects.jobs.len(), 2);
    assert_eq!(effects.jobs[1], deferred_deletion(&upload.object_key, upload.expires_at));
    assert_eq!(run_at(&effects), f.clock.now() + chrono::Duration::seconds(900) + skew);

    // Once the URL has expired, only the margin remains.
    f.clock.advance(Duration::from_secs(2000));
    let effects = uploads.with_deletion(WriteEffects::default(), &upload.object_key).await;
    assert_eq!(run_at(&effects.unwrap()), f.clock.now() + skew);

    // A key without upload is treated as if it had just been presigned.
    let effects = uploads.with_deletion(WriteEffects::default(), "avatar/legacy").await.unwrap();
    assert_eq!(run_at(&effects), f.clock.now() + chrono::Duration::seconds(900) + skew);
    assert_eq!(effects.jobs[0].job, Job::StorageDeleteObject { key: "avatar/legacy".into() });
}

#[tokio::test]
async fn a_concurrent_avatar_change_is_a_stale_state_conflict() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let id = actor.user_id().unwrap();
    let upload = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    let claimed = f.uploads().claim(id, upload, UploadPurpose::Avatar, "upload_id").await.unwrap();
    let now = f.clock.now();
    let effects = WriteEffects::default();
    let stale = f.store.set_avatar(id, Some(&claimed), Some("avatar/old"), now, effects);
    assert!(matches!(stale.await, Err(AppError::Conflict(ConflictKind::StaleState))));
    // Nothing was attached by the failed write.
    assert_eq!(f.store.upload(upload).unwrap().status, UploadStatus::Pending);
}

#[tokio::test]
async fn avatars_need_storage_and_a_human_account() {
    let f = Fakes::default();
    let accounts =
        AccountService::new(f.store.clone(), f.uploads_without_storage(), f.clock.clone());
    let actor = user(&f, Role::Passenger).await;
    let err = accounts.set_avatar(&actor, UploadId::generate()).await;
    assert!(matches!(err, Err(AppError::Unavailable("storage"))));
    assert!(matches!(accounts.remove_avatar(&actor).await, Err(AppError::Unavailable("storage"))));
    let (_, view) = accounts.me(&actor).await.unwrap();
    assert_eq!(view.avatar_url, None);
    let anonymous = accounts.set_avatar(&Actor::Anonymous, UploadId::generate()).await;
    assert!(matches!(anonymous, Err(AppError::Unauthenticated(_))));
}

#[tokio::test]
async fn download_urls_are_stable_within_an_hour() {
    let f = Fakes::default();
    let uploads = f.uploads();
    let first = uploads.download_url(Some("avatar/a/b")).unwrap();
    f.clock.advance(Duration::from_secs(60));
    assert_eq!(uploads.download_url(Some("avatar/a/b")).unwrap(), first);
    f.clock.advance(Duration::from_secs(3600));
    assert_ne!(uploads.download_url(Some("avatar/a/b")).unwrap(), first);
}

#[tokio::test]
async fn expired_pending_uploads_are_purged_with_their_objects() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let accounts = AccountService::new(f.store.clone(), f.uploads(), f.clock.clone());
    let stale = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    let attached = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    accounts.set_avatar(&actor, attached).await.unwrap();
    let stale_key = f.store.upload(stale).unwrap().object_key;

    // Expired, but within the grace hour: kept.
    f.clock.advance(Duration::from_secs(900 + 1800));
    runner(&f).run(&Job::PurgeExpiredUploads).await.unwrap();
    assert!(f.store.upload(stale).is_some());

    f.clock.advance(Duration::from_secs(1801));
    let fresh = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    runner(&f).run(&Job::PurgeExpiredUploads).await.unwrap();
    assert_eq!(f.store.upload(stale), None);
    assert_eq!(f.storage.object(&stale_key), None);
    assert!(f.store.upload(attached).is_some(), "attached uploads are never purged");
    assert!(f.store.upload(fresh).is_some());
}

#[tokio::test]
async fn failed_object_deletions_keep_the_upload_for_the_next_run() {
    let f = Fakes::default();
    let actor = user(&f, Role::Passenger).await;
    let stale = uploaded(&f, &actor, UploadPurpose::Avatar, 10).await;
    f.clock.advance(Duration::from_secs(900 + 3601));
    f.storage.failing.store(true, Ordering::SeqCst);
    let err = runner(&f).run(&Job::PurgeExpiredUploads).await;
    assert!(matches!(err, Err(AppError::Unavailable("storage"))));
    assert!(f.store.upload(stale).is_some());
    let delete = runner(&f).run(&Job::StorageDeleteObject { key: "avatar/x".into() }).await;
    assert!(matches!(delete, Err(AppError::Unavailable("storage"))));

    f.storage.failing.store(false, Ordering::SeqCst);
    runner(&f).run(&Job::PurgeExpiredUploads).await.unwrap();
    assert_eq!(f.store.upload(stale), None);

    // Without storage the deletion job cannot run (it is retried later).
    let without = JobRunner { storage: None, ..runner(&f) };
    let err = without.run(&Job::StorageDeleteObject { key: "avatar/x".into() }).await;
    assert!(matches!(err, Err(AppError::Unavailable("storage"))));
}

#[test]
fn storage_jobs_have_stable_kinds() {
    let job = Job::StorageDeleteObject { key: "bus_photo/a/b".into() };
    assert_eq!(job.kind(), "storage_delete_object");
    let json = serde_json::to_value(&job).unwrap();
    assert_eq!(json["payload"]["key"], "bus_photo/a/b");
    assert_eq!(serde_json::from_value::<Job>(json).unwrap(), job);
    assert_eq!(Job::PurgeExpiredUploads.kind(), "purge_expired_uploads");
}

#[test]
fn write_effects_collect_audit_entries_and_jobs() {
    assert!(WriteEffects::default().is_empty());
    let effects = WriteEffects::default().with_job(Job::PurgeExpiredUploads);
    assert!(!effects.is_empty());
    assert_eq!(effects.jobs[0].options, crate::ports::JobOptions::default());
}
