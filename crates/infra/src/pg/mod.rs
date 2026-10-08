//! PostgreSQL adapters (sqlx, compile-time checked queries).

mod api_keys;
mod audit;
pub mod effects;
mod resets;
mod sessions;
mod uploads;
mod users;

use std::str::FromStr;
use std::time::Duration;

use dz_app::AppError;
use dz_config::DatabaseSettings;
use secrecy::ExposeSecret;
use sqlx::PgPool;
use sqlx::migrate::Migrator;
use sqlx::postgres::{PgConnectOptions, PgPoolOptions};

/// Migrations embedded at compile time from `/migrations`.
pub static MIGRATOR: Migrator = sqlx::migrate!("../../migrations");

/// Opens the connection pool. Every connection gets a server-side `statement_timeout` so that a
/// runaway query cannot hold a connection forever.
pub async fn connect(settings: &DatabaseSettings, application_name: &str) -> anyhow::Result<PgPool> {
    let options = PgConnectOptions::from_str(settings.url.expose_secret())?
        .application_name(application_name)
        .statement_cache_capacity(256)
        .options([
            ("statement_timeout", settings.statement_timeout_ms.to_string()),
            ("idle_in_transaction_session_timeout", "30000".to_owned()),
        ]);
    let pool = PgPoolOptions::new()
        .max_connections(settings.max_connections)
        .min_connections(settings.min_connections)
        .acquire_timeout(Duration::from_millis(settings.acquire_timeout_ms))
        .idle_timeout(Duration::from_secs(settings.idle_timeout_secs))
        .max_lifetime(Duration::from_secs(settings.max_lifetime_secs))
        .connect_with(options)
        .await?;
    Ok(pool)
}

/// Applies pending migrations (idempotent; guarded by an advisory lock in sqlx).
pub async fn migrate(pool: &PgPool) -> anyhow::Result<()> {
    MIGRATOR.run(pool).await?;
    Ok(())
}

/// Status of the embedded migrations against the database.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MigrationStatus {
    pub expected: usize,
    pub applied: usize,
    /// Versions embedded in the binary but missing or failed in the database.
    pub pending: Vec<i64>,
    /// Applied versions whose checksum differs from the embedded file.
    pub checksum_mismatch: Vec<i64>,
}

impl MigrationStatus {
    #[must_use]
    pub fn is_up_to_date(&self) -> bool {
        self.pending.is_empty() && self.checksum_mismatch.is_empty()
    }
}

/// Compares embedded migrations with `_sqlx_migrations`.
pub async fn migration_status(pool: &PgPool) -> anyhow::Result<MigrationStatus> {
    let exists: Option<String> =
        sqlx::query_scalar("SELECT to_regclass('_sqlx_migrations')::text").fetch_one(pool).await?;
    let applied: Vec<(i64, bool, Vec<u8>)> = if exists.is_some() {
        sqlx::query_as("SELECT version, success, checksum FROM _sqlx_migrations")
            .fetch_all(pool)
            .await?
    } else {
        Vec::new()
    };
    let mut status = MigrationStatus {
        expected: MIGRATOR.iter().filter(|m| m.migration_type.is_up_migration()).count(),
        applied: applied.iter().filter(|(_, ok, _)| *ok).count(),
        pending: Vec::new(),
        checksum_mismatch: Vec::new(),
    };
    for migration in MIGRATOR.iter().filter(|m| m.migration_type.is_up_migration()) {
        match applied.iter().find(|(v, _, _)| *v == migration.version) {
            Some((_, true, checksum)) if checksum.as_slice() == migration.checksum.as_ref() => {}
            Some((_, true, _)) => status.checksum_mismatch.push(migration.version),
            _ => status.pending.push(migration.version),
        }
    }
    Ok(status)
}

/// The PostgreSQL implementation of every repository port.
#[derive(Debug, Clone)]
pub struct PgStore {
    pool: PgPool,
}

impl PgStore {
    #[must_use]
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.pool
    }
}

/// Maps a database error to an application error. Constraint violations that clients can
/// cause are mapped by the caller; everything else is internal or "unavailable".
pub(crate) fn db_error(error: sqlx::Error) -> AppError {
    match &error {
        sqlx::Error::PoolTimedOut | sqlx::Error::PoolClosed | sqlx::Error::Io(_) => {
            tracing::error!(%error, "database unavailable");
            AppError::Unavailable("database")
        }
        sqlx::Error::Database(db) if db.code().as_deref() == Some("57014") => {
            tracing::error!(%error, "database statement timeout");
            AppError::Unavailable("database")
        }
        _ => AppError::internal(error),
    }
}

/// The name of the violated constraint, if the error is a constraint violation.
pub(crate) fn violated_constraint(error: &sqlx::Error) -> Option<&str> {
    match error {
        sqlx::Error::Database(db) => db.constraint(),
        _ => None,
    }
}

/// Escapes `%`, `_` and `\` for use in a `LIKE ... ESCAPE '\'` pattern.
pub(crate) fn like_prefix(prefix: &str) -> String {
    let mut out = String::with_capacity(prefix.len() + 1);
    for c in prefix.chars() {
        if matches!(c, '%' | '_' | '\\') {
            out.push('\\');
        }
        out.push(c);
    }
    out.push('%');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn like_prefix_escapes_wildcards() {
        assert_eq!(like_prefix("a_b%c\\"), "a\\_b\\%c\\\\%");
    }
}
