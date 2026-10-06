//! Adapters against real PostgreSQL/PostGIS and Valkey: the job queue, retention jobs, the
//! audit log's immutability, schema-level invariants, rate limiting and session revocation.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::HashSet;
use std::sync::Mutex;
use std::time::Duration;

use async_trait::async_trait;
use dz_app::jobs::Job;
use dz_app::ports::{EnqueueOutcome, JobOptions, JobQueue, Quota, RateLimiter, RevocationStore};
use dz_app::{AppError, AppResult};
use dz_domain::ids::SessionId;
use dz_domain::user::Role;
use dz_infra::jobs::{self, JobExecutor, WorkerConfig};
use dz_infra::valkey::{ValkeyRateLimiter, ValkeyRevocationStore};
use dz_testkit::TestApp;
use sqlx::PgPool;
use uuid::Uuid;

fn worker(id: &str) -> WorkerConfig {
    WorkerConfig {
        worker_id: id.to_owned(),
        concurrency: 3,
        poll_interval: Duration::from_millis(50),
        lease: Duration::from_secs(60),
        job_timeout: Duration::from_secs(5),
    }
}

/// Records every job it runs and fails when asked to.
#[derive(Default)]
struct Recorder {
    fail: bool,
    ran: Mutex<Vec<Job>>,
}

#[async_trait]
impl JobExecutor for Recorder {
    async fn execute(&self, job: &Job) -> AppResult<()> {
        self.ran.lock().unwrap().push(job.clone());
        tokio::time::sleep(Duration::from_millis(5)).await;
        if self.fail { Err(AppError::Unavailable("smtp")) } else { Ok(()) }
    }
}

async fn job_state(pool: &PgPool, id: Uuid) -> (String, i16, bool, Option<String>) {
    sqlx::query_as(
        "SELECT status, attempts, run_at > now(), last_error FROM jobs WHERE id = $1",
    )
    .bind(id)
    .fetch_one(pool)
    .await
    .unwrap()
}

#[tokio::test]
async fn failed_jobs_are_retried_with_backoff_then_dead_lettered() {
    let app = TestApp::spawn().await;
    let options = JobOptions { max_attempts: Some(2), ..JobOptions::default() };
    let EnqueueOutcome::Enqueued(id) =
        app.infra.queue.enqueue(&Job::PurgeFinishedJobs, options).await.unwrap()
    else {
        panic!("expected a new job");
    };
    let failing = Recorder { fail: true, ..Recorder::default() };

    assert_eq!(jobs::drain(app.pool(), &failing, &worker("w1")).await.unwrap(), 1);
    let (status, attempts, delayed, error) = job_state(app.pool(), id).await;
    assert_eq!((status.as_str(), attempts, delayed), ("queued", 1, true));
    assert!(error.unwrap().contains("smtp"));

    // Not due yet: nothing to do.
    assert_eq!(jobs::drain(app.pool(), &failing, &worker("w1")).await.unwrap(), 0);

    sqlx::query("UPDATE jobs SET run_at = now() WHERE id = $1").bind(id).execute(app.pool()).await.unwrap();
    assert_eq!(jobs::drain(app.pool(), &failing, &worker("w1")).await.unwrap(), 1);
    let (status, attempts, _, _) = job_state(app.pool(), id).await;
    assert_eq!((status.as_str(), attempts), ("failed", 2), "dead-lettered after max_attempts");
}

#[tokio::test]
async fn undecodable_payloads_are_dead_lettered_immediately() {
    let app = TestApp::spawn().await;
    let id = Uuid::now_v7();
    sqlx::query(
        "INSERT INTO jobs (id, kind, payload, run_at, created_at, updated_at)
         VALUES ($1, 'from_the_future', '{\"kind\": \"from_the_future\"}', now(), now(), now())",
    )
    .bind(id)
    .execute(app.pool())
    .await
    .unwrap();
    let recorder = Recorder::default();
    jobs::drain(app.pool(), &recorder, &worker("w1")).await.unwrap();
    let (status, attempts, _, error) = job_state(app.pool(), id).await;
    assert_eq!((status.as_str(), attempts), ("failed", 1));
    assert!(error.unwrap().contains("undecodable"));
    assert!(recorder.ran.lock().unwrap().is_empty());
}

#[tokio::test]
async fn abandoned_leases_are_reclaimed() {
    let app = TestApp::spawn().await;
    let EnqueueOutcome::Enqueued(id) =
        app.infra.queue.enqueue(&Job::PurgeFinishedJobs, JobOptions::default()).await.unwrap()
    else {
        panic!("expected a new job");
    };
    // A worker claimed the job and died.
    sqlx::query(
        "UPDATE jobs SET status = 'running', attempts = 1, locked_by = 'dead-worker',
                         locked_until = now() - interval '1 second'
         WHERE id = $1",
    )
    .bind(id)
    .execute(app.pool())
    .await
    .unwrap();
    jobs::reap_expired_leases(app.pool()).await.unwrap();
    let (status, attempts, _, error) = job_state(app.pool(), id).await;
    assert_eq!((status.as_str(), attempts), ("queued", 1));
    assert!(error.unwrap().contains("lease expired"));

    // A late result from the dead worker cannot overwrite the new owner's outcome.
    let recorder = Recorder::default();
    assert_eq!(jobs::drain(app.pool(), &recorder, &worker("w2")).await.unwrap(), 1);
    let (status, attempts, _, _) = job_state(app.pool(), id).await;
    assert_eq!((status.as_str(), attempts), ("succeeded", 2));
}

#[tokio::test]
async fn concurrent_workers_never_run_a_job_twice() {
    let app = TestApp::spawn().await;
    for i in 0..30 {
        let job = Job::PasswordResetRequested {
            email: format!("user{i}@example.test"),
            lang: dz_domain::Lang::Fr,
            requested_ip: None,
        };
        app.infra.queue.enqueue(&job, JobOptions::default()).await.unwrap();
    }
    let (a, b) = (Recorder::default(), Recorder::default());
    let (worker_a, worker_b) = (worker("w-a"), worker("w-b"));
    let (ran_a, ran_b) = tokio::join!(
        jobs::drain(app.pool(), &a, &worker_a),
        jobs::drain(app.pool(), &b, &worker_b),
    );
    assert_eq!(ran_a.unwrap() + ran_b.unwrap(), 30);
    let mut seen = HashSet::new();
    for job in a.ran.lock().unwrap().iter().chain(b.ran.lock().unwrap().iter()) {
        let Job::PasswordResetRequested { email, .. } = job else { unreachable!() };
        assert!(seen.insert(email.clone()), "{email} ran twice");
    }
    assert_eq!(seen.len(), 30);
}

#[tokio::test]
async fn deduplication_applies_only_while_pending() {
    let app = TestApp::spawn().await;
    let options = || JobOptions { dedup_key: Some("cron:purge".to_owned()), ..JobOptions::default() };
    let first = app.infra.queue.enqueue(&Job::PurgeFinishedJobs, options()).await.unwrap();
    assert!(matches!(first, EnqueueOutcome::Enqueued(_)));
    let second = app.infra.queue.enqueue(&Job::PurgeFinishedJobs, options()).await.unwrap();
    assert_eq!(second, EnqueueOutcome::Duplicate);

    jobs::drain(app.pool(), &Recorder::default(), &worker("w1")).await.unwrap();
    let third = app.infra.queue.enqueue(&Job::PurgeFinishedJobs, options()).await.unwrap();
    assert!(matches!(third, EnqueueOutcome::Enqueued(_)), "finished jobs no longer block the key");
}

#[tokio::test]
async fn retention_jobs_purge_expired_data() {
    let app = TestApp::spawn().await;
    let stale = app.register("stale@example.test").await;
    let fresh = app.register("fresh@example.test").await;
    sqlx::query(
        "UPDATE auth_sessions SET expires_at = now() - interval '30 days', created_at = now() - interval '90 days'
         WHERE id = $1",
    )
    .bind(stale.session_id)
    .execute(app.pool())
    .await
    .unwrap();
    sqlx::query(
        "INSERT INTO jobs (id, kind, payload, status, attempts, run_at, created_at, updated_at, finished_at)
         VALUES (uuidv7(), 'purge_finished_jobs', '{\"kind\": \"purge_finished_jobs\"}', 'succeeded', 1,
                 now() - interval '30 days', now() - interval '30 days', now() - interval '30 days',
                 now() - interval '30 days')",
    )
    .execute(app.pool())
    .await
    .unwrap();

    app.infra.queue.enqueue(&Job::PurgeExpiredAuth, JobOptions::default()).await.unwrap();
    app.infra.queue.enqueue(&Job::PurgeFinishedJobs, JobOptions::default()).await.unwrap();
    assert_eq!(app.run_jobs().await, 2);

    let sessions: Vec<Uuid> = sqlx::query_scalar("SELECT id FROM auth_sessions")
        .fetch_all(app.pool())
        .await
        .unwrap();
    assert_eq!(sessions, [fresh.session_id]);
    let old_jobs: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM jobs WHERE finished_at < now() - interval '8 days'",
    )
    .fetch_one(app.pool())
    .await
    .unwrap();
    assert_eq!(old_jobs, 0);
}

#[tokio::test]
async fn the_audit_log_is_append_only() {
    let app = TestApp::spawn().await;
    let admin = app.account(Role::Admin).await;
    app.api_key(&admin, &["catalog:read"]).await;
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM audit_log").fetch_one(app.pool()).await.unwrap();
    assert_eq!(count, 1);

    for statement in [
        "UPDATE audit_log SET action = 'forged'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ] {
        let error = sqlx::query(statement).execute(app.pool()).await.unwrap_err();
        assert!(error.to_string().contains("append-only"), "{statement}: {error}");
    }
}

#[tokio::test]
async fn schedules_of_a_line_cannot_overlap() {
    let app = TestApp::spawn().await;
    let line: Uuid = sqlx::query_scalar("INSERT INTO lines (code, name) VALUES ('L1', 'Line 1') RETURNING id")
        .fetch_one(app.pool())
        .await
        .unwrap();
    let insert = |day: i16, start: &'static str, end: &'static str, active: bool| {
        sqlx::query(
            "INSERT INTO schedules (line_id, day_of_week, start_time, end_time, frequency_minutes, is_active)
             VALUES ($1, $2, $3::time, $4::time, 15, $5)",
        )
        .bind(line)
        .bind(day)
        .bind(start)
        .bind(end)
        .bind(active)
        .execute(app.pool())
    };
    insert(1, "06:00", "12:00", true).await.unwrap();
    // Touching intervals are fine ([06:00, 12:00) and [12:00, 18:00)).
    insert(1, "12:00", "18:00", true).await.unwrap();
    // Another day, or an inactive draft, may overlap.
    insert(2, "07:00", "09:00", true).await.unwrap();
    insert(1, "07:00", "09:00", false).await.unwrap();

    let overlap = insert(1, "11:00", "13:00", true).await.unwrap_err();
    assert_eq!(overlap.as_database_error().and_then(|e| e.constraint()), Some("schedules_no_overlap"));
    let backwards = insert(3, "10:00", "09:00", true).await.unwrap_err();
    assert_eq!(backwards.as_database_error().and_then(|e| e.constraint()), Some("schedules_time_order"));
    let sunday_zero = insert(0, "10:00", "11:00", true).await.unwrap_err();
    assert_eq!(sunday_zero.as_database_error().and_then(|e| e.constraint()), Some("schedules_day_range"));
}

#[tokio::test]
async fn stops_of_a_line_can_be_reordered_atomically() {
    let app = TestApp::spawn().await;
    let pool = app.pool();
    let line: Uuid = sqlx::query_scalar("INSERT INTO lines (code, name) VALUES ('L2', 'Line 2') RETURNING id")
        .fetch_one(pool)
        .await
        .unwrap();
    let mut stops = Vec::new();
    for (i, (lon, lat)) in [(3.0588, 36.7538), (3.0620, 36.7600)].into_iter().enumerate() {
        let stop: Uuid = sqlx::query_scalar(
            "INSERT INTO stops (name, location) VALUES ($1, ST_MakePoint($2, $3)::geography) RETURNING id",
        )
        .bind(format!("Stop {i}"))
        .bind(lon)
        .bind(lat)
        .fetch_one(pool)
        .await
        .unwrap();
        sqlx::query("INSERT INTO line_stops (line_id, stop_id, position) VALUES ($1, $2, $3)")
            .bind(line)
            .bind(stop)
            .bind(i16::try_from(i).unwrap())
            .execute(pool)
            .await
            .unwrap();
        stops.push(stop);
    }

    // Swapping positions needs the uniqueness check deferred to commit.
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("SET CONSTRAINTS line_stops_position_key DEFERRED").execute(&mut *tx).await.unwrap();
    sqlx::query("UPDATE line_stops SET position = 1 - position WHERE line_id = $1")
        .bind(line)
        .execute(&mut *tx)
        .await
        .unwrap();
    tx.commit().await.unwrap();
    let first: Uuid = sqlx::query_scalar("SELECT stop_id FROM line_stops WHERE line_id = $1 AND position = 0")
        .bind(line)
        .fetch_one(pool)
        .await
        .unwrap();
    assert_eq!(first, stops[1]);

    // Two stops at one position are still rejected.
    let error = sqlx::query("UPDATE line_stops SET position = 0 WHERE line_id = $1")
        .bind(line)
        .execute(pool)
        .await
        .unwrap_err();
    assert_eq!(error.as_database_error().and_then(|e| e.constraint()), Some("line_stops_position_key"));

    // Geography distance in metres (~730 m between the two stops).
    let metres: f64 = sqlx::query_scalar(
        "SELECT ST_Distance(a.location, b.location) FROM stops a, stops b WHERE a.id = $1 AND b.id = $2",
    )
    .bind(stops[0])
    .bind(stops[1])
    .fetch_one(pool)
    .await
    .unwrap();
    assert!((600.0..900.0).contains(&metres), "{metres}");
}

#[tokio::test]
async fn gcra_rate_limiting_in_valkey() {
    let app = TestApp::spawn().await;
    let limiter = ValkeyRateLimiter::new(app.infra.valkey.clone());
    let quota = Quota::per_minute(60, 3);

    for remaining in [2, 1, 0] {
        let decision = limiter.check("test:alice", quota).await.unwrap();
        assert!(decision.allowed);
        assert_eq!(decision.remaining, remaining);
    }
    let denied = limiter.check("test:alice", quota).await.unwrap();
    assert!(!denied.allowed);
    assert!(denied.retry_after > Duration::ZERO && denied.retry_after <= Duration::from_secs(1));

    // Buckets are independent, and refill at the sustained rate (one per second here).
    assert!(limiter.check("test:bob", quota).await.unwrap().allowed);
    tokio::time::sleep(denied.retry_after + Duration::from_millis(50)).await;
    assert!(limiter.check("test:alice", quota).await.unwrap().allowed);
}

#[tokio::test]
async fn session_revocations_are_shared_through_valkey() {
    let app = TestApp::spawn().await;
    let store = ValkeyRevocationStore::new(app.infra.valkey.clone());
    let (revoked, untouched) = (SessionId::from_uuid(Uuid::now_v7()), SessionId::from_uuid(Uuid::now_v7()));
    store.revoke_sessions(&[revoked], Duration::from_secs(60)).await.unwrap();
    assert!(store.is_session_revoked(revoked).await.unwrap());
    assert!(!store.is_session_revoked(untouched).await.unwrap());

    // Markers expire with the access tokens they guard.
    let ttl: i64 = fred::prelude::KeysInterface::pttl(
        app.infra.valkey.pool(),
        app.infra.valkey.key(&format!("revoked:sid:{revoked}")),
    )
    .await
    .unwrap();
    assert!((1..=60_000).contains(&ttl), "{ttl}");
}
