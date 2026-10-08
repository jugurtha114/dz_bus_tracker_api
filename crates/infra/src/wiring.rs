//! Composition root shared by the binaries and the test kit: connects the adapters and builds
//! the use-case services from validated settings.

use std::sync::Arc;
use std::time::Duration;

use dz_app::account::AccountService;
use dz_app::admin::{AdminUserService, ApiKeyService, AuditService};
use dz_app::auth::{AuthDeps, AuthService, AuthSettings};
use dz_app::drivers::DriverService;
use dz_app::jobs::{JobRunner, JobSettings};
use dz_app::network::{LineService, ScheduleService, StopService};
use dz_app::ports::{
    Clock, IdempotencyStore, LockoutPolicy, Mailer, ObjectStorage, Quota, RateLimiter,
    ReadinessProbe, SystemClock,
};
use dz_app::uploads::UploadService;
use dz_config::Settings;
use dz_domain::password::PasswordPolicy;
use sqlx::PgPool;

use crate::health::DependencyProbe;
use crate::jobs::PgJobQueue;
use crate::jwt::JwtCodec;
use crate::password::{Argon2Config, Argon2Hasher};
use crate::pg::{self, PgStore};
use crate::storage::S3Storage;
use crate::valkey::{Valkey, ValkeyIdempotencyStore, ValkeyRateLimiter, ValkeyRevocationStore};

/// Connected adapters.
#[derive(Clone)]
pub struct Infrastructure {
    pub settings: Arc<Settings>,
    pub pool: PgPool,
    pub valkey: Valkey,
    pub store: Arc<PgStore>,
    pub queue: Arc<PgJobQueue>,
    pub jwt: Arc<JwtCodec>,
    pub hasher: Arc<Argon2Hasher>,
    pub mailer: Arc<dyn Mailer>,
    /// `None` when `storage.endpoint` is not configured.
    pub storage: Option<Arc<S3Storage>>,
    pub clock: Arc<dyn Clock>,
}

/// The use-case services exposed through HTTP.
pub struct Services {
    pub auth: AuthService,
    pub accounts: AccountService,
    pub uploads: Arc<UploadService>,
    pub stops: StopService,
    pub lines: LineService,
    pub schedules: ScheduleService,
    pub drivers: DriverService,
    pub admin_users: AdminUserService,
    pub api_keys: ApiKeyService,
    pub audit: AuditService,
    pub limiter: Arc<dyn RateLimiter>,
    pub idempotency: Arc<dyn IdempotencyStore>,
    pub readiness: Arc<dyn ReadinessProbe>,
    pub jwks: serde_json::Value,
}

/// Builds the access-token codec from the key directory, or an ephemeral key when allowed.
pub fn jwt_codec(settings: &Settings) -> anyhow::Result<JwtCodec> {
    let auth = &settings.auth;
    match (&auth.signing_keys_dir, &auth.active_key_id) {
        (Some(dir), Some(kid)) => JwtCodec::from_dir(dir, kid, &auth.issuer, &auth.audience),
        _ if auth.allow_ephemeral_keys => {
            tracing::warn!("using an ephemeral signing key: tokens will not survive a restart");
            JwtCodec::ephemeral(&auth.issuer, &auth.audience)
        }
        _ => anyhow::bail!("no signing key configured"),
    }
}

/// Builds the password hasher from settings.
pub fn password_hasher(settings: &Settings) -> anyhow::Result<Argon2Hasher> {
    Argon2Hasher::new(
        Argon2Config {
            memory_kib: settings.auth.argon2_memory_kib,
            iterations: settings.auth.argon2_iterations,
            parallelism: settings.auth.argon2_parallelism,
        },
        settings.auth.max_concurrent_hashes,
    )
}

impl Infrastructure {
    /// Connects PostgreSQL and Valkey and builds every adapter.
    pub async fn connect(settings: Settings, application_name: &str) -> anyhow::Result<Self> {
        let pool = pg::connect(&settings.database, application_name).await?;
        let valkey = Valkey::connect(&settings.valkey).await?;
        let mailer = crate::mail::build_mailer(&settings.email)?;
        Self::assemble(settings, pool, valkey, mailer)
    }

    /// Builds the adapters around existing connections (used by tests to inject a mailer).
    pub fn assemble(
        settings: Settings,
        pool: PgPool,
        valkey: Valkey,
        mailer: Arc<dyn Mailer>,
    ) -> anyhow::Result<Self> {
        let jwt = Arc::new(jwt_codec(&settings)?);
        let hasher = Arc::new(password_hasher(&settings)?);
        let clock: Arc<dyn Clock> = Arc::new(SystemClock);
        let storage = if settings.storage.enabled() {
            Some(Arc::new(S3Storage::new(&settings.storage, clock.clone())?))
        } else {
            tracing::warn!("object storage is not configured: uploads are disabled");
            None
        };
        Ok(Self {
            store: Arc::new(PgStore::new(pool.clone())),
            queue: Arc::new(PgJobQueue::new(pool.clone())),
            settings: Arc::new(settings),
            pool,
            valkey,
            jwt,
            hasher,
            mailer,
            storage,
            clock,
        })
    }

    fn object_storage(&self) -> Option<Arc<dyn ObjectStorage>> {
        self.storage.clone().map(|s| s as Arc<dyn ObjectStorage>)
    }

    fn revocation_ttl(&self) -> Duration {
        Duration::from_secs(self.settings.auth.access_token_ttl_secs + 60)
    }

    /// Builds the use-case services.
    #[must_use]
    pub fn services(&self) -> Services {
        let s = &self.settings;
        let revocations = Arc::new(ValkeyRevocationStore::new(self.valkey.clone()));
        let limiter: Arc<dyn RateLimiter> = Arc::new(ValkeyRateLimiter::new(self.valkey.clone()));
        let deps = AuthDeps {
            users: self.store.clone(),
            sessions: self.store.clone(),
            resets: self.store.clone(),
            hasher: self.hasher.clone(),
            tokens: self.jwt.clone(),
            revocations: revocations.clone(),
            jobs: self.queue.clone(),
            limiter: limiter.clone(),
            clock: self.clock.clone(),
        };
        let auth_settings = AuthSettings {
            access_ttl: Duration::from_secs(s.auth.access_token_ttl_secs),
            refresh_ttl: Duration::from_secs(s.auth.refresh_token_ttl_secs),
            session_max_lifetime: Duration::from_secs(s.auth.session_max_lifetime_secs),
            password_policy: PasswordPolicy { min_length: s.auth.password_min_length, max_length: 128 },
            lockout: LockoutPolicy {
                threshold: s.auth.lockout_threshold,
                base: Duration::from_secs(s.auth.lockout_base_secs),
            },
            reset_quota: Quota { limit: 3, period: Duration::from_secs(15 * 60), burst: 3 },
            revocation_fail_open: s.auth.revocation_fail_open,
        };
        let uploads = Arc::new(UploadService::new(
            self.store.clone(),
            self.object_storage(),
            self.clock.clone(),
            Duration::from_secs(s.storage.upload_ttl_secs),
        ));
        Services {
            auth: AuthService::new(deps, auth_settings),
            accounts: AccountService::new(self.store.clone(), uploads.clone(), self.clock.clone()),
            stops: StopService::new(self.store.clone(), uploads.clone(), self.clock.clone()),
            lines: LineService::new(self.store.clone(), self.store.clone(), self.clock.clone()),
            schedules: ScheduleService::new(
                self.store.clone(),
                self.store.clone(),
                self.clock.clone(),
            ),
            drivers: DriverService::new(self.store.clone(), uploads.clone(), self.clock.clone()),
            uploads,
            admin_users: AdminUserService::new(
                self.store.clone(),
                revocations,
                self.clock.clone(),
                self.revocation_ttl(),
            ),
            api_keys: ApiKeyService::new(self.store.clone(), self.clock.clone()),
            audit: AuditService::new(self.store.clone()),
            limiter,
            idempotency: Arc::new(ValkeyIdempotencyStore::new(self.valkey.clone())),
            readiness: Arc::new(DependencyProbe::new(self.pool.clone(), self.valkey.clone())),
            jwks: self.jwt.jwks().clone(),
        }
    }

    /// The executor of background jobs.
    #[must_use]
    pub fn job_runner(&self) -> JobRunner {
        let s = &self.settings;
        JobRunner {
            users: self.store.clone(),
            sessions: self.store.clone(),
            resets: self.store.clone(),
            uploads: self.store.clone(),
            drivers: self.store.clone(),
            storage: self.object_storage(),
            mailer: self.mailer.clone(),
            queue: self.queue.clone(),
            clock: self.clock.clone(),
            settings: JobSettings {
                password_reset_ttl: Duration::from_secs(s.auth.password_reset_ttl_secs),
                password_reset_url: s.auth.password_reset_url.to_string(),
                auth_retention: Duration::from_secs(7 * 24 * 3600),
                job_retention: Duration::from_secs(u64::from(s.worker.retention_days) * 24 * 3600),
                upload_purge_grace: Duration::from_secs(3600),
            },
        }
    }

    /// Closes connections.
    pub async fn close(&self) {
        self.pool.close().await;
        self.valkey.quit().await;
    }
}
