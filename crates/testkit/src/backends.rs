//! PostgreSQL/PostGIS, Valkey and S3 (RustFS) for a test binary: from `DZ_TEST_*` URLs or
//! containers.

use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use sqlx::Connection;
use sqlx::postgres::PgConnection;
use url::Url;
use testcontainers::core::{IntoContainerPort, WaitFor};
use testcontainers::runners::SyncRunner;
use testcontainers::{Container, GenericImage, ImageExt};

/// Image tags match `compose.yaml` (see `docs/VERSIONS.md`).
const POSTGIS_IMAGE: (&str, &str) = ("postgis/postgis", "18-3.6-alpine");
const VALKEY_IMAGE: (&str, &str) = ("valkey/valkey", "9.1.2-alpine");
const RUSTFS_IMAGE: (&str, &str) = ("rustfs/rustfs", "1.0.1");
/// Root credentials of the RustFS container started here.
const RUSTFS_ACCESS_KEY: &str = "dz-test-access";
const RUSTFS_SECRET_KEY: &str = "dz-test-secret-0123456789";
/// Label on every container started here: `docker rm -f $(docker ps -aq -f label=dz-testkit)`
/// cleans up after a test run that was killed before its reaper could.
const LABEL: &str = "dz-testkit";

/// Connection URLs of the shared backends.
pub(crate) struct Backends {
    /// A maintenance connection allowed to create and drop databases.
    pub postgres_url: String,
    pub valkey_url: String,
    pub s3: S3Backend,
}

/// An S3-compatible server whose root credentials may create buckets.
#[derive(Debug, Clone)]
pub(crate) struct S3Backend {
    pub endpoint: Url,
    pub access_key: String,
    pub secret_key: String,
}

impl S3Backend {
    /// Parses `DZ_TEST_S3_URL`: `http://<access key>:<secret key>@<host>:<port>` (the keys must
    /// consist of URL-safe characters, as RustFS and MinIO keys usually do).
    fn from_url(raw: &str) -> Self {
        let mut endpoint = Url::parse(raw).expect("DZ_TEST_S3_URL is a URL");
        let access_key = endpoint.username().to_owned();
        let secret_key = endpoint.password().unwrap_or_default().to_owned();
        assert!(
            !access_key.is_empty() && !secret_key.is_empty(),
            "DZ_TEST_S3_URL must carry credentials: http://<access key>:<secret key>@host:port"
        );
        endpoint.set_username("").expect("URL with a host");
        endpoint.set_password(None).expect("URL with a host");
        Self { endpoint, access_key, secret_key }
    }
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
    let s3 = std::env::var("DZ_TEST_S3_URL").map_or_else(
        |_| {
            let container = rustfs();
            let endpoint = format!(
                "http://{}:{}",
                container.get_host().expect("container host"),
                container.get_host_port_ipv4(9000).expect("S3 port"),
            );
            started.push(container.id().to_owned());
            std::mem::forget(container);
            S3Backend {
                endpoint: endpoint.parse().expect("S3 endpoint"),
                access_key: RUSTFS_ACCESS_KEY.to_owned(),
                secret_key: RUSTFS_SECRET_KEY.to_owned(),
            }
        },
        |url| S3Backend::from_url(&url),
    );
    if !started.is_empty() {
        spawn_reaper(&started);
    }
    wait_for_postgres(&postgres_url);
    wait_for_s3(&s3.endpoint);
    Backends { postgres_url, valkey_url, s3 }
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

fn rustfs() -> Container<GenericImage> {
    GenericImage::new(RUSTFS_IMAGE.0, RUSTFS_IMAGE.1)
        .with_exposed_port(9000.tcp())
        .with_wait_for(WaitFor::message_on_stdout("Starting:"))
        .with_env_var("RUSTFS_ACCESS_KEY", RUSTFS_ACCESS_KEY)
        .with_env_var("RUSTFS_SECRET_KEY", RUSTFS_SECRET_KEY)
        .with_label(LABEL, "1")
        .with_startup_timeout(Duration::from_secs(120))
        .start()
        .expect("could not start RustFS (is Docker or the Podman socket available?)")
}

/// The entrypoint prints `Starting:` before the server listens; wait for its health endpoint.
fn wait_for_s3(endpoint: &Url) {
    let health = endpoint.join("health").expect("health URL");
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    runtime.block_on(async {
        let client = dz_infra::storage::http_client(Duration::from_secs(2)).unwrap();
        let deadline = Instant::now() + Duration::from_secs(60);
        loop {
            match client.get(health.clone()).send().await {
                Ok(response) if response.status().is_success() => return,
                Ok(response) if Instant::now() > deadline => {
                    panic!("S3 at {endpoint} is not healthy: {}", response.status())
                }
                Err(error) if Instant::now() > deadline => {
                    panic!("S3 at {endpoint} never became ready: {error}")
                }
                _ => tokio::time::sleep(Duration::from_millis(250)).await,
            }
        }
    });
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
