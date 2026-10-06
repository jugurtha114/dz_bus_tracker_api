//! PostgreSQL/PostGIS and Valkey for a test binary: from `DZ_TEST_*` URLs or containers.

use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use sqlx::Connection;
use sqlx::postgres::PgConnection;
use testcontainers::core::{IntoContainerPort, WaitFor};
use testcontainers::runners::SyncRunner;
use testcontainers::{Container, GenericImage, ImageExt};

/// Image tags match `compose.yaml` (see `docs/VERSIONS.md`).
const POSTGIS_IMAGE: (&str, &str) = ("postgis/postgis", "18-3.6-alpine");
const VALKEY_IMAGE: (&str, &str) = ("valkey/valkey", "9.1.2-alpine");
/// Label on every container started here: `docker rm -f $(docker ps -aq -f label=dz-testkit)`
/// cleans up after a test run that was killed before its reaper could.
const LABEL: &str = "dz-testkit";

/// Connection URLs of the shared backends.
pub(crate) struct Backends {
    /// A maintenance connection allowed to create and drop databases.
    pub postgres_url: String,
    pub valkey_url: String,
}

static BACKENDS: OnceLock<Backends> = OnceLock::new();

/// The backends of this test binary, started on first use. Blocks: call it from
/// `spawn_blocking`.
pub(crate) fn get() -> &'static Backends {
    // The blocking testcontainers runner owns a Tokio runtime, so it must not run on a test's
    // runtime thread.
    BACKENDS.get_or_init(|| {
        std::thread::spawn(start).join().unwrap_or_else(|_| panic!("test backends failed to start"))
    })
}

fn start() -> Backends {
    let mut started = Vec::new();
    let postgres_url = std::env::var("DZ_TEST_DATABASE_URL").unwrap_or_else(|_| {
        let container = postgis();
        let url = format!(
            "postgres://dz:dz@{}:{}/dz",
            container.get_host().expect("container host"),
            container.get_host_port_ipv4(5432).expect("postgres port"),
        );
        started.push(container.id().to_owned());
        // Kept running until the process exits; the reaper removes it afterwards.
        std::mem::forget(container);
        url
    });
    let valkey_url = std::env::var("DZ_TEST_VALKEY_URL").unwrap_or_else(|_| {
        let container = valkey();
        let url = format!(
            "redis://{}:{}/0",
            container.get_host().expect("container host"),
            container.get_host_port_ipv4(6379).expect("valkey port"),
        );
        started.push(container.id().to_owned());
        std::mem::forget(container);
        url
    });
    if !started.is_empty() {
        spawn_reaper(&started);
    }
    wait_for_postgres(&postgres_url);
    Backends { postgres_url, valkey_url }
}

fn postgis() -> Container<GenericImage> {
    GenericImage::new(POSTGIS_IMAGE.0, POSTGIS_IMAGE.1)
        .with_exposed_port(5432.tcp())
        .with_wait_for(WaitFor::message_on_stderr("database system is ready to accept connections"))
        .with_env_var("POSTGRES_USER", "dz")
        .with_env_var("POSTGRES_PASSWORD", "dz")
        .with_env_var("POSTGRES_DB", "dz")
        // Durability is irrelevant for throw-away test data.
        .with_cmd([
            "postgres",
            "-c",
            "fsync=off",
            "-c",
            "synchronous_commit=off",
            "-c",
            "full_page_writes=off",
            "-c",
            "max_connections=400",
        ])
        .with_label(LABEL, "1")
        .with_startup_timeout(Duration::from_secs(180))
        .start()
        .expect("could not start PostGIS (is Docker or the Podman socket available?)")
}

fn valkey() -> Container<GenericImage> {
    GenericImage::new(VALKEY_IMAGE.0, VALKEY_IMAGE.1)
        .with_exposed_port(6379.tcp())
        .with_wait_for(WaitFor::message_on_stdout("Ready to accept connections"))
        .with_label(LABEL, "1")
        .with_startup_timeout(Duration::from_secs(120))
        .start()
        .expect("could not start Valkey (is Docker or the Podman socket available?)")
}

/// The PostGIS image restarts the server after its init scripts; wait until the final
/// server accepts TCP connections and queries.
fn wait_for_postgres(url: &str) {
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    runtime.block_on(async {
        let deadline = Instant::now() + Duration::from_secs(90);
        loop {
            let attempt = async {
                let mut conn = PgConnection::connect(url).await?;
                sqlx::query("SELECT 1").execute(&mut conn).await?;
                conn.close().await
            };
            match attempt.await {
                Ok(()) => return,
                Err(error) if Instant::now() > deadline => {
                    panic!("PostgreSQL at the test URL never became ready: {error}")
                }
                Err(_) => tokio::time::sleep(Duration::from_millis(250)).await,
            }
        }
    });
}

/// Removes the containers once this process has exited (statics are never dropped, so the
/// containers cannot be removed from inside the process at exit).
#[allow(clippy::zombie_processes, reason = "the reaper must outlive this process")]
fn spawn_reaper(container_ids: &[String]) {
    let ids = container_ids.join(" ");
    let script = format!(
        "while kill -0 {pid} 2>/dev/null; do sleep 1; done; \
         docker rm -fv {ids} >/dev/null 2>&1 || podman rm -fv {ids} >/dev/null 2>&1",
        pid = std::process::id(),
    );
    let spawned = Command::new("sh")
        .args(["-c", &script])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    if spawned.is_err() {
        eprintln!(
            "dz-testkit: could not start the container reaper; remove containers labelled \
             {LABEL} manually"
        );
    }
}
