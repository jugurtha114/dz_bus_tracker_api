//! Distributed rate limiting with the Generic Cell Rate Algorithm (GCRA).
//!
//! One key per (tier, identity) stores the "theoretical arrival time" (TAT). The decision and
//! the update happen atomically in a Lua script using the server clock, so every API replica
//! shares the same buckets and clock skew between replicas does not matter.

use std::time::Duration;

use async_trait::async_trait;
use dz_app::ports::{Quota, RateDecision, RateLimiter};
use dz_app::{AppError, AppResult};
use fred::types::scripts::Script;

use super::Valkey;

/// KEYS[1] = bucket key; ARGV[1] = emission interval (ms); ARGV[2] = burst.
/// Returns {allowed (0/1), retry_after_ms, reset_after_ms, remaining}.
const GCRA_LUA: &str = r"
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local interval = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local tolerance = interval * burst
local tat = tonumber(redis.call('GET', KEYS[1]))
if tat == nil or tat < now then
  tat = now
end
local new_tat = tat + interval
local allow_at = new_tat - tolerance
if allow_at > now then
  local remaining_tat = tat - now
  return {0, allow_at - now, remaining_tat, 0}
end
redis.call('SET', KEYS[1], new_tat, 'PX', math.max(1, new_tat - now))
local remaining = math.floor((tolerance - (new_tat - now)) / interval)
return {1, 0, new_tat - now, remaining}
";

/// GCRA rate limiter backed by Valkey.
#[derive(Clone)]
pub struct ValkeyRateLimiter {
    valkey: Valkey,
    script: Script,
}

impl std::fmt::Debug for ValkeyRateLimiter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ValkeyRateLimiter").finish_non_exhaustive()
    }
}

impl ValkeyRateLimiter {
    #[must_use]
    pub fn new(valkey: Valkey) -> Self {
        Self { valkey, script: Script::from_lua(GCRA_LUA) }
    }
}

#[async_trait]
impl RateLimiter for ValkeyRateLimiter {
    async fn check(&self, key: &str, quota: Quota) -> AppResult<RateDecision> {
        let interval_ms =
            u64::try_from(quota.emission_interval().as_millis()).unwrap_or(u64::MAX).max(1);
        let burst = u64::from(quota.burst.max(1));
        let full_key = self.valkey.key(&format!("rl:{key}"));
        let client = self.valkey.pool().next();
        let reply: Vec<i64> = self
            .script
            .evalsha_with_reload(client, vec![full_key], vec![interval_ms, burst])
            .await
            .map_err(|e| {
                tracing::warn!(error = %e, "rate limiter unavailable");
                AppError::Unavailable("rate limiter")
            })?;
        let [allowed, retry_after_ms, reset_after_ms, remaining] = reply[..] else {
            return Err(AppError::Internal(anyhow::anyhow!("unexpected GCRA reply: {reply:?}")));
        };
        let millis = |v: i64| Duration::from_millis(u64::try_from(v).unwrap_or(0));
        Ok(RateDecision {
            allowed: allowed == 1,
            limit: quota.burst.max(1),
            remaining: u32::try_from(remaining).unwrap_or(0),
            retry_after: millis(retry_after_ms),
            reset_after: millis(reset_after_ms),
        })
    }
}
