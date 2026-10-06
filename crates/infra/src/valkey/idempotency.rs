//! `Idempotency-Key` reservations and stored responses in Valkey.

use std::time::Duration;

use async_trait::async_trait;
use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use dz_app::ports::{IdempotencyBegin, IdempotencyStore, StoredResponse};
use dz_app::{AppError, AppResult};
use fred::prelude::{Expiration, KeysInterface, SetOptions};
use serde::{Deserialize, Serialize};

use super::Valkey;

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case")]
enum Entry {
    InProgress { fingerprint: String },
    Done { fingerprint: String, response: StoredResponse },
}

#[derive(Debug, Clone)]
pub struct ValkeyIdempotencyStore {
    valkey: Valkey,
}

impl ValkeyIdempotencyStore {
    #[must_use]
    pub fn new(valkey: Valkey) -> Self {
        Self { valkey }
    }

    fn key(&self, key: &str) -> String {
        self.valkey.key(&format!("idem:{key}"))
    }
}

fn millis(d: Duration) -> i64 {
    i64::try_from(d.as_millis()).unwrap_or(i64::MAX).max(1)
}

fn unavailable(error: &fred::error::Error) -> AppError {
    tracing::warn!(%error, "idempotency store unavailable");
    AppError::Unavailable("idempotency store")
}

#[async_trait]
impl IdempotencyStore for ValkeyIdempotencyStore {
    async fn begin(
        &self,
        key: &str,
        fingerprint: [u8; 32],
        lock_ttl: Duration,
    ) -> AppResult<IdempotencyBegin> {
        let full_key = self.key(key);
        let fingerprint = STANDARD.encode(fingerprint);
        let reservation = serde_json::to_string(&Entry::InProgress {
            fingerprint: fingerprint.clone(),
        })
        .map_err(AppError::internal)?;
        let client = self.valkey.pool().next();
        // Two attempts cover the race where an existing entry expires between SET NX and GET.
        for _ in 0..2 {
            let reserved: Option<String> = client
                .set(
                    &full_key,
                    reservation.as_str(),
                    Some(Expiration::PX(millis(lock_ttl))),
                    Some(SetOptions::NX),
                    false,
                )
                .await
                .map_err(|e| unavailable(&e))?;
            if reserved.is_some() {
                return Ok(IdempotencyBegin::Proceed);
            }
            let existing: Option<String> = client.get(&full_key).await.map_err(|e| unavailable(&e))?;
            let Some(existing) = existing else { continue };
            let entry: Entry = serde_json::from_str(&existing).map_err(AppError::internal)?;
            return Ok(match entry {
                Entry::InProgress { fingerprint: f } | Entry::Done { fingerprint: f, .. }
                    if f != fingerprint =>
                {
                    IdempotencyBegin::Mismatch
                }
                Entry::InProgress { .. } => IdempotencyBegin::InProgress,
                Entry::Done { response, .. } => IdempotencyBegin::Replay(response),
            });
        }
        Ok(IdempotencyBegin::InProgress)
    }

    async fn complete(
        &self,
        key: &str,
        fingerprint: [u8; 32],
        response: &StoredResponse,
        ttl: Duration,
    ) -> AppResult<()> {
        let entry = Entry::Done { fingerprint: STANDARD.encode(fingerprint), response: response.clone() };
        let value = serde_json::to_string(&entry).map_err(AppError::internal)?;
        let _: () = self
            .valkey
            .pool()
            .set(self.key(key), value, Some(Expiration::PX(millis(ttl))), None, false)
            .await
            .map_err(|e| unavailable(&e))?;
        Ok(())
    }

    async fn release(&self, key: &str) -> AppResult<()> {
        let _: i64 = self.valkey.pool().del(self.key(key)).await.map_err(|e| unavailable(&e))?;
        Ok(())
    }
}
