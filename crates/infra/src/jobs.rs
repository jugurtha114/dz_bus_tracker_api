//! Durable job queue on PostgreSQL (`FOR UPDATE SKIP LOCKED`), worker loop and cron scheduler.
//!
//! * Jobs are claimed with a lease; a crashed worker's jobs become claimable again when the
//!   lease expires. Failed jobs are retried with exponential backoff and jitter, then
//!   dead-lettered (`status = 'failed'`).
//! * `NOTIFY dz_jobs` (from an insert trigger) wakes idle workers; polling is the fallback.
//! * Cron firings are claimed per (name, slot) in `cron_runs`, so with N replicas each slot is
//!   enqueued exactly once.

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use chrono::Utc;
use croner::Cron;
use croner::parser::{CronParser, Seconds};
use dz_app::jobs::{CronEntry, Job, JobRunner};
use dz_app::ports::{EnqueueOutcome, JobOptions, JobQueue};
use dz_app::{AppError, AppResult};
use rand::RngExt;
use sqlx::PgPool;
use sqlx::postgres::PgListener;
use tokio::sync::Semaphore;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;
use tracing::Instrument;
use uuid::Uuid;

use crate::pg::db_error;

/// Default number of attempts before a job is dead-lettered.
const DEFAULT_MAX_ATTEMPTS: u16 = 5;
/// Channel used by the insert trigger.
const NOTIFY_CHANNEL: &str = "dz_jobs";

/// Enqueues jobs into the `jobs` table.
#[derive(Debug, Clone)]
pub struct PgJobQueue {
    pool: PgPool,
}

impl PgJobQueue {
    #[must_use]
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl JobQueue for PgJobQueue {
    async fn enqueue(&self, job: &Job, options: JobOptions) -> AppResult<EnqueueOutcome> {
        let payload = serde_json::to_value(job).map_err(AppError::internal)?;
        let id = Uuid::now_v7();
        let max_attempts = i16::try_from(options.max_attempts.unwrap_or(DEFAULT_MAX_ATTEMPTS))
            .unwrap_or(i16::MAX)
            .clamp(1, 100);
        let inserted = sqlx::query_scalar!(
            r#"
            INSERT INTO jobs (id, kind, payload, status, max_attempts, run_at, dedup_key,
                              created_at, updated_at)
            VALUES ($1, $2, $3, 'queued', $4, COALESCE($5, now()), $6, now(), now())
            ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL AND status IN ('queued', 'running')
            DO NOTHING
            RETURNING id
            "#,
            id,
            job.kind(),
            payload,
            max_attempts,
            options.run_at,
            options.dedup_key,
        )
        .fetch_optional(&self.pool)
        .await
        .map_err(db_error)?;
        metrics::counter!("dz_jobs_enqueued_total", "kind" => job.kind()).increment(1);
        Ok(inserted.map_or(EnqueueOutcome::Duplicate, EnqueueOutcome::Enqueued))
    }

    async fn purge_finished(&self, before: chrono::DateTime<Utc>) -> AppResult<u64> {
        let mut tx = self.pool.begin().await.map_err(db_error)?;
        let jobs = sqlx::query!(
            r#"
            DELETE FROM jobs
            WHERE status IN ('succeeded', 'failed') AND finished_at < $1
            "#,
            before,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!("DELETE FROM cron_runs WHERE slot < $1", before)
            .execute(&mut *tx)
            .await
            .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok(jobs.rows_affected())
    }
}

/// Something that can execute a decoded job.
#[async_trait]
pub trait JobExecutor: Send + Sync + 'static {
    async fn execute(&self, job: &Job) -> AppResult<()>;
}

#[async_trait]
impl JobExecutor for JobRunner {
    async fn execute(&self, job: &Job) -> AppResult<()> {
        self.run(job).await
    }
}

/// Worker tuning.
#[derive(Debug, Clone)]
pub struct WorkerConfig {
    /// Identifies this worker in `jobs.locked_by` (host name + process id).
    pub worker_id: String,
    pub concurrency: usize,
    pub poll_interval: Duration,
    /// Must exceed `job_timeout`, otherwise a slow job could be claimed twice.
    pub lease: Duration,
    pub job_timeout: Duration,
}

struct ClaimedJob {
    id: Uuid,
    kind: String,
    payload: serde_json::Value,
    attempts: i16,
    max_attempts: i16,
}

/// Runs the worker loop until `shutdown` is cancelled, then waits for in-flight jobs.
pub async fn run_worker(
    pool: PgPool,
    executor: Arc<dyn JobExecutor>,
    config: WorkerConfig,
    shutdown: CancellationToken,
) -> anyhow::Result<()> {
    anyhow::ensure!(config.lease > config.job_timeout, "worker lease must exceed the job timeout");
    let mut listener = PgListener::connect_with(&pool).await?;
    listener.listen(NOTIFY_CHANNEL).await?;
    let slots = Arc::new(Semaphore::new(config.concurrency.max(1)));
    let mut tasks = JoinSet::new();
    let mut last_reap: Option<Instant> = None;
    tracing::info!(worker_id = %config.worker_id, concurrency = config.concurrency, "worker started");

    loop {
        if last_reap.is_none_or(|t| t.elapsed() > Duration::from_secs(30)) {
            if let Err(error) = reap_expired_leases(&pool).await {
                tracing::warn!(%error, "could not re-queue abandoned jobs");
            }
            last_reap = Some(Instant::now());
        }

        let free = slots.available_permits();
        let mut claimed_all_free = false;
        if free > 0 && !shutdown.is_cancelled() {
            match claim(&pool, &config, free).await {
                Ok(jobs) => {
                    claimed_all_free = jobs.len() == free;
                    for job in jobs {
                        let permit = Arc::clone(&slots).acquire_owned().await?;
                        let pool = pool.clone();
                        let executor = Arc::clone(&executor);
                        let config = config.clone();
                        tasks.spawn(async move {
                            process(&pool, executor.as_ref(), &config, job).await;
                            drop(permit);
                        });
                    }
                }
                Err(error) => tracing::error!(%error, "could not claim jobs"),
            }
        }
        if claimed_all_free {
            // More work may be ready; wait only for a free slot.
            tokio::select! {
                () = shutdown.cancelled() => break,
                _ = tasks.join_next(), if !tasks.is_empty() => {}
            }
            continue;
        }

        tokio::select! {
            () = shutdown.cancelled() => break,
            notification = listener.recv() => {
                if let Err(error) = notification {
                    tracing::warn!(%error, "job notification listener error; falling back to polling");
                    tokio::time::sleep(config.poll_interval).await;
                }
            }
            () = tokio::time::sleep(config.poll_interval) => {}
            _ = tasks.join_next(), if !tasks.is_empty() => {}
        }
    }

    tracing::info!(in_flight = tasks.len(), "worker stopping; waiting for in-flight jobs");
    let drain = async { while tasks.join_next().await.is_some() {} };
    if tokio::time::timeout(config.job_timeout, drain).await.is_err() {
        tracing::warn!("in-flight jobs did not finish in time; their leases will expire");
    }
    Ok(())
}

async fn claim(pool: &PgPool, config: &WorkerConfig, limit: usize) -> AppResult<Vec<ClaimedJob>> {
    sqlx::query_as!(
        ClaimedJob,
        r#"
        UPDATE jobs
        SET status = 'running', attempts = attempts + 1, locked_by = $1,
            locked_until = now() + make_interval(secs => $2), updated_at = now()
        WHERE id IN (
            SELECT id FROM jobs
            WHERE status = 'queued' AND run_at <= now()
            ORDER BY run_at
            LIMIT $3
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, kind, payload, attempts, max_attempts
        "#,
        config.worker_id,
        config.lease.as_secs_f64(),
        i64::try_from(limit).unwrap_or(i64::MAX),
    )
    .fetch_all(pool)
    .await
    .map_err(db_error)
}

async fn reap_expired_leases(pool: &PgPool) -> AppResult<()> {
    let result = sqlx::query!(
        r#"
        UPDATE jobs
        SET status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
            finished_at = CASE WHEN attempts >= max_attempts THEN now() END,
            locked_by = NULL, locked_until = NULL,
            last_error = 'lease expired (worker crashed or was killed)', updated_at = now()
        WHERE status = 'running' AND locked_until < now()
        "#,
    )
    .execute(pool)
    .await
    .map_err(db_error)?;
    if result.rows_affected() > 0 {
        tracing::warn!(jobs = result.rows_affected(), "re-queued jobs with expired leases");
    }
    Ok(())
}

async fn process(pool: &PgPool, executor: &dyn JobExecutor, config: &WorkerConfig, job: ClaimedJob) {
    let span = tracing::info_span!("job", id = %job.id, kind = %job.kind, attempt = job.attempts);
    process_in_span(pool, executor, config, job).instrument(span).await;
}

async fn process_in_span(
    pool: &PgPool,
    executor: &dyn JobExecutor,
    config: &WorkerConfig,
    job: ClaimedJob,
) {
    let started = Instant::now();
    let kind = job.kind.clone();
    let outcome = match serde_json::from_value::<Job>(job.payload) {
        Err(error) => {
            // Undecodable payloads never succeed: dead-letter immediately.
            tracing::error!(%error, "cannot decode job payload");
            finish(pool, &config.worker_id, job.id, Err(format!("undecodable payload: {error}")), true)
                .await
        }
        Ok(decoded) => {
            let result = tokio::time::timeout(config.job_timeout, executor.execute(&decoded)).await;
            let result = match result {
                Ok(Ok(())) => Ok(()),
                Ok(Err(error)) => Err(error.to_string()),
                Err(_) => Err(format!("timed out after {:?}", config.job_timeout)),
            };
            let exhausted = job.attempts >= job.max_attempts;
            if let Err(error) = &result {
                tracing::warn!(%error, exhausted, "job failed");
            }
            let backoff = retry_backoff(u32::try_from(job.attempts).unwrap_or(1));
            finish_with_backoff(pool, &config.worker_id, job.id, result, exhausted, backoff).await
        }
    };
    let label = if outcome.as_ref().is_ok_and(|ok| *ok) { "succeeded" } else { "failed" };
    if let Err(error) = &outcome {
        tracing::error!(%error, "could not record job outcome");
    }
    metrics::counter!("dz_jobs_processed_total", "kind" => kind.clone(), "outcome" => label)
        .increment(1);
    metrics::histogram!("dz_job_duration_seconds", "kind" => kind)
        .record(started.elapsed().as_secs_f64());
}

/// Records the outcome. Returns whether the job succeeded.
async fn finish(
    pool: &PgPool,
    worker_id: &str,
    id: Uuid,
    result: Result<(), String>,
    dead_letter: bool,
) -> AppResult<bool> {
    finish_with_backoff(pool, worker_id, id, result, dead_letter, Duration::ZERO).await
}

async fn finish_with_backoff(
    pool: &PgPool,
    worker_id: &str,
    id: Uuid,
    result: Result<(), String>,
    exhausted: bool,
    backoff: Duration,
) -> AppResult<bool> {
    match result {
        Ok(()) => {
            sqlx::query!(
                r#"
                UPDATE jobs
                SET status = 'succeeded', finished_at = now(), updated_at = now(),
                    locked_by = NULL, locked_until = NULL, last_error = NULL
                WHERE id = $1 AND locked_by = $2 AND status = 'running'
                "#,
                id,
                worker_id,
            )
            .execute(pool)
            .await
            .map_err(db_error)?;
            Ok(true)
        }
        Err(error) => {
            let error: String = error.chars().take(2000).collect();
            sqlx::query!(
                r#"
                UPDATE jobs
                SET status = CASE WHEN $3 THEN 'failed' ELSE 'queued' END,
                    finished_at = CASE WHEN $3 THEN now() END,
                    run_at = CASE WHEN $3 THEN run_at ELSE now() + make_interval(secs => $4) END,
                    locked_by = NULL, locked_until = NULL, last_error = $5, updated_at = now()
                WHERE id = $1 AND locked_by = $2 AND status = 'running'
                "#,
                id,
                worker_id,
                exhausted,
                backoff.as_secs_f64(),
                error,
            )
            .execute(pool)
            .await
            .map_err(db_error)?;
            Ok(false)
        }
    }
}

/// Exponential backoff (5 s × 2^(attempt-1), capped at one hour) with "equal jitter".
#[must_use]
pub fn retry_backoff(attempt: u32) -> Duration {
    let exponent = attempt.saturating_sub(1).min(10);
    let base = Duration::from_secs(5).saturating_mul(1 << exponent).min(Duration::from_secs(3600));
    let half = base / 2;
    let jitter_ms = rand::rng().random_range(0..=u64::try_from(half.as_millis()).unwrap_or(0));
    half + Duration::from_millis(jitter_ms)
}

/// Parses a schedule with a mandatory seconds field.
pub fn parse_schedule(pattern: &str) -> anyhow::Result<Cron> {
    CronParser::builder()
        .seconds(Seconds::Required)
        .build()
        .parse(pattern)
        .map_err(|e| anyhow::anyhow!("invalid cron pattern `{pattern}`: {e}"))
}

/// Enqueues recurring jobs at their scheduled slots until `shutdown` is cancelled.
pub async fn run_cron(
    pool: PgPool,
    queue: Arc<dyn JobQueue>,
    entries: &'static [CronEntry],
    claimant: String,
    shutdown: CancellationToken,
) -> anyhow::Result<()> {
    let schedules = entries
        .iter()
        .map(|e| parse_schedule(e.schedule).map(|cron| (e, cron)))
        .collect::<anyhow::Result<Vec<_>>>()?;
    if schedules.is_empty() {
        shutdown.cancelled().await;
        return Ok(());
    }
    loop {
        let now = Utc::now();
        let mut next = Vec::with_capacity(schedules.len());
        for (entry, cron) in &schedules {
            next.push((*entry, cron.find_next_occurrence(&now, false)?));
        }
        let Some(earliest) = next.iter().map(|(_, at)| *at).min() else {
            return Ok(());
        };
        let wait = (earliest - now).to_std().unwrap_or(Duration::ZERO);
        tokio::select! {
            () = shutdown.cancelled() => return Ok(()),
            () = tokio::time::sleep(wait) => {}
        }
        for (entry, slot) in next.into_iter().filter(|(_, at)| *at == earliest) {
            let claimed = sqlx::query_scalar!(
                r#"
                INSERT INTO cron_runs (name, slot, claimed_by, claimed_at)
                VALUES ($1, $2, $3, now())
                ON CONFLICT DO NOTHING
                RETURNING name
                "#,
                entry.name,
                slot,
                claimant,
            )
            .fetch_optional(&pool)
            .await;
            match claimed {
                Ok(Some(_)) => {
                    let options = JobOptions {
                        dedup_key: Some(format!("cron:{}", entry.name)),
                        ..JobOptions::default()
                    };
                    if let Err(error) = queue.enqueue(&(entry.job)(), options).await {
                        tracing::error!(%error, job = entry.name, "could not enqueue cron job");
                    } else {
                        tracing::info!(job = entry.name, %slot, "cron job enqueued");
                    }
                }
                Ok(None) => tracing::debug!(job = entry.name, %slot, "cron slot claimed elsewhere"),
                Err(error) => tracing::error!(%error, job = entry.name, "could not claim cron slot"),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dz_app::jobs::CRON_SCHEDULE;

    #[test]
    fn backoff_grows_and_is_capped() {
        for attempt in 1..20 {
            let d = retry_backoff(attempt);
            let base = Duration::from_secs(5).saturating_mul(1 << (attempt - 1).min(10));
            let base = base.min(Duration::from_secs(3600));
            assert!(d >= base / 2 && d <= base, "attempt {attempt}: {d:?}");
        }
    }

    #[test]
    fn every_cron_schedule_parses() {
        for entry in CRON_SCHEDULE {
            parse_schedule(entry.schedule).unwrap();
        }
        assert!(parse_schedule("* * * * *").is_err(), "seconds field is mandatory");
    }
}
