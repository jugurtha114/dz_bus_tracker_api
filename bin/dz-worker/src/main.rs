//! `dz-worker`: executes durable jobs and enqueues the cron schedule.
//!
//! Any number of replicas can run: jobs are claimed with `SKIP LOCKED` leases and each cron
//! slot is claimed exactly once. On SIGTERM the worker stops claiming and finishes in-flight
//! jobs (bounded by the job timeout).

use std::process::ExitCode;
use std::sync::Arc;
use std::time::Duration;

use axum::Router;
use axum::routing::get;
use dz_app::jobs::CRON_SCHEDULE;
use dz_config::Settings;
use dz_infra::jobs::{JobExecutor, WorkerConfig, run_cron, run_worker};
use dz_infra::wiring::Infrastructure;
use dz_infra::{pg, shutdown, telemetry};
use tokio_util::sync::CancellationToken;

fn main() -> ExitCode {
    let run = || -> anyhow::Result<()> {
        let settings = Settings::load()?;
        let _telemetry = telemetry::init(&settings.telemetry, "worker")?;
        let runtime = tokio::runtime::Builder::new_multi_thread().enable_all().build()?;
        let result = runtime.block_on(work(settings));
        if let Err(error) = &result {
            tracing::error!(error = %format!("{error:#}"), "worker terminated with an error");
        }
        result
    };
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("dz-worker: {error:#}");
            ExitCode::FAILURE
        }
    }
}

fn worker_id() -> String {
    let host = std::env::var("HOSTNAME").unwrap_or_else(|_| "worker".to_owned());
    format!("{host}:{}:{}", std::process::id(), &uuid::Uuid::new_v4().simple().to_string()[..6])
}

async fn work(settings: Settings) -> anyhow::Result<()> {
    let metrics = telemetry::install_metrics()?;
    let metrics_addr = settings.http.metrics_addr;
    let worker = settings.worker.clone();
    let infra = Infrastructure::connect(settings, "dz-worker").await?;
    let status = pg::migration_status(&infra.pool).await?;
    anyhow::ensure!(
        status.is_up_to_date(),
        "database schema is not up to date (pending {:?}); run `dz-cli migrate` first",
        status.pending
    );

    let shutdown = CancellationToken::new();
    shutdown::cancel_on_signal(shutdown.clone());

    if let Some(addr) = metrics_addr {
        let listener = tokio::net::TcpListener::bind(addr).await?;
        let router = Router::new()
            .route("/metrics", get(move || std::future::ready(metrics.render())))
            .route("/health/live", get(|| std::future::ready("ok")));
        let token = shutdown.clone();
        tokio::spawn(async move {
            if let Err(error) =
                axum::serve(listener, router).with_graceful_shutdown(token.cancelled_owned()).await
            {
                tracing::error!(%error, "metrics listener failed");
            }
        });
    }

    let id = worker_id();
    let executor: Arc<dyn JobExecutor> = Arc::new(infra.job_runner());
    let config = WorkerConfig {
        worker_id: id.clone(),
        concurrency: worker.concurrency,
        poll_interval: Duration::from_millis(worker.poll_interval_ms),
        lease: Duration::from_secs(worker.lease_secs),
        job_timeout: Duration::from_secs(worker.job_timeout_secs),
    };
    let jobs = tokio::spawn(run_worker(infra.pool.clone(), executor, config, shutdown.clone()));
    let cron = tokio::spawn(run_cron(
        infra.pool.clone(),
        infra.queue.clone(),
        CRON_SCHEDULE,
        id,
        shutdown.clone(),
    ));

    let (jobs, cron) = tokio::join!(jobs, cron);
    shutdown.cancel();
    infra.close().await;
    jobs??;
    cron??;
    tracing::info!("worker stopped");
    Ok(())
}
