# 0009 — GCRA rate limiting in Valkey

* Status: accepted
* Date: 2026-10-05

## Context

Legacy throttling (DRF) was per process, used fixed windows, never applied the location
tier, and a `1000/day` sustained limit locked drivers out after about four hours (L-13).
Several API replicas must share limits.

## Decision

* The **Generic Cell Rate Algorithm**: one key per (tier, identity) stores the theoretical
  arrival time; decision and update run atomically in a Lua script on the Valkey server clock
  (no clock skew between replicas, one round trip, O(1) memory per identity).
* Tiers: anonymous per client IP (30/min), users per user id (60/min, burst 60), credential
  endpoints per IP (10/min, in addition), API keys per key (1200/min), driver location
  publishing per driver (100/min, M3).
* Responses carry `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`
  (the most restrictive applicable tier); rejections are `429` with `Retry-After`.
* If Valkey is unreachable, rate limiting fails **open** and the failure is counted
  (`dz_http_rate_limiter_errors_total`); nginx's coarse per-IP limits still apply.

## Consequences

* Smooth limits without window-boundary bursts; bursts are explicit per tier.
* Client IPs come from the trusted-proxy resolution (no spoofing through headers).

## Alternatives considered

* **In-process limiter (governor)** — not shared between replicas.
* **Fixed/sliding windows with INCR** — boundary bursts or more memory.
