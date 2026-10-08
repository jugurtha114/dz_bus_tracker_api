//! S3-compatible object storage (RustFS, MinIO-compatible servers, AWS S3, …).
//!
//! * Presigning is pure computation with `rusty-s3` (AWS Signature V4, query-string auth).
//!   URLs handed to clients use the *public* endpoint; the API and the worker reach storage
//!   through the *internal* endpoint (they differ when storage sits on a private network).
//! * Server-side `HEAD`/`DELETE` are presigned with the same credentials and sent with
//!   `reqwest` over rustls (ring provider, platform certificate verifier).
//! * Every remote failure is logged and reported as `AppError::Unavailable("storage")`.

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, DurationRound, TimeDelta, Utc};
use dz_app::jobs::chrono_duration;
use dz_app::ports::{Clock, ObjectInfo, ObjectStorage, PresignedUpload};
use dz_app::{AppError, AppResult};
use dz_config::StorageSettings;
use reqwest::StatusCode;
use reqwest::header::{CONTENT_LENGTH, CONTENT_TYPE};
use rusty_s3::actions::{
    CreateBucket, DeleteBucket, DeleteObject, GetObject, HeadBucket, HeadObject, PutObject,
    S3Action,
};
use rusty_s3::{Bucket, Credentials, UrlStyle};
use secrecy::ExposeSecret;
use url::Url;

/// Validity of the presigned requests the server sends itself.
const SERVER_REQUEST_TTL: Duration = Duration::from_secs(60);
/// Download URLs stay identical for a whole hour (see [`ObjectStorage::presign_get`]).
const DOWNLOAD_URL_WINDOW: Duration = Duration::from_secs(3600);

/// The S3 adapter.
pub struct S3Storage {
    /// Bucket addressed through the internal endpoint (server-side requests).
    internal: Bucket,
    /// Bucket addressed through the public endpoint (presigned URLs for clients).
    public: Bucket,
    credentials: Credentials,
    http: reqwest::Client,
    clock: Arc<dyn Clock>,
    download_ttl: Duration,
}

impl std::fmt::Debug for S3Storage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("S3Storage")
            .field("endpoint", &self.internal.base_url().as_str())
            .field("public_endpoint", &self.public.base_url().as_str())
            .finish_non_exhaustive()
    }
}

impl S3Storage {
    /// Builds the adapter from enabled settings (`storage.endpoint` set).
    pub fn new(settings: &StorageSettings, clock: Arc<dyn Clock>) -> anyhow::Result<Self> {
        let endpoint =
            settings.endpoint.clone().ok_or_else(|| anyhow::anyhow!("storage is not configured"))?;
        let public = settings.public_endpoint.clone().unwrap_or_else(|| endpoint.clone());
        let style = if settings.path_style { UrlStyle::Path } else { UrlStyle::VirtualHost };
        let bucket = |endpoint: Url| {
            Bucket::new(
                with_trailing_slash(endpoint),
                style,
                settings.bucket.clone(),
                settings.region.clone(),
            )
            .map_err(|e| anyhow::anyhow!("invalid storage endpoint: {e:?}"))
        };
        let secret = settings
            .secret_access_key
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("storage.secret_access_key is not set"))?;
        Ok(Self {
            internal: bucket(endpoint)?,
            public: bucket(public)?,
            credentials: Credentials::new(
                settings.access_key_id.clone(),
                secret.expose_secret().to_owned(),
            ),
            http: http_client(Duration::from_millis(settings.request_timeout_ms))?,
            clock,
            download_ttl: Duration::from_secs(settings.download_ttl_secs),
        })
    }

    /// Creates the bucket. Returns `false` when it already exists and belongs to these
    /// credentials (idempotent provisioning, e.g. `dz-cli storage create-bucket`).
    pub async fn create_bucket(&self) -> anyhow::Result<bool> {
        // Some servers answer 200 to re-creating one's own bucket: ask first.
        let url = HeadBucket::new(&self.internal, Some(&self.credentials))
            .sign_with_time(SERVER_REQUEST_TTL, &self.signing_time(self.clock.now()));
        let head = self.http.head(url).send().await.map_err(reqwest::Error::without_url)?;
        if head.status().is_success() {
            return Ok(false);
        }
        let url = CreateBucket::new(&self.internal, &self.credentials)
            .sign_with_time(SERVER_REQUEST_TTL, &self.signing_time(self.clock.now()));
        let response = self.http.put(url).send().await.map_err(reqwest::Error::without_url)?;
        let status = response.status();
        if status.is_success() {
            return Ok(true);
        }
        let body = response.text().await.unwrap_or_default();
        if status == StatusCode::CONFLICT && body.contains("BucketAlreadyOwnedByYou") {
            return Ok(false);
        }
        anyhow::bail!("could not create bucket {}: {status} {body}", self.internal.name())
    }

    /// Deletes the (empty) bucket; used by the test kit to clean up after itself.
    pub async fn delete_bucket(&self) -> anyhow::Result<()> {
        let url = DeleteBucket::new(&self.internal, &self.credentials)
            .sign_with_time(SERVER_REQUEST_TTL, &self.signing_time(self.clock.now()));
        let response = self.http.delete(url).send().await.map_err(reqwest::Error::without_url)?;
        let status = response.status();
        anyhow::ensure!(
            status.is_success() || status == StatusCode::NOT_FOUND,
            "could not delete bucket {}: {status} {}",
            self.internal.name(),
            response.text().await.unwrap_or_default()
        );
        Ok(())
    }

    fn signing_time(&self, at: DateTime<Utc>) -> jiff::Timestamp {
        jiff::Timestamp::from_second(at.timestamp()).unwrap_or_else(|_| jiff::Timestamp::now())
    }

    async fn send(
        &self,
        request: reqwest::RequestBuilder,
        op: &'static str,
    ) -> AppResult<reqwest::Response> {
        request.send().await.map_err(|error| {
            // The URL is presigned (signature and access key id): never log it.
            let error = error.without_url();
            tracing::error!(%error, op, "object storage unreachable");
            AppError::Unavailable("storage")
        })
    }
}

/// `Url::join` replaces the last path segment unless the base ends with a slash, which would
/// drop a path prefix such as `https://gateway.example/s3`.
fn with_trailing_slash(mut url: Url) -> Url {
    if !url.path().ends_with('/') {
        let path = format!("{}/", url.path());
        url.set_path(&path);
    }
    url
}

/// HTTP client for server-side requests: rustls with the ring provider and the operating
/// system's trust store (so a private CA installed on the host is honoured), no redirects.
/// Also used by the test kit to act as a client of presigned URLs.
pub fn http_client(timeout: Duration) -> anyhow::Result<reqwest::Client> {
    use rustls_platform_verifier::BuilderVerifierExt;

    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()?
        .with_platform_verifier()?
        .with_no_client_auth();
    Ok(reqwest::Client::builder()
        .tls_backend_preconfigured(tls)
        .connect_timeout(timeout)
        .timeout(timeout)
        .redirect(reqwest::redirect::Policy::none())
        .build()?)
}

fn unexpected(op: &'static str, status: StatusCode) -> AppError {
    tracing::error!(op, %status, "unexpected object storage response");
    AppError::Unavailable("storage")
}

#[async_trait]
impl ObjectStorage for S3Storage {
    fn presign_put(
        &self,
        key: &str,
        content_type: &str,
        size_bytes: u64,
        expires_in: Duration,
    ) -> PresignedUpload {
        // Second precision, as in the signature (`X-Amz-Date`).
        let now = self.clock.now();
        let signed_at = now.duration_trunc(TimeDelta::seconds(1)).unwrap_or(now);
        let length = size_bytes.to_string();
        let mut action = PutObject::new(&self.public, Some(&self.credentials), key);
        action.headers_mut().insert("content-type", content_type);
        action.headers_mut().insert("content-length", length.as_str());
        let url = action.sign_with_time(expires_in, &self.signing_time(signed_at));
        PresignedUpload {
            url: url.into(),
            method: "PUT",
            headers: vec![("content-type", content_type.to_owned()), ("content-length", length)],
            expires_at: signed_at + chrono_duration(expires_in),
        }
    }

    fn presign_get(&self, key: &str) -> String {
        let now = self.clock.now();
        let hour = now.duration_trunc(TimeDelta::hours(1)).unwrap_or(now);
        GetObject::new(&self.public, Some(&self.credentials), key)
            .sign_with_time(self.download_ttl + DOWNLOAD_URL_WINDOW, &self.signing_time(hour))
            .into()
    }

    async fn head(&self, key: &str) -> AppResult<Option<ObjectInfo>> {
        let url = HeadObject::new(&self.internal, Some(&self.credentials), key)
            .sign_with_time(SERVER_REQUEST_TTL, &self.signing_time(self.clock.now()));
        let response = self.send(self.http.head(url), "head").await?;
        match response.status() {
            StatusCode::NOT_FOUND => Ok(None),
            status if status.is_success() => {
                let header = |name| response.headers().get(name).and_then(|v| v.to_str().ok());
                let size_bytes = header(CONTENT_LENGTH)
                    .and_then(|v| v.parse().ok())
                    .ok_or_else(|| unexpected("head", status))?;
                let content_type = header(CONTENT_TYPE).map(str::to_owned);
                Ok(Some(ObjectInfo { size_bytes, content_type }))
            }
            status => Err(unexpected("head", status)),
        }
    }

    async fn delete(&self, key: &str) -> AppResult<()> {
        let url = DeleteObject::new(&self.internal, Some(&self.credentials), key)
            .sign_with_time(SERVER_REQUEST_TTL, &self.signing_time(self.clock.now()));
        let response = self.send(self.http.delete(url), "delete").await?;
        match response.status() {
            // S3 answers 204 for missing objects too; some servers say 404.
            status if status.is_success() || status == StatusCode::NOT_FOUND => Ok(()),
            status => Err(unexpected("delete", status)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dz_app::testing::ManualClock;

    fn storage(public: Option<&str>) -> (S3Storage, Arc<ManualClock>) {
        let start = DateTime::parse_from_rfc3339("2026-10-01T08:20:31.250Z").unwrap().to_utc();
        let clock = Arc::new(ManualClock::new(start));
        let settings = StorageSettings {
            endpoint: Some("http://rustfs:9000".parse().unwrap()),
            public_endpoint: public.map(|p| p.parse().unwrap()),
            bucket: "dz-media".into(),
            access_key_id: "AKIDEXAMPLE".into(),
            secret_access_key: Some("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY".to_owned().into()),
            ..StorageSettings::default()
        };
        (S3Storage::new(&settings, clock.clone()).unwrap(), clock)
    }

    fn query(url: &str) -> Vec<(String, String)> {
        Url::parse(url).unwrap().query_pairs().into_owned().collect()
    }

    fn param(url: &str, name: &str) -> String {
        query(url).into_iter().find(|(k, _)| k == name).map(|(_, v)| v).unwrap()
    }

    #[test]
    fn uploads_are_presigned_on_the_public_endpoint_with_signed_type_and_length() {
        let (s3, _) = storage(Some("https://media.dzbus.example"));
        let presigned = s3.presign_put("avatar/u/1", "image/png", 2048, Duration::from_secs(900));
        assert!(presigned.url.starts_with("https://media.dzbus.example/dz-media/avatar/u/1?"));
        let signed = param(&presigned.url, "X-Amz-SignedHeaders");
        assert_eq!(signed, "content-length;content-type;host");
        assert_eq!(param(&presigned.url, "X-Amz-Expires"), "900");
        assert_eq!(param(&presigned.url, "X-Amz-Date"), "20261001T082031Z");
        assert_eq!(presigned.method, "PUT");
        assert_eq!(
            presigned.headers,
            vec![("content-type", "image/png".to_owned()), ("content-length", "2048".to_owned())]
        );
        let expected = DateTime::parse_from_rfc3339("2026-10-01T08:35:31Z").unwrap().to_utc();
        assert_eq!(presigned.expires_at, expected);
    }

    #[test]
    fn download_urls_are_stable_for_an_hour() {
        let (s3, clock) = storage(None);
        let url = s3.presign_get("avatar/u/1");
        assert!(url.starts_with("http://rustfs:9000/dz-media/avatar/u/1?"), "{url}");
        assert_eq!(param(&url, "X-Amz-Date"), "20261001T080000Z");
        assert_eq!(param(&url, "X-Amz-Expires"), "7200");
        clock.advance(Duration::from_secs(39 * 60));
        assert_eq!(s3.presign_get("avatar/u/1"), url);
        clock.advance(Duration::from_secs(60));
        assert_ne!(s3.presign_get("avatar/u/1"), url);
    }

    #[test]
    fn endpoint_paths_are_kept() {
        let url = with_trailing_slash("https://gw.example/s3".parse().unwrap());
        assert_eq!(url.as_str(), "https://gw.example/s3/");
        let (s3, _) = storage(Some("https://gw.example/s3"));
        assert!(s3.presign_get("k").starts_with("https://gw.example/s3/dz-media/k?"));
    }

    #[test]
    fn disabled_storage_cannot_be_built() {
        let clock = Arc::new(ManualClock::new(Utc::now()));
        assert!(S3Storage::new(&StorageSettings::default(), clock).is_err());
    }
}
