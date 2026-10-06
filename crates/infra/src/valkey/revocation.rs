//! Immediate revocation of access tokens: a TTL'd marker per revoked session, checked on every
//! authenticated request. Markers outlive the longest access token, then disappear.

use std::time::Duration;

use async_trait::async_trait;
use dz_app::ports::RevocationStore;
use dz_app::{AppError, AppResult};
use dz_domain::ids::SessionId;
use fred::prelude::{Expiration, KeysInterface};

use super::Valkey;

#[derive(Debug, Clone)]
pub struct ValkeyRevocationStore {
    valkey: Valkey,
}

impl ValkeyRevocationStore {
    #[must_use]
    pub fn new(valkey: Valkey) -> Self {
        Self { valkey }
    }

    fn key(&self, session: SessionId) -> String {
        self.valkey.key(&format!("revoked:sid:{session}"))
    }
}

#[async_trait]
impl RevocationStore for ValkeyRevocationStore {
    async fn revoke_sessions(&self, sessions: &[SessionId], ttl: Duration) -> AppResult<()> {
        let seconds = i64::try_from(ttl.as_secs().max(1)).unwrap_or(i64::MAX);
        let pipeline = self.valkey.pool().next().pipeline();
        for session in sessions {
            let _: () = pipeline
                .set(self.key(*session), 1, Some(Expiration::EX(seconds)), None, false)
                .await
                .map_err(|e| unavailable(&e))?;
        }
        let _: Vec<fred::types::Value> = pipeline.all().await.map_err(|e| unavailable(&e))?;
        Ok(())
    }

    async fn is_session_revoked(&self, session: SessionId) -> AppResult<bool> {
        let exists: i64 =
            self.valkey.pool().exists(self.key(session)).await.map_err(|e| unavailable(&e))?;
        Ok(exists > 0)
    }
}

fn unavailable(error: &fred::error::Error) -> AppError {
    tracing::warn!(%error, "revocation store unavailable");
    AppError::Unavailable("session store")
}
