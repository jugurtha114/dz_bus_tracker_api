# 0004 — Valkey with the `fred` client

* Status: accepted
* Date: 2026-10-05

## Context

Valkey (the BSD-licensed Redis fork) holds short-lived shared state: rate-limit buckets,
session revocation markers, idempotency records, and from M3 live bus positions and pub/sub
fan-out between API replicas. The spec allows `fred` or `redis-rs`.

## Decision

Use **fred 10** with a connection pool.

* Built-in pooling, automatic reconnection with backoff, per-command timeouts and
  `max_command_attempts` — essential for fail-open/fail-closed decisions to be fast.
* First-class Lua script support (`EVALSHA` with automatic reload) for atomic GCRA.
* A dedicated subscriber client with automatic re-subscription after reconnects (needed for
  WebSocket fan-out in M3), RESP3, and typed command traits.
* Keys are namespaced by a configurable prefix (`dz:`); the Valkey ACL confines the
  application user to that prefix.

## Consequences

* One more abstraction than raw `redis-rs`, but no separate pool crate (`bb8`/`deadpool`).
* Failure policy is explicit per use: rate limiting fails **open** (counted in metrics),
  session revocation checks fail **closed**.

## Alternatives considered

* **redis-rs + deadpool-redis** — solid, but reconnection, pub/sub re-subscription and
  script handling would be hand-written.
