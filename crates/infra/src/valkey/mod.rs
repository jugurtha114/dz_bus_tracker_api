//! Valkey adapters (cache, rate limiting, revocation, pub/sub) built on `fred`.

mod idempotency;
mod rate_limit;
mod revocation;

use std::time::Duration;

use dz_config::ValkeySettings;
use fred::prelude::{Builder, ClientLike, Config, Pool, ReconnectPolicy};
use secrecy::ExposeSecret;

pub use idempotency::ValkeyIdempotencyStore;
pub use rate_limit::ValkeyRateLimiter;
pub use revocation::ValkeyRevocationStore;

/// A connection pool plus the key prefix of this deployment.
#[derive(Clone)]
pub struct Valkey {
    pool: Pool,
    prefix: String,
}

impl std::fmt::Debug for Valkey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Valkey").field("prefix", &self.prefix).finish_non_exhaustive()
    }
}

impl Valkey {
    /// Connects the pool. Commands time out instead of hanging when Valkey is unreachable, and
    /// the client reconnects in the background with exponential backoff.
    pub async fn connect(settings: &ValkeySettings) -> anyhow::Result<Self> {
        let config = Config::from_url(settings.url.expose_secret())?;
        let timeout = Duration::from_millis(settings.command_timeout_ms);
        let pool = Builder::from_config(config)
            .with_connection_config(|c| {
                c.connection_timeout = timeout;
                c.internal_command_timeout = timeout;
                c.max_command_attempts = 2;
            })
            .with_performance_config(|c| {
                c.default_command_timeout = timeout;
            })
            .set_policy(ReconnectPolicy::new_exponential(0, 100, 5_000, 2))
            .build_pool(settings.pool_size)?;
        pool.init().await?;
        Ok(Self { pool, prefix: settings.key_prefix.clone() })
    }

    #[must_use]
    pub fn pool(&self) -> &Pool {
        &self.pool
    }

    /// The fully qualified key for `key`.
    #[must_use]
    pub fn key(&self, key: &str) -> String {
        format!("{}{key}", self.prefix)
    }

    /// Round-trip check used by the readiness probe.
    pub async fn ping(&self) -> anyhow::Result<()> {
        let _: String = self.pool.next().ping(None).await?;
        Ok(())
    }

    /// Closes all connections.
    pub async fn quit(&self) {
        if let Err(error) = self.pool.quit().await {
            tracing::warn!(%error, "error while closing valkey connections");
        }
    }
}
