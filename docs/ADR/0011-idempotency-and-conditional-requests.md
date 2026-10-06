# 0011 — Idempotency-Key for creating requests, ETags for reads

* Status: accepted
* Date: 2026-10-05

## Context

Mobile clients on unreliable networks retry. Retried POSTs must not create duplicates, and
unchanged reads should not re-download payloads.

## Decision

* **Idempotency-Key** (draft-ietf-httpapi-idempotency-key-header) on POST: the key is scoped
  to the caller (user, API key or IP) and the path; the request fingerprint (method, path,
  body SHA-256) is stored with it in Valkey.
  * First request: reserved (60 s), executed; a `2xx` response is stored for 24 h.
  * Retry with the same request: the stored response is replayed (`Idempotent-Replayed: true`).
  * Concurrent duplicate: `409 idempotency_in_progress`; same key, different request:
    `422 idempotency_key_reused`.
  * Errors are not stored (the client can fix and retry). Responses marked
    `Cache-Control: no-store` (tokens, API-key secrets) are never stored: the key is released.
* **ETag**: `GET` responses get a weak ETag derived from the body; `If-None-Match` yields
  `304` with no body. Personal resources use `Cache-Control: private, no-cache`.

## Consequences

* Safe client retries without per-endpoint deduplication logic.
* Body-derived ETags cost one hash per response but need no per-resource versioning.

## Alternatives considered

* **Database-stored idempotency records** — durable but slower; 24 h in Valkey (with AOF)
  matches the retry horizon of clients.
