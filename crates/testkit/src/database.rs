//! One fresh database per test, cloned from a migrated template.

use std::hash::{DefaultHasher, Hash, Hasher};

use sqlx::postgres::PgConnection;
use sqlx::{AssertSqlSafe, Connection};
use tokio::sync::OnceCell;
use url::Url;
use uuid::Uuid;

use crate::backends;

/// Session-level advisory lock serialising template creation across test processes.
const TEMPLATE_LOCK: i64 = 0x647a_7465_7374;

static TEMPLATE: OnceCell<String> = OnceCell::const_new();

/// A database owned by one test; dropped (with `FORCE`) when the value is dropped.
/// Set `DZ_TEST_KEEP_DB=1` to keep the databases of failed tests for inspection.
#[derive(Debug)]
pub struct TestDatabase {
    pub name: String,
    pub url: String,
    pub valkey_url: String,
    admin_url: String,
}

impl TestDatabase {
    /// Creates an empty, fully migrated database.
    pub async fn create() -> Self {
        let backends = tokio::task::spawn_blocking(backends::get).await.unwrap();
        let template = TEMPLATE
            .get_or_try_init(|| create_template(&backends.postgres_url))
            .await
            .unwrap_or_else(|error| panic!("could not prepare the template database: {error:#}"));
        let name = format!("dz_t_{}", Uuid::now_v7().simple());
        let mut admin = PgConnection::connect(&backends.postgres_url).await.unwrap();
        execute(&mut admin, format!(r#"CREATE DATABASE "{name}" TEMPLATE "{template}""#)).await.unwrap();
        admin.close().await.unwrap();
        Self {
            url: database_url(&backends.postgres_url, &name),
            name,
            valkey_url: backends.valkey_url.clone(),
            admin_url: backends.postgres_url.clone(),
        }
    }
}

impl Drop for TestDatabase {
    fn drop(&mut self) {
        if std::thread::panicking() && std::env::var_os("DZ_TEST_KEEP_DB").is_some() {
            eprintln!("dz-testkit: kept database {} ({})", self.name, self.url);
            return;
        }
        let admin_url = self.admin_url.clone();
        let name = self.name.clone();
        // Drop runs inside the test's runtime; use a separate thread with its own runtime.
        let dropped = std::thread::spawn(move || {
            let runtime =
                tokio::runtime::Builder::new_current_thread().enable_all().build().ok()?;
            runtime.block_on(async {
                let mut admin = PgConnection::connect(&admin_url).await.ok()?;
                execute(&mut admin, format!(r#"DROP DATABASE IF EXISTS "{name}" WITH (FORCE)"#))
                    .await
                    .ok()?;
                admin.close().await.ok()
            })
        })
        .join();
        if !matches!(dropped, Ok(Some(()))) {
            eprintln!("dz-testkit: could not drop database {}", self.name);
        }
    }
}

/// Builds (once per migration set, shared across processes) a migrated template database.
/// The name embeds a fingerprint of the migrations, so changing a migration builds a new one.
async fn create_template(admin_url: &str) -> anyhow::Result<String> {
    let name = format!("dz_tpl_{:016x}", migrations_fingerprint());
    let mut admin = PgConnection::connect(admin_url).await?;
    sqlx::query("SELECT pg_advisory_lock($1)").bind(TEMPLATE_LOCK).execute(&mut admin).await?;
    let exists: bool =
        sqlx::query_scalar("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)")
            .bind(&name)
            .fetch_one(&mut admin)
            .await?;
    if !exists {
        // Built under a temporary name and renamed when complete, so a crash never leaves a
        // half-migrated template behind.
        let building = format!("{name}_build");
        execute(&mut admin, format!(r#"DROP DATABASE IF EXISTS "{building}" WITH (FORCE)"#)).await?;
        execute(&mut admin, format!(r#"CREATE DATABASE "{building}""#)).await?;
        let mut settings = dz_config::DatabaseSettings {
            url: database_url(admin_url, &building).into(),
            ..dz_config::DatabaseSettings::default()
        };
        settings.min_connections = 0;
        settings.max_connections = 2;
        let pool = dz_infra::pg::connect(&settings, "dz-testkit").await?;
        dz_infra::pg::migrate(&pool).await?;
        pool.close().await;
        execute(&mut admin, format!(r#"ALTER DATABASE "{building}" RENAME TO "{name}""#)).await?;
        // Nobody may connect to a template, otherwise `CREATE DATABASE … TEMPLATE` fails.
        execute(&mut admin, format!(r#"ALTER DATABASE "{name}" WITH IS_TEMPLATE true ALLOW_CONNECTIONS false"#))
            .await?;
    }
    sqlx::query("SELECT pg_advisory_unlock($1)").bind(TEMPLATE_LOCK).execute(&mut admin).await?;
    admin.close().await?;
    Ok(name)
}

fn migrations_fingerprint() -> u64 {
    let mut hasher = DefaultHasher::new();
    for migration in dz_infra::pg::MIGRATOR.iter() {
        migration.version.hash(&mut hasher);
        migration.checksum.hash(&mut hasher);
    }
    hasher.finish()
}

fn database_url(admin_url: &str, database: &str) -> String {
    let mut url = Url::parse(admin_url).expect("DZ_TEST_DATABASE_URL is a URL");
    url.set_path(&format!("/{database}"));
    url.to_string()
}

/// Runs DDL built from names this module generated itself (identifiers cannot be bound).
async fn execute(conn: &mut PgConnection, sql: String) -> sqlx::Result<()> {
    sqlx::raw_sql(AssertSqlSafe(sql)).execute(conn).await.map(|_| ())
}
