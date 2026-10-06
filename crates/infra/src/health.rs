//! Readiness probe: database, Valkey and migration status, each with its own timeout.

use std::future::Future;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use dz_app::ports::{ComponentHealth, ReadinessProbe};
use sqlx::PgPool;

use crate::pg::migration_status;
use crate::valkey::Valkey;

/// Per-check timeout: readiness must answer quickly even when a dependency hangs.
const CHECK_TIMEOUT: Duration = Duration::from_secs(2);

pub struct DependencyProbe {
    pool: PgPool,
    valkey: Valkey,
}

impl DependencyProbe {
    #[must_use]
    pub fn new(pool: PgPool, valkey: Valkey) -> Self {
        Self { pool, valkey }
    }
}

async fn timed<F>(name: &'static str, check: F) -> ComponentHealth
where
    F: Future<Output = anyhow::Result<Option<String>>>,
{
    let started = Instant::now();
    let outcome = tokio::time::timeout(CHECK_TIMEOUT, check).await;
    let latency_ms = u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX);
    let (healthy, detail) = match outcome {
        Ok(Ok(None)) => (true, None),
        Ok(Ok(Some(problem))) => (false, Some(problem)),
        Ok(Err(error)) => (false, Some(error.to_string())),
        Err(_) => (false, Some(format!("timed out after {CHECK_TIMEOUT:?}"))),
    };
    if !healthy {
        tracing::warn!(component = name, detail = ?detail, "readiness check failed");
    }
    ComponentHealth { name, healthy, latency_ms, detail }
}

#[async_trait]
impl ReadinessProbe for DependencyProbe {
    async fn check(&self) -> Vec<ComponentHealth> {
        let database = timed("database", async {
            sqlx::query_scalar::<_, i32>("SELECT 1").fetch_one(&self.pool).await?;
            Ok(None)
        });
        let migrations = timed("migrations", async {
            let status = migration_status(&self.pool).await?;
            Ok((!status.is_up_to_date()).then(|| {
                format!(
                    "pending: {:?}, checksum mismatch: {:?}",
                    status.pending, status.checksum_mismatch
                )
            }))
        });
        let valkey = timed("valkey", async {
            self.valkey.ping().await?;
            Ok(None)
        });
        let (database, migrations, valkey) = tokio::join!(database, migrations, valkey);
        vec![database, migrations, valkey]
    }
}
