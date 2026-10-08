//! `dz-api`: the HTTP API server.
//!
//! * `dz-api` / `dz-api serve` — run the server (plain HTTP/1.1 + h2c behind nginx).
//! * `dz-api healthcheck` — probe the local server; used as the container health check
//!   (the runtime image has no shell or curl).
//! * `dz-api openapi` — print the OpenAPI document (CI diffs it against the committed copy).

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::ExitCode;
use std::time::Duration;

use axum::Router;
use axum::routing::get;
use axum::serve::ListenerExt;
use clap::{Parser, Subcommand};
use dz_config::Settings;
use dz_http::state::{AppServices, AppState};
use dz_infra::wiring::Infrastructure;
use dz_infra::{pg, shutdown, telemetry};
use tokio_util::sync::CancellationToken;

#[derive(Parser)]
#[command(name = "dz-api", version, about = "DZ Bus Tracker HTTP API")]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Run the API server (default).
    Serve,
    /// Exit 0 when the local server answers `/health/live` with 200.
    Healthcheck {
        /// Port to probe (default: the port of `DZ_HTTP__ADDR`). The worker image probes its
        /// metrics port, which also serves `/health/live`.
        #[arg(long)]
        port: Option<u16>,
    },
    /// Print the OpenAPI document as JSON.
    Openapi,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let result = match cli.command.unwrap_or(Command::Serve) {
        Command::Serve => serve(),
        Command::Healthcheck { port } => return healthcheck(port),
        Command::Openapi => print_openapi(),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            // Logging may not be initialised (e.g. configuration errors): use stderr.
            eprintln!("dz-api: {error:#}");
            ExitCode::FAILURE
        }
    }
}

fn print_openapi() -> anyhow::Result<()> {
    let json = dz_http::openapi().to_pretty_json()?;
    std::io::stdout().write_all(json.as_bytes())?;
    std::io::stdout().write_all(b"\n")?;
    Ok(())
}

/// Minimal HTTP probe without TLS or extra dependencies.
fn healthcheck(port: Option<u16>) -> ExitCode {
    let port = port.unwrap_or_else(|| {
        let addr = std::env::var("DZ_HTTP__ADDR").unwrap_or_else(|_| "0.0.0.0:8080".to_owned());
        addr.rsplit(':').next().and_then(|p| p.parse::<u16>().ok()).unwrap_or(8080)
    });
    let probe = || -> std::io::Result<bool> {
        let target = SocketAddr::from(([127, 0, 0, 1], port));
        let mut stream = TcpStream::connect_timeout(&target, Duration::from_secs(2))?;
        stream.set_read_timeout(Some(Duration::from_secs(2)))?;
        stream.write_all(
            b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )?;
        let mut head = [0u8; 12];
        stream.read_exact(&mut head)?;
        Ok(head.starts_with(b"HTTP/1.1 200"))
    };
    match probe() {
        Ok(true) => ExitCode::SUCCESS,
        _ => ExitCode::FAILURE,
    }
}

fn serve() -> anyhow::Result<()> {
    let settings = Settings::load()?;
    // Telemetry is initialised before the runtime (see `telemetry::init`).
    let _telemetry = telemetry::init(&settings.telemetry, "api")?;
    let runtime = tokio::runtime::Builder::new_multi_thread().enable_all().build()?;
    let result = runtime.block_on(run(settings));
    if let Err(error) = &result {
        tracing::error!(error = %format!("{error:#}"), "api terminated with an error");
    }
    result
}

async fn run(settings: Settings) -> anyhow::Result<()> {
    let metrics = telemetry::install_metrics()?;
    let addr = settings.http.addr;
    let metrics_addr = settings.http.metrics_addr;
    let grace = Duration::from_secs(settings.http.shutdown_grace_secs);
    let migrate_on_start = settings.database.migrate_on_start;

    let infra = Infrastructure::connect(settings, "dz-api").await?;
    if migrate_on_start {
        pg::migrate(&infra.pool).await?;
        tracing::info!("migrations applied");
    }
    let status = pg::migration_status(&infra.pool).await?;
    if !status.is_up_to_date() {
        tracing::warn!(
            pending = ?status.pending,
            checksum_mismatch = ?status.checksum_mismatch,
            "database schema is not up to date; readiness will fail until `dz-cli migrate` runs"
        );
    }

    let services = infra.services();
    let state = AppState::new(AppServices {
        settings: infra.settings.clone(),
        auth: services.auth,
        accounts: services.accounts,
        uploads: services.uploads,
        stops: services.stops,
        lines: services.lines,
        schedules: services.schedules,
        admin_users: services.admin_users,
        api_keys: services.api_keys,
        audit: services.audit,
        limiter: services.limiter,
        idempotency: services.idempotency,
        readiness: services.readiness,
        jwks: services.jwks,
    });
    let app = dz_http::router(state);

    let shutdown = CancellationToken::new();
    shutdown::cancel_on_signal(shutdown.clone());

    let metrics_task = match metrics_addr {
        Some(metrics_addr) => {
            let listener = tokio::net::TcpListener::bind(metrics_addr).await?;
            tracing::info!(%metrics_addr, "metrics listener started");
            let router = Router::new().route("/metrics", get(move || std::future::ready(metrics.render())));
            let token = shutdown.clone();
            Some(tokio::spawn(async move {
                axum::serve(listener, router).with_graceful_shutdown(token.cancelled_owned()).await
            }))
        }
        None => None,
    };

    let listener = tokio::net::TcpListener::bind(addr).await?.tap_io(|tcp| {
        if let Err(error) = tcp.set_nodelay(true) {
            tracing::debug!(%error, "could not set TCP_NODELAY");
        }
    });
    tracing::info!(%addr, "api listening");
    let server = axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>())
        .with_graceful_shutdown(shutdown.clone().cancelled_owned());
    let server = tokio::spawn(async move { server.await });

    shutdown.cancelled().await;
    tracing::info!(grace_secs = grace.as_secs(), "draining in-flight requests");
    match tokio::time::timeout(grace, server).await {
        Ok(Ok(Ok(()))) => tracing::info!("http server stopped"),
        Ok(Ok(Err(error))) => tracing::error!(%error, "http server error"),
        Ok(Err(error)) => tracing::error!(%error, "http server task failed"),
        Err(_) => tracing::warn!("grace period elapsed; dropping remaining connections"),
    }
    if let Some(task) = metrics_task {
        task.abort();
    }
    infra.close().await;
    tracing::info!("api stopped");
    Ok(())
}
