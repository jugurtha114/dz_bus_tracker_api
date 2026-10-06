//! Password hashing: Argon2id for new hashes, plus verification of the hash formats produced by
//! the legacy Django service so that imported accounts keep working and are upgraded on their
//! next successful login.
//!
//! Hashing is CPU and memory heavy, so it runs on the blocking thread pool and a semaphore caps
//! the number of concurrent computations (a burst of logins cannot starve the runtime or exhaust
//! memory: each Argon2 run allocates `m_cost` KiB).

use std::sync::Arc;

use argon2::password_hash::phc::PasswordHash;
use argon2::password_hash::{PasswordHasher as _, PasswordVerifier as _};
use argon2::{Algorithm, Argon2, Params, Version};
use async_trait::async_trait;
use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use dz_app::ports::{PasswordCheck, PasswordHasher};
use dz_app::{AppError, AppResult};
use secrecy::{ExposeSecret, SecretString};
use subtle::ConstantTimeEq;
use tokio::sync::Semaphore;

/// Upper bound accepted for legacy PBKDF2 iteration counts (protects against a tampered row).
const MAX_PBKDF2_ITERATIONS: u32 = 10_000_000;

/// Argon2 cost parameters.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Argon2Config {
    pub memory_kib: u32,
    pub iterations: u32,
    pub parallelism: u32,
}

/// Argon2id hasher with legacy Django verification.
#[derive(Clone)]
pub struct Argon2Hasher {
    params: Params,
    permits: Arc<Semaphore>,
    /// Hash of a random password with the current parameters, used to burn equal time when the
    /// account does not exist.
    dummy_hash: Arc<String>,
}

impl std::fmt::Debug for Argon2Hasher {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Argon2Hasher").field("params", &self.params).finish_non_exhaustive()
    }
}

impl Argon2Hasher {
    /// Builds the hasher; `max_concurrent = 0` means "number of CPUs".
    pub fn new(config: Argon2Config, max_concurrent: usize) -> anyhow::Result<Self> {
        let params = Params::new(config.memory_kib, config.iterations, config.parallelism, None)
            .map_err(|e| anyhow::anyhow!("invalid argon2 parameters: {e}"))?;
        let permits = if max_concurrent == 0 {
            std::thread::available_parallelism().map_or(2, std::num::NonZero::get)
        } else {
            max_concurrent
        };
        let dummy = format!("dummy-{}", uuid::Uuid::new_v4());
        let dummy_hash = hash_blocking(&params, dummy.as_bytes())?;
        Ok(Self { params, permits: Arc::new(Semaphore::new(permits)), dummy_hash: Arc::new(dummy_hash) })
    }

    async fn on_blocking_pool<T, F>(&self, f: F) -> AppResult<T>
    where
        F: FnOnce() -> T + Send + 'static,
        T: Send + 'static,
    {
        let _permit = self.permits.acquire().await.map_err(AppError::internal)?;
        tokio::task::spawn_blocking(f).await.map_err(AppError::internal)
    }
}

fn argon2(params: &Params) -> Argon2<'static> {
    Argon2::new(Algorithm::Argon2id, Version::V0x13, params.clone())
}

fn hash_blocking(params: &Params, password: &[u8]) -> anyhow::Result<String> {
    argon2(params)
        .hash_password(password)
        .map(|h| h.to_string())
        .map_err(|e| anyhow::anyhow!("argon2 hashing failed: {e}"))
}

/// Verifies `password` against any supported stored format.
fn verify_blocking(params: &Params, password: &[u8], stored: &str) -> PasswordCheck {
    if stored.starts_with("$argon2") {
        return verify_argon2(params, password, stored, false);
    }
    // Django's Argon2PasswordHasher stores "argon2" + the PHC string.
    if let Some(phc) = stored.strip_prefix("argon2$argon2") {
        return verify_argon2(params, password, &format!("$argon2{phc}"), true);
    }
    if let Some(rest) = stored.strip_prefix("pbkdf2_sha256$") {
        return verify_django_pbkdf2(rest, password, PbkdfDigest::Sha256);
    }
    if let Some(rest) = stored.strip_prefix("pbkdf2_sha1$") {
        return verify_django_pbkdf2(rest, password, PbkdfDigest::Sha1);
    }
    // Django unusable passwords start with "!"; anything else is unknown.
    if !stored.starts_with('!') {
        tracing::warn!("unrecognised password hash format");
    }
    PasswordCheck::Mismatch
}

fn verify_argon2(params: &Params, password: &[u8], phc: &str, legacy: bool) -> PasswordCheck {
    let Ok(parsed) = PasswordHash::new(phc) else {
        tracing::warn!("malformed argon2 hash");
        return PasswordCheck::Mismatch;
    };
    // Verification uses the parameters embedded in the stored hash.
    if argon2(params).verify_password(password, &parsed).is_err() {
        return PasswordCheck::Mismatch;
    }
    let outdated = Params::try_from(&parsed).map_or(true, |stored| {
        stored.m_cost() != params.m_cost()
            || stored.t_cost() != params.t_cost()
            || stored.p_cost() != params.p_cost()
    });
    let wrong_algorithm = parsed.algorithm.as_str() != "argon2id";
    PasswordCheck::Match { needs_rehash: legacy || outdated || wrong_algorithm }
}

#[derive(Debug, Clone, Copy)]
enum PbkdfDigest {
    Sha256,
    Sha1,
}

/// Django format after the algorithm prefix: `<iterations>$<salt>$<base64(hash)>`.
fn verify_django_pbkdf2(rest: &str, password: &[u8], digest: PbkdfDigest) -> PasswordCheck {
    let mut parts = rest.splitn(3, '$');
    let (Some(iterations), Some(salt), Some(expected)) = (parts.next(), parts.next(), parts.next())
    else {
        return PasswordCheck::Mismatch;
    };
    let Ok(iterations) = iterations.parse::<u32>() else {
        return PasswordCheck::Mismatch;
    };
    let Ok(expected) = STANDARD.decode(expected) else {
        return PasswordCheck::Mismatch;
    };
    if iterations == 0 || iterations > MAX_PBKDF2_ITERATIONS || expected.is_empty() {
        return PasswordCheck::Mismatch;
    }
    let mut derived = vec![0u8; expected.len()];
    match digest {
        PbkdfDigest::Sha256 => pbkdf2::pbkdf2_hmac::<sha2::Sha256>(
            password,
            salt.as_bytes(),
            iterations,
            &mut derived,
        ),
        PbkdfDigest::Sha1 => {
            pbkdf2::pbkdf2_hmac::<sha1::Sha1>(password, salt.as_bytes(), iterations, &mut derived);
        }
    }
    if derived.ct_eq(&expected).into() {
        PasswordCheck::Match { needs_rehash: true }
    } else {
        PasswordCheck::Mismatch
    }
}

#[async_trait]
impl PasswordHasher for Argon2Hasher {
    async fn hash(&self, password: &SecretString) -> AppResult<String> {
        let params = self.params.clone();
        let password = password.expose_secret().as_bytes().to_vec();
        self.on_blocking_pool(move || hash_blocking(&params, &password))
            .await?
            .map_err(AppError::Internal)
    }

    async fn verify(&self, password: &SecretString, stored_hash: &str) -> AppResult<PasswordCheck> {
        let params = self.params.clone();
        let password = password.expose_secret().as_bytes().to_vec();
        let stored = stored_hash.to_owned();
        self.on_blocking_pool(move || verify_blocking(&params, &password, &stored)).await
    }

    async fn burn(&self, password: &SecretString) {
        let params = self.params.clone();
        let password = password.expose_secret().as_bytes().to_vec();
        let dummy = Arc::clone(&self.dummy_hash);
        let _ = self.on_blocking_pool(move || verify_blocking(&params, &password, &dummy)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cheap() -> Argon2Hasher {
        Argon2Hasher::new(Argon2Config { memory_kib: 8, iterations: 1, parallelism: 1 }, 2).unwrap()
    }

    fn secret(s: &str) -> SecretString {
        SecretString::from(s.to_owned())
    }

    #[tokio::test]
    async fn argon2_round_trip() {
        let hasher = cheap();
        let hash = hasher.hash(&secret("correct horse")).await.unwrap();
        assert!(hash.starts_with("$argon2id$v=19$m=8,t=1,p=1$"));
        assert_eq!(
            hasher.verify(&secret("correct horse"), &hash).await.unwrap(),
            PasswordCheck::Match { needs_rehash: false }
        );
        assert_eq!(hasher.verify(&secret("wrong"), &hash).await.unwrap(), PasswordCheck::Mismatch);
    }

    #[tokio::test]
    async fn outdated_parameters_ask_for_a_rehash() {
        let old = Argon2Hasher::new(Argon2Config { memory_kib: 16, iterations: 1, parallelism: 1 }, 1)
            .unwrap();
        let hash = old.hash(&secret("pw")).await.unwrap();
        assert_eq!(
            cheap().verify(&secret("pw"), &hash).await.unwrap(),
            PasswordCheck::Match { needs_rehash: true }
        );
    }

    /// Same layout as Django's `make_password(..., hasher="pbkdf2_sha256")`, with a small
    /// iteration count to keep the test fast.
    #[tokio::test]
    async fn django_pbkdf2_hashes_verify_and_need_rehash() {
        let iterations = 1_000;
        let salt = "dzbussalt";
        let mut derived = [0u8; 32];
        pbkdf2::pbkdf2_hmac::<sha2::Sha256>(b"Passw0rd!", salt.as_bytes(), iterations, &mut derived);
        let stored = format!("pbkdf2_sha256${iterations}${salt}${}", STANDARD.encode(derived));
        let hasher = cheap();
        assert_eq!(
            hasher.verify(&secret("Passw0rd!"), &stored).await.unwrap(),
            PasswordCheck::Match { needs_rehash: true }
        );
        assert_eq!(hasher.verify(&secret("nope"), &stored).await.unwrap(), PasswordCheck::Mismatch);
    }

    /// Known-answer vectors computed independently with Python's `hashlib.pbkdf2_hmac`
    /// (the primitive Django uses), in Django's storage format.
    #[tokio::test]
    async fn known_answer_vectors() {
        let hasher = cheap();
        let sha256 = "pbkdf2_sha256$260000$seasalt$YlZ2Vggtqdc61YjArZuoApoBh9JNGYoDRBUGu6tcJQo=";
        assert_eq!(
            hasher.verify(&secret("lètmein"), sha256).await.unwrap(),
            PasswordCheck::Match { needs_rehash: true }
        );
        let sha1 = "pbkdf2_sha1$1000$seasalt$h8WVtFzNLTNUp5hU+IFmjz0virc=";
        assert_eq!(
            hasher.verify(&secret("lettmein"), sha1).await.unwrap(),
            PasswordCheck::Match { needs_rehash: true }
        );
    }

    #[tokio::test]
    async fn unusable_and_malformed_hashes_never_match() {
        let hasher = cheap();
        for stored in ["!unusable", "", "pbkdf2_sha256$x$y$z", "pbkdf2_sha256$0$s$AAAA", "md5$a$b", "$argon2id$garbage"] {
            assert_eq!(hasher.verify(&secret("x"), stored).await.unwrap(), PasswordCheck::Mismatch, "{stored}");
        }
        hasher.burn(&secret("anything")).await;
    }
}
