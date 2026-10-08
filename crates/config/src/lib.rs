//! Runtime configuration.
//!
//! Every setting comes from an environment variable named `DZ_<SECTION>__<KEY>`
//! (e.g. `DZ_DATABASE__URL`). Any variable may instead be supplied through a file by appending
//! `_FILE` (e.g. `DZ_DATABASE__URL_FILE=/run/secrets/database_url`), which is how container
//! secrets are mounted. Unknown `DZ_*` variables are rejected so that typos fail fast.
//!
//! [`Settings::load`] parses and then [`Settings::validate`]s; binaries refuse to start on error.

use std::collections::BTreeMap;
use std::net::SocketAddr;
use std::path::PathBuf;

use figment::Figment;
use ipnet::IpNet;
use secrecy::{ExposeSecret, SecretString};
use serde::{Deserialize, Deserializer, Serialize};
use url::Url;

const ENV_PREFIX: &str = "DZ_";

/// Errors raised while loading or validating configuration.
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("could not read secret file {path} (from {var}): {source}")]
    SecretFile { var: String, path: String, source: std::io::Error },
    #[error("invalid configuration: {0}")]
    Parse(Box<figment::Error>),
    #[error("invalid configuration:\n  - {}", .0.join("\n  - "))]
    Invalid(Vec<String>),
}

impl From<figment::Error> for ConfigError {
    fn from(e: figment::Error) -> Self {
        Self::Parse(Box::new(e))
    }
}

/// Deployment environment. Production enables the strictest validation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Environment {
    #[default]
    Development,
    Test,
    Production,
}

/// Root configuration.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Settings {
    pub env: Environment,
    pub http: HttpSettings,
    pub database: DatabaseSettings,
    pub valkey: ValkeySettings,
    pub auth: AuthSettings,
    pub rate_limit: RateLimitSettings,
    pub email: EmailSettings,
    pub telemetry: TelemetrySettings,
    pub worker: WorkerSettings,
    pub storage: StorageSettings,
}

/// HTTP server settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct HttpSettings {
    /// Address of the public API listener (plain HTTP/1.1 + h2c behind nginx).
    pub addr: SocketAddr,
    /// Address of the internal Prometheus listener; never exposed through nginx.
    pub metrics_addr: Option<SocketAddr>,
    /// Externally visible base URL (used in links and the OpenAPI `servers` list).
    pub public_base_url: Url,
    /// Exact origins allowed by CORS. Empty disables CORS.
    #[serde(deserialize_with = "de::string_list")]
    pub cors_allowed_origins: Vec<String>,
    /// Proxies whose `X-Forwarded-For` / `X-Real-IP` headers are trusted.
    #[serde(deserialize_with = "de::cidr_list")]
    pub trusted_proxies: Vec<IpNet>,
    pub request_timeout_secs: u64,
    pub body_limit_bytes: usize,
    /// Time allowed for in-flight requests to finish after SIGTERM.
    pub shutdown_grace_secs: u64,
    /// Serve the interactive API reference at `/api/docs`.
    pub docs_enabled: bool,
}

impl Default for HttpSettings {
    fn default() -> Self {
        Self {
            addr: SocketAddr::from(([0, 0, 0, 0], 8080)),
            metrics_addr: Some(SocketAddr::from(([0, 0, 0, 0], 9090))),
            public_base_url: Url::parse("http://localhost:8080").unwrap_or_else(|_| unreachable!()),
            cors_allowed_origins: Vec::new(),
            trusted_proxies: vec![loopback_v4(), loopback_v6()],
            request_timeout_secs: 15,
            body_limit_bytes: 1024 * 1024,
            shutdown_grace_secs: 25,
            docs_enabled: true,
        }
    }
}

fn loopback_v4() -> IpNet {
    IpNet::from(std::net::IpAddr::from([127, 0, 0, 1]))
}

fn loopback_v6() -> IpNet {
    IpNet::from(std::net::IpAddr::from(std::net::Ipv6Addr::LOCALHOST))
}

/// PostgreSQL settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct DatabaseSettings {
    #[serde(serialize_with = "ser::redacted")]
    pub url: SecretString,
    pub max_connections: u32,
    pub min_connections: u32,
    pub acquire_timeout_ms: u64,
    pub idle_timeout_secs: u64,
    pub max_lifetime_secs: u64,
    /// Server-side `statement_timeout` applied to every pooled connection.
    pub statement_timeout_ms: u64,
    /// Apply pending migrations when the API starts (handy in development; production runs
    /// `dz-cli migrate` as a one-shot job instead).
    pub migrate_on_start: bool,
}

impl Default for DatabaseSettings {
    fn default() -> Self {
        Self {
            url: SecretString::from("postgres://dzbus:dzbus@localhost:5432/dzbus"),
            max_connections: 32,
            min_connections: 2,
            acquire_timeout_ms: 3_000,
            idle_timeout_secs: 300,
            max_lifetime_secs: 1_800,
            statement_timeout_ms: 5_000,
            migrate_on_start: false,
        }
    }
}

/// Valkey (Redis-compatible) settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ValkeySettings {
    /// `redis://[:password@]host:port/db` or `rediss://` for TLS.
    #[serde(serialize_with = "ser::redacted")]
    pub url: SecretString,
    pub pool_size: usize,
    /// Prefix applied to every key, so several deployments can share an instance.
    pub key_prefix: String,
    pub command_timeout_ms: u64,
}

impl Default for ValkeySettings {
    fn default() -> Self {
        Self {
            url: SecretString::from("redis://localhost:6379/0"),
            pool_size: 8,
            key_prefix: "dz:".to_owned(),
            command_timeout_ms: 1_000,
        }
    }
}

/// Authentication settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct AuthSettings {
    pub issuer: String,
    pub audience: String,
    pub access_token_ttl_secs: u64,
    /// Sliding lifetime of a refresh token.
    pub refresh_token_ttl_secs: u64,
    /// Absolute lifetime of a session (refresh-token family), regardless of activity.
    pub session_max_lifetime_secs: u64,
    /// Directory containing Ed25519 private keys in PKCS#8 PEM, one file per key,
    /// named `<kid>.pem`. All keys verify; only `active_key_id` signs.
    pub signing_keys_dir: Option<PathBuf>,
    pub active_key_id: Option<String>,
    /// Development only: generate a throw-away signing key when no key directory is set.
    pub allow_ephemeral_keys: bool,
    pub password_min_length: usize,
    pub argon2_memory_kib: u32,
    pub argon2_iterations: u32,
    pub argon2_parallelism: u32,
    /// Maximum concurrent password hash computations (0 = number of CPUs).
    pub max_concurrent_hashes: usize,
    /// Consecutive failed logins before the account is temporarily locked.
    pub lockout_threshold: u32,
    /// First lock duration; doubles for each further failure (capped at 32×).
    pub lockout_base_secs: u64,
    pub password_reset_ttl_secs: u64,
    /// Front-end page that completes a password reset. The token is appended as a URL
    /// fragment (`#token=…`) so it never reaches server logs or `Referer` headers.
    pub password_reset_url: Url,
    /// Behaviour when the session-revocation store (Valkey) is unreachable:
    /// `false` rejects authenticated requests (secure default).
    pub revocation_fail_open: bool,
}

impl Default for AuthSettings {
    fn default() -> Self {
        Self {
            issuer: "dz-bus-tracker".to_owned(),
            audience: "dz-bus-api".to_owned(),
            access_token_ttl_secs: 900,
            refresh_token_ttl_secs: 14 * 24 * 3600,
            session_max_lifetime_secs: 60 * 24 * 3600,
            signing_keys_dir: None,
            active_key_id: None,
            allow_ephemeral_keys: false,
            password_min_length: 12,
            argon2_memory_kib: 19_456,
            argon2_iterations: 2,
            argon2_parallelism: 1,
            max_concurrent_hashes: 0,
            lockout_threshold: 5,
            lockout_base_secs: 60,
            password_reset_ttl_secs: 3_600,
            password_reset_url: Url::parse("http://localhost:3000/reset-password")
                .unwrap_or_else(|_| unreachable!()),
            revocation_fail_open: false,
        }
    }
}

/// Rate-limit tiers (requests per minute, GCRA with the given burst).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct RateLimitSettings {
    pub enabled: bool,
    /// Unauthenticated callers, per client IP.
    pub anon_per_minute: u32,
    /// Authenticated users, per user.
    pub user_per_minute: u32,
    /// Burst capacity for the anon/user tiers.
    pub burst: u32,
    /// Driver location publishing, per user.
    pub location_per_minute: u32,
    /// Credential endpoints (login, register, password reset), per client IP.
    pub auth_per_minute: u32,
    /// Machine-to-machine API keys, per key.
    pub service_per_minute: u32,
    /// When Valkey is unreachable: `true` lets requests through (and counts the failure).
    pub fail_open: bool,
}

impl Default for RateLimitSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            anon_per_minute: 30,
            user_per_minute: 60,
            burst: 60,
            location_per_minute: 100,
            auth_per_minute: 10,
            service_per_minute: 1_200,
            fail_open: true,
        }
    }
}

/// E-mail delivery.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EmailTransport {
    /// Log messages instead of sending them (development and tests).
    #[default]
    Log,
    Smtp,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct EmailSettings {
    pub transport: EmailTransport,
    /// `smtps://user:pass@host:465` (implicit TLS) or `smtp://user:pass@host:587?tls=required`.
    #[serde(serialize_with = "ser::redacted_opt")]
    pub smtp_url: Option<SecretString>,
    pub from: String,
    pub timeout_secs: u64,
}

impl Default for EmailSettings {
    fn default() -> Self {
        Self {
            transport: EmailTransport::Log,
            smtp_url: None,
            from: "DZ Bus Tracker <noreply@localhost>".to_owned(),
            timeout_secs: 10,
        }
    }
}

/// Log output format.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    #[default]
    Json,
    Pretty,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct TelemetrySettings {
    pub log_format: LogFormat,
    /// `tracing` filter directive, e.g. `info,dz_http=debug,sqlx=warn`.
    pub log_filter: String,
    /// OTLP/HTTP traces endpoint (e.g. `http://otel-collector:4318/v1/traces`); unset disables.
    pub otlp_endpoint: Option<Url>,
    /// Fraction of traces sampled when OTLP export is enabled.
    pub otlp_sample_ratio: f64,
    pub service_name: String,
}

impl Default for TelemetrySettings {
    fn default() -> Self {
        Self {
            log_format: LogFormat::Json,
            log_filter: "info,sqlx=warn,fred=warn".to_owned(),
            otlp_endpoint: None,
            otlp_sample_ratio: 0.1,
            service_name: "dz-bus-tracker".to_owned(),
        }
    }
}

/// Background worker settings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct WorkerSettings {
    /// Jobs executed concurrently by one worker process.
    pub concurrency: usize,
    /// Fallback polling interval when no `NOTIFY` wake-up arrives.
    pub poll_interval_ms: u64,
    /// A running job whose lease is older than this is considered abandoned and re-queued.
    pub lease_secs: u64,
    /// Hard timeout for a single job execution.
    pub job_timeout_secs: u64,
    /// Finished jobs are kept this long for inspection.
    pub retention_days: u32,
}

impl Default for WorkerSettings {
    fn default() -> Self {
        Self {
            concurrency: 4,
            poll_interval_ms: 2_000,
            lease_secs: 300,
            job_timeout_secs: 120,
            retention_days: 7,
        }
    }
}

/// Private S3-compatible object storage for photos and documents.
///
/// Optional: without `endpoint`, upload and attach endpoints answer `503 storage_unavailable`
/// and every `*_url` field is `null`. Production requires it with an `https` public endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct StorageSettings {
    /// S3 endpoint the API and the worker talk to (e.g. `http://rustfs:9000` on an internal
    /// network). Unset disables storage.
    pub endpoint: Option<Url>,
    /// Endpoint embedded in presigned URLs handed to clients (default: `endpoint`).
    pub public_endpoint: Option<Url>,
    pub region: String,
    pub bucket: String,
    pub access_key_id: String,
    #[serde(serialize_with = "ser::redacted_opt")]
    pub secret_access_key: Option<SecretString>,
    /// `https://endpoint/bucket/key` (true) or `https://bucket.endpoint/key` (false).
    pub path_style: bool,
    /// Validity of presigned upload URLs (60–3600 s).
    pub upload_ttl_secs: u64,
    /// Validity of presigned download URLs (300–43200 s); one hour is added so that a URL
    /// signed at the start of an hour stays stable (and valid) throughout that hour.
    pub download_ttl_secs: u64,
    /// Timeout of server-side requests (`HEAD`, `DELETE`).
    pub request_timeout_ms: u64,
}

impl Default for StorageSettings {
    fn default() -> Self {
        Self {
            endpoint: None,
            public_endpoint: None,
            region: "us-east-1".to_owned(),
            bucket: String::new(),
            access_key_id: String::new(),
            secret_access_key: None,
            path_style: true,
            upload_ttl_secs: 900,
            download_ttl_secs: 3_600,
            request_timeout_ms: 5_000,
        }
    }
}

impl StorageSettings {
    /// Whether object storage is configured.
    #[must_use]
    pub fn enabled(&self) -> bool {
        self.endpoint.is_some()
    }

    /// The endpoint used in presigned URLs for clients.
    #[must_use]
    pub fn effective_public_endpoint(&self) -> Option<&Url> {
        self.public_endpoint.as_ref().or(self.endpoint.as_ref())
    }

    fn validate(&self, prod: bool, errors: &mut Vec<String>) {
        if !(60..=3_600).contains(&self.upload_ttl_secs) {
            errors.push("storage.upload_ttl_secs must be between 60 and 3600".to_owned());
        }
        if !(300..=43_200).contains(&self.download_ttl_secs) {
            errors.push("storage.download_ttl_secs must be between 300 and 43200".to_owned());
        }
        if !(100..=60_000).contains(&self.request_timeout_ms) {
            errors.push("storage.request_timeout_ms must be between 100 and 60000".to_owned());
        }
        let Some(endpoint) = &self.endpoint else {
            if self.public_endpoint.is_some() {
                errors.push("storage.public_endpoint requires storage.endpoint".to_owned());
            }
            if prod {
                errors.push("storage.endpoint is required in production".to_owned());
            }
            return;
        };
        let public = self.public_endpoint.as_ref().map(|url| ("public_endpoint", url));
        for (name, url) in std::iter::once(("endpoint", endpoint)).chain(public) {
            let plain = url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none();
            if !matches!(url.scheme(), "http" | "https") || url.host().is_none() || !plain {
                errors.push(format!(
                    "storage.{name} must be an http(s) URL without credentials, query or fragment"
                ));
            }
        }
        if !valid_bucket_name(&self.bucket) {
            errors.push(
                "storage.bucket must be 3-63 characters of [a-z0-9.-], starting and ending with \
                 a letter or digit"
                    .to_owned(),
            );
        }
        if self.region.trim().is_empty() {
            errors.push("storage.region must not be empty".to_owned());
        }
        if self.access_key_id.trim().is_empty() {
            errors.push(
                "storage.access_key_id is required when storage.endpoint is set".to_owned(),
            );
        }
        if self.secret_access_key.as_ref().is_none_or(|k| k.expose_secret().is_empty()) {
            errors.push(
                "storage.secret_access_key is required when storage.endpoint is set".to_owned(),
            );
        }
        if prod && self.effective_public_endpoint().is_some_and(|u| u.scheme() != "https") {
            errors.push("storage.public_endpoint must use https in production".to_owned());
        }
    }
}

/// S3 bucket naming rules (the subset every provider accepts).
fn valid_bucket_name(name: &str) -> bool {
    let bytes = name.as_bytes();
    (3..=63).contains(&bytes.len())
        && bytes.iter().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"-.".contains(b))
        && bytes.first().is_some_and(u8::is_ascii_alphanumeric)
        && bytes.last().is_some_and(u8::is_ascii_alphanumeric)
        && !name.contains("..")
}

impl Settings {
    /// Loads settings from the process environment and validates them.
    pub fn load() -> Result<Self, ConfigError> {
        let vars: Vec<(String, String)> = std::env::vars().collect();
        Self::from_vars(vars)
    }

    /// Loads settings from an explicit list of variables (used by tests).
    pub fn from_vars<I>(vars: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (String, String)>,
    {
        let mut plain = BTreeMap::new();
        for (key, value) in vars {
            let Some(rest) = key.strip_prefix(ENV_PREFIX) else { continue };
            if let Some(base) = rest.strip_suffix("_FILE") {
                let contents = std::fs::read_to_string(&value).map_err(|source| {
                    ConfigError::SecretFile { var: key.clone(), path: value.clone(), source }
                })?;
                // A file wins over a plain variable of the same name.
                plain.insert(base.to_owned(), contents.trim_end_matches(['\r', '\n']).to_owned());
            } else {
                plain.entry(rest.to_owned()).or_insert(value);
            }
        }

        // Defaults come from the `#[serde(default)]` impls; only overrides are merged here so
        // that redacting serializers never leak into the loaded values.
        let mut figment = Figment::new();
        for (key, value) in plain {
            let path = key.to_lowercase().replace("__", ".");
            figment = figment.merge((path, parse_value(&value)));
        }
        let settings: Self = figment.extract()?;
        settings.validate()?;
        Ok(settings)
    }

    /// Cross-field validation. In production the checks are strict.
    pub fn validate(&self) -> Result<(), ConfigError> {
        let mut errors = Vec::new();
        let prod = self.env == Environment::Production;
        let a = &self.auth;

        if !(60..=3_600).contains(&a.access_token_ttl_secs) {
            errors.push("auth.access_token_ttl_secs must be between 60 and 3600".to_owned());
        }
        if a.refresh_token_ttl_secs <= a.access_token_ttl_secs {
            errors.push("auth.refresh_token_ttl_secs must exceed access_token_ttl_secs".to_owned());
        }
        if a.session_max_lifetime_secs < a.refresh_token_ttl_secs {
            errors.push(
                "auth.session_max_lifetime_secs must be >= refresh_token_ttl_secs".to_owned(),
            );
        }
        if a.password_min_length < 8 || a.password_min_length > 64 {
            errors.push("auth.password_min_length must be between 8 and 64".to_owned());
        }
        if a.argon2_iterations == 0 || a.argon2_parallelism == 0 {
            errors.push("auth.argon2_iterations and argon2_parallelism must be >= 1".to_owned());
        }
        if a.lockout_threshold == 0 {
            errors.push("auth.lockout_threshold must be >= 1".to_owned());
        }
        if a.signing_keys_dir.is_some() != a.active_key_id.is_some() {
            errors.push(
                "auth.signing_keys_dir and auth.active_key_id must be set together".to_owned(),
            );
        }
        if a.signing_keys_dir.is_none() && !a.allow_ephemeral_keys {
            errors.push(
                "auth.signing_keys_dir is required (or set auth.allow_ephemeral_keys=true in \
                 development)"
                    .to_owned(),
            );
        }
        if self.database.min_connections > self.database.max_connections {
            errors.push("database.min_connections must be <= max_connections".to_owned());
        }
        if self.database.max_connections == 0 {
            errors.push("database.max_connections must be >= 1".to_owned());
        }
        if !self.database.url.expose_secret().starts_with("postgres") {
            errors.push("database.url must be a postgres:// URL".to_owned());
        }
        let valkey_url = self.valkey.url.expose_secret();
        if !(valkey_url.starts_with("redis://") || valkey_url.starts_with("rediss://")) {
            errors.push("valkey.url must be a redis:// or rediss:// URL".to_owned());
        }
        if self.valkey.pool_size == 0 {
            errors.push("valkey.pool_size must be >= 1".to_owned());
        }
        for origin in &self.http.cors_allowed_origins {
            match Url::parse(origin) {
                Ok(url) if url.origin().ascii_serialization() == *origin => {
                    if prod && url.scheme() != "https" {
                        errors.push(format!("http.cors_allowed_origins: {origin} must use https"));
                    }
                }
                _ => errors.push(format!(
                    "http.cors_allowed_origins: {origin} is not a bare origin (scheme://host[:port])"
                )),
            }
        }
        if self.http.body_limit_bytes < 1024 {
            errors.push("http.body_limit_bytes must be >= 1024".to_owned());
        }
        if self.http.request_timeout_secs == 0 {
            errors.push("http.request_timeout_secs must be >= 1".to_owned());
        }
        if self.email.transport == EmailTransport::Smtp && self.email.smtp_url.is_none() {
            errors.push("email.smtp_url is required when email.transport=smtp".to_owned());
        }
        if !(0.0..=1.0).contains(&self.telemetry.otlp_sample_ratio) {
            errors.push("telemetry.otlp_sample_ratio must be within [0, 1]".to_owned());
        }
        if self.worker.concurrency == 0 {
            errors.push("worker.concurrency must be >= 1".to_owned());
        }
        self.storage.validate(prod, &mut errors);

        if prod {
            if a.allow_ephemeral_keys {
                errors.push("auth.allow_ephemeral_keys is forbidden in production".to_owned());
            }
            if a.argon2_memory_kib < 19_456 {
                errors.push("auth.argon2_memory_kib must be >= 19456 in production".to_owned());
            }
            if self.http.public_base_url.scheme() != "https" {
                errors.push("http.public_base_url must use https in production".to_owned());
            }
            if a.password_reset_url.scheme() != "https" {
                errors.push("auth.password_reset_url must use https in production".to_owned());
            }
            if self.email.transport == EmailTransport::Log {
                errors.push("email.transport=log is not allowed in production".to_owned());
            }
            if self.database.url.expose_secret().contains("dzbus:dzbus@") {
                errors.push("database.url still uses the development credentials".to_owned());
            }
        }

        if errors.is_empty() { Ok(()) } else { Err(ConfigError::Invalid(errors)) }
    }
}

/// Parses a raw environment string the way operators expect: booleans, integers, floats and
/// `[a, b]` arrays are typed; everything else stays a string.
fn parse_value(raw: &str) -> figment::value::Value {
    use figment::value::Value;
    let trimmed = raw.trim();
    if trimmed.starts_with('[') && trimmed.ends_with(']') {
        let inner = &trimmed[1..trimmed.len() - 1];
        let items = inner
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(|s| Value::from(s.trim_matches('"').to_owned()))
            .collect::<Vec<_>>();
        return Value::from(items);
    }
    match trimmed {
        "true" => return Value::from(true),
        "false" => return Value::from(false),
        _ => {}
    }
    if let Ok(i) = trimmed.parse::<i64>() {
        return Value::from(i);
    }
    if trimmed.contains('.')
        && let Ok(f) = trimmed.parse::<f64>()
        && !trimmed.contains(':')
    {
        return Value::from(f);
    }
    Value::from(raw.to_owned())
}

mod de {
    use super::{Deserialize, Deserializer, IpNet};

    #[derive(Deserialize)]
    #[serde(untagged)]
    enum ListOrString {
        List(Vec<String>),
        String(String),
    }

    /// Accepts `a,b,c` or a list.
    pub fn string_list<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<String>, D::Error> {
        Ok(match ListOrString::deserialize(d)? {
            ListOrString::List(items) => items,
            ListOrString::String(s) => {
                s.split(',').map(str::trim).filter(|s| !s.is_empty()).map(str::to_owned).collect()
            }
        })
    }

    /// Accepts CIDRs or bare IPs, comma separated or as a list.
    pub fn cidr_list<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<IpNet>, D::Error> {
        string_list(d)?
            .into_iter()
            .map(|s| {
                s.parse::<IpNet>()
                    .or_else(|_| s.parse::<std::net::IpAddr>().map(IpNet::from))
                    .map_err(|_| serde::de::Error::custom(format!("invalid CIDR or IP `{s}`")))
            })
            .collect()
    }
}

mod ser {
    use secrecy::SecretString;
    use serde::Serializer;

    pub fn redacted<S: Serializer>(_: &SecretString, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str("[redacted]")
    }

    pub fn redacted_opt<S: Serializer>(v: &Option<SecretString>, s: S) -> Result<S::Ok, S::Error> {
        match v {
            Some(_) => s.serialize_some("[redacted]"),
            None => s.serialize_none(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vars(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
        let mut v: Vec<(String, String)> =
            vec![("DZ_AUTH__ALLOW_EPHEMERAL_KEYS".into(), "true".into())];
        v.extend(pairs.iter().map(|(k, val)| ((*k).to_owned(), (*val).to_owned())));
        v
    }

    #[test]
    fn defaults_are_valid_for_development() {
        let s = Settings::from_vars(vars(&[])).unwrap();
        assert_eq!(s.env, Environment::Development);
        assert_eq!(s.rate_limit.anon_per_minute, 30);
        assert_eq!(s.auth.access_token_ttl_secs, 900);
    }

    #[test]
    fn nested_keys_lists_and_types_are_parsed() {
        let s = Settings::from_vars(vars(&[
            ("DZ_HTTP__ADDR", "127.0.0.1:9000"),
            ("DZ_HTTP__CORS_ALLOWED_ORIGINS", "https://a.example, https://b.example"),
            ("DZ_HTTP__TRUSTED_PROXIES", "10.0.0.0/8,192.168.1.10"),
            ("DZ_RATE_LIMIT__ENABLED", "false"),
            ("DZ_DATABASE__MAX_CONNECTIONS", "64"),
            ("DZ_TELEMETRY__OTLP_SAMPLE_RATIO", "0.25"),
            ("UNRELATED", "ignored"),
        ]))
        .unwrap();
        assert_eq!(s.http.addr.port(), 9000);
        assert_eq!(s.http.cors_allowed_origins.len(), 2);
        assert_eq!(s.http.trusted_proxies.len(), 2);
        assert!(!s.rate_limit.enabled);
        assert_eq!(s.database.max_connections, 64);
        assert!((s.telemetry.otlp_sample_ratio - 0.25).abs() < f64::EPSILON);
    }

    #[test]
    fn unknown_keys_fail_fast() {
        let err = Settings::from_vars(vars(&[("DZ_HTTP__ADRR", "x")])).unwrap_err();
        assert!(err.to_string().contains("adrr"), "{err}");
    }

    #[test]
    fn secret_files_are_read() {
        let dir = std::env::temp_dir().join(format!("dz-config-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("db_url");
        std::fs::write(&file, "postgres://u:secret@db:5432/app\n").unwrap();
        let s = Settings::from_vars(vars(&[(
            "DZ_DATABASE__URL_FILE",
            file.to_str().unwrap(),
        )]))
        .unwrap();
        assert_eq!(s.database.url.expose_secret(), "postgres://u:secret@db:5432/app");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn secrets_are_redacted_when_serialized() {
        let s = Settings::from_vars(vars(&[])).unwrap();
        let dump = serde_json::to_string(&s).unwrap();
        assert!(!dump.contains("dzbus:dzbus"), "{dump}");
        assert!(dump.contains("[redacted]"));
    }

    #[test]
    fn production_is_strict() {
        let err = Settings::from_vars(vec![("DZ_ENV".to_owned(), "production".to_owned())])
            .unwrap_err()
            .to_string();
        let needles =
            ["signing_keys_dir", "https", "email.transport", "development credentials", "storage"];
        for needle in needles {
            assert!(err.contains(needle), "missing `{needle}` in: {err}");
        }
    }

    #[test]
    fn bad_origins_and_ranges_are_reported_together() {
        let err = Settings::from_vars(vars(&[
            ("DZ_HTTP__CORS_ALLOWED_ORIGINS", "https://a.example/path"),
            ("DZ_AUTH__ACCESS_TOKEN_TTL_SECS", "10"),
        ]))
        .unwrap_err()
        .to_string();
        assert!(err.contains("bare origin") && err.contains("access_token_ttl_secs"), "{err}");
    }
    /// A complete storage section; `overrides` win (the first occurrence of a variable is used).
    fn storage_vars(overrides: &[(&str, &str)]) -> Vec<(String, String)> {
        let mut pairs = overrides.to_vec();
        pairs.extend_from_slice(&[
            ("DZ_STORAGE__ENDPOINT", "http://rustfs:9000"),
            ("DZ_STORAGE__BUCKET", "dz-media"),
            ("DZ_STORAGE__ACCESS_KEY_ID", "dz-api"),
            ("DZ_STORAGE__SECRET_ACCESS_KEY", "s3-secret-value"),
        ]);
        vars(&pairs)
    }

    #[test]
    fn storage_is_optional_and_has_defaults() {
        let s = Settings::from_vars(vars(&[])).unwrap();
        assert!(!s.storage.enabled());
        assert_eq!(s.storage.region, "us-east-1");
        assert!(s.storage.path_style);
        assert_eq!((s.storage.upload_ttl_secs, s.storage.download_ttl_secs), (900, 3_600));
        assert_eq!(s.storage.request_timeout_ms, 5_000);
    }

    #[test]
    fn storage_settings_are_parsed() {
        let s = Settings::from_vars(storage_vars(&[
            ("DZ_STORAGE__PUBLIC_ENDPOINT", "https://media.dzbus.example"),
            ("DZ_STORAGE__PATH_STYLE", "false"),
            ("DZ_STORAGE__UPLOAD_TTL_SECS", "600"),
        ]))
        .unwrap();
        assert!(s.storage.enabled());
        assert_eq!(s.storage.endpoint.as_ref().unwrap().as_str(), "http://rustfs:9000/");
        assert_eq!(
            s.storage.effective_public_endpoint().unwrap().as_str(),
            "https://media.dzbus.example/"
        );
        assert!(!s.storage.path_style);
        assert_eq!(s.storage.upload_ttl_secs, 600);
        let secret = s.storage.secret_access_key.as_ref().unwrap();
        assert_eq!(secret.expose_secret(), "s3-secret-value");

        // Without a public endpoint, clients get URLs on the internal endpoint.
        let s = Settings::from_vars(storage_vars(&[])).unwrap();
        assert_eq!(s.storage.effective_public_endpoint(), s.storage.endpoint.as_ref());
    }

    #[test]
    fn storage_secret_is_redacted_and_readable_from_a_file() {
        let dir = std::env::temp_dir().join(format!("dz-config-s3-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("s3_secret_key");
        std::fs::write(&file, "from-a-file\n").unwrap();
        let mut pairs = storage_vars(&[]);
        pairs.retain(|(k, _)| k != "DZ_STORAGE__SECRET_ACCESS_KEY");
        pairs.push(("DZ_STORAGE__SECRET_ACCESS_KEY_FILE".into(), file.to_str().unwrap().into()));
        let s = Settings::from_vars(pairs).unwrap();
        assert_eq!(s.storage.secret_access_key.as_ref().unwrap().expose_secret(), "from-a-file");
        let dump = serde_json::to_string(&s).unwrap();
        assert!(!dump.contains("from-a-file"), "{dump}");
        assert!(dump.contains(r#""secret_access_key":"[redacted]""#), "{dump}");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn enabled_storage_needs_a_bucket_and_credentials() {
        let err = Settings::from_vars(vars(&[("DZ_STORAGE__ENDPOINT", "http://rustfs:9000")]))
            .unwrap_err()
            .to_string();
        for needle in ["storage.bucket", "storage.access_key_id", "storage.secret_access_key"] {
            assert!(err.contains(needle), "missing `{needle}` in: {err}");
        }
        for bucket in ["ab", "Upper", "-dash", "dot.", "a..b", "under_score"] {
            let err = Settings::from_vars(storage_vars(&[("DZ_STORAGE__BUCKET", bucket)]))
                .unwrap_err()
                .to_string();
            assert!(err.contains("storage.bucket"), "{bucket}: {err}");
        }
    }

    #[test]
    fn storage_urls_and_ranges_are_validated() {
        let err = Settings::from_vars(storage_vars(&[
            ("DZ_STORAGE__ENDPOINT", "ftp://rustfs:9000"),
            ("DZ_STORAGE__PUBLIC_ENDPOINT", "https://user:pass@media.example"),
            ("DZ_STORAGE__UPLOAD_TTL_SECS", "59"),
            ("DZ_STORAGE__DOWNLOAD_TTL_SECS", "43201"),
            ("DZ_STORAGE__REQUEST_TIMEOUT_MS", "0"),
        ]))
        .unwrap_err()
        .to_string();
        for needle in [
            "storage.endpoint must be an http(s) URL",
            "storage.public_endpoint must be an http(s) URL",
            "upload_ttl_secs",
            "download_ttl_secs",
            "request_timeout_ms",
        ] {
            assert!(err.contains(needle), "missing `{needle}` in: {err}");
        }
        let public_only = vars(&[("DZ_STORAGE__PUBLIC_ENDPOINT", "https://m.example")]);
        let err = Settings::from_vars(public_only).unwrap_err().to_string();
        assert!(err.contains("requires storage.endpoint"), "{err}");
        let err = Settings::from_vars(storage_vars(&[("DZ_STORAGE__RGION", "eu")])).unwrap_err();
        assert!(err.to_string().contains("rgion"), "{err}");
    }

    #[test]
    fn production_requires_https_storage() {
        let production = |extra: &[(&str, &str)]| {
            let mut pairs = storage_vars(extra);
            pairs.push(("DZ_ENV".into(), "production".into()));
            Settings::from_vars(pairs).unwrap_err().to_string()
        };
        let err = production(&[]);
        assert!(err.contains("storage.public_endpoint must use https"), "{err}");
        assert!(!err.contains("storage.endpoint is required"), "{err}");
        // An internal plain-HTTP endpoint is fine when clients get an https one.
        let err = production(&[("DZ_STORAGE__PUBLIC_ENDPOINT", "https://media.dzbus.example")]);
        assert!(!err.contains("storage."), "{err}");
    }
}
