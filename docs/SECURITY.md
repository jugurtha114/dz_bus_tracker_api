# Security

How the Rust backend defends itself, mapped to the
[OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/),
plus secrets, transport, containers and the supply chain. Each control names the code that
implements it and the test that proves it, so this page stays checkable.

Status: milestone M1 (identity, administration, platform). Items for later milestones are
marked with the milestone that delivers them.

## Reporting a vulnerability

Do not open a public issue. E-mail the maintainers (see repository owner) with a description
and reproduction steps; expect an acknowledgement within three working days.

## OWASP API Security Top 10

### API1 — Broken object-level authorization

* Every use case calls `Policy::authorize(actor, &Action)` (`crates/domain/src/authz.rs`)
  before touching data; resource actions carry the target (`ReadUser { target }`,
  `ManageUser { target }`).
* Self-service routes never take a user id: `/me`, `/me/profile` and `/auth/sessions` act on
  the authenticated subject only.
* Another user's object is indistinguishable from a missing one (`404`), so ids cannot be
  probed — e.g. revoking someone else's session (`tests/auth.rs`,
  `sessions_can_be_listed_and_revoked`). Malformed ids are `404` too (`PathId`).
* Ids are UUIDv7: unguessable enough for enumeration not to pay, never sequential.

### API2 — Broken authentication

* **Passwords:** Argon2id (m = 19 MiB, t = 2, p = 1; OWASP baseline, enforced in production),
  hashing bounded by a semaphore on the blocking pool so login floods cannot starve the
  runtime (`crates/infra/src/password.rs`). Imported Django PBKDF2 hashes verify in constant
  time and are upgraded to Argon2id on the next login.
* **Password policy:** 12–128 characters, not common, not numeric-only, not similar to the
  e-mail or name (`crates/domain/src/password.rs`).
* **Login:** one generic `invalid_credentials` answer for unknown e-mail, wrong password,
  locked or disabled account, after the same amount of work (a dummy hash is burnt) —
  `login_failures_are_indistinguishable`.
* **Brute force:** exponential per-account lockout computed in SQL (5 failures → 60 s,
  doubling, capped at 32×) — `repeated_failures_lock_the_account`; per-IP credential tier
  (10/min) in the API and a 2 r/s tier in nginx.
* **Access tokens:** EdDSA (Ed25519) JWTs, 15 minutes, algorithm pinned, `iss`/`aud`/`exp` validated,
  30 s leeway, key id (`kid`) rotation with a public JWKS (`crates/infra/src/jwt.rs`).
  Tokens are bound to a session; revoked sessions are rejected immediately through a Valkey
  marker, **fail-closed** if Valkey is unreachable (`revocation_fail_open = false`).
* **Refresh tokens:** opaque 256-bit random values (`dzr_…`), stored as SHA-256 only, rotated
  on every use under a row lock; presenting a spent token revokes the whole session (theft
  detection) — `refresh_tokens_rotate_and_reuse_revokes_the_session`,
  `concurrent_refreshes_rotate_exactly_once`. Sessions also have an absolute lifetime (60 d).
* **Password change/reset** revoke the other sessions / all sessions. Reset tokens are
  single-use, 1 hour, hashed, sent by the worker (no timing or existence oracle) and carried
  in the URL fragment so they never reach logs or `Referer` headers.
* **API keys** (`dzk_<id>_<secret>`): SHA-256 hashed, compared in constant time, scoped to a
  fixed allow-list of grantable permissions, expirable, revocable, last use recorded.

### API3 — Broken object-property-level authorization

* Request DTOs are strict (`#[serde(deny_unknown_fields)]`): sending `role`, `is_active` or
  `email` to `PATCH /me` is a `422 unknown_field`, never silently applied or ignored
  (`updating_the_account`, `registration_is_validated_strictly`).
* Responses are explicit DTOs (`crates/api/src/dto.rs`); entities are never serialized, so
  hashes, lockout counters and internal fields cannot leak.

### API4 — Unrestricted resource consumption

* GCRA rate limits in Valkey (atomic Lua on the server clock), per user / API key / client IP:
  anonymous 30/min, users 60/min, credentials 10/min, location 100/min (M3), services
  1200/min; `RateLimit-*` and `Retry-After` headers (`tests/ops.rs`).
* Request body limit (1 MiB), request deadline (15 s → `503 request_timeout`), PostgreSQL
  `statement_timeout` (5 s) and `idle_in_transaction_session_timeout`, bounded pools,
  cursor pagination capped at 100 items, password hashing concurrency limit.
* nginx: per-IP request and connection limits, header/body timeouts.
* Containers: CPU, memory and PID limits (`compose.yaml`).

### API5 — Broken function-level authorization

* Handlers declare the permission in their signature: `RequirePermission<perm::UserManage>`
  rejects the request before the handler body runs; `CurrentUser` rejects API keys on
  personal endpoints. Permissions come from one policy module (`role_permissions`), deny by
  default.
* A table-driven role × endpoint matrix (`tests/admin.rs`, `permission_matrix`) and a
  "every protected endpoint requires authentication" sweep run in CI. Administrators cannot
  deactivate or demote themselves (lock-out protection).

### API6 — Unrestricted access to sensitive business flows

* Password reset: per-address quota (3 per 15 minutes) and de-duplication of pending jobs, on
  top of the per-IP tier — mail bombing an address is not possible
  (`reset_requests_are_deduplicated_per_address`).
* Registration and login share the strict credential tier; registration cannot choose a role.
* Flows of later milestones (ratings, reports, rewards) get eligibility rules in their own
  milestone (see `docs/PARITY_MATRIX.md` §9).

### API7 — Server-side request forgery

* The API fetches no user-supplied URL. Outbound connections go only to configured hosts
  (PostgreSQL, Valkey, SMTP, optional OTLP collector).
* Uploads (M2) will use S3 presigned URLs generated locally: clients upload directly to object
  storage; the API never downloads user content.

### API8 — Security misconfiguration

* Configuration is validated at start-up and production mode refuses unsafe values: ephemeral
  signing keys, weak Argon2 parameters, non-HTTPS public/reset URLs or CORS origins, the log
  mailer, development database credentials; unknown `DZ_*` variables are errors
  (`crates/config`).
* Strict CORS (exact origins only, credentials not allowed), security headers on every
  response (`nosniff`, `DENY` framing, `no-referrer`, `default-src 'none'` CSP,
  `Cache-Control: no-store` unless a route opts into caching), HSTS at the TLS edge.
* Errors are RFC 9457 problem documents with stable codes; internal errors return a generic
  `internal_error` with a request id — details only go to logs.
* Health details (`/health/ready`) and metrics are not routed by nginx; metrics listen on a
  separate port.

### API9 — Improper inventory management

* One versioned surface (`/api/v1`). The OpenAPI 3.1 document is generated from the handlers,
  committed (`docs/openapi.json`) and diffed in CI, so undocumented or accidental endpoints
  fail the build. Legacy Django endpoints are not exposed by the new service.
* The docs page can be disabled per environment (`DZ_HTTP__DOCS_ENABLED`).

### API10 — Unsafe consumption of APIs

* SMTP uses rustls with WebPKI roots (implicit TLS or mandatory STARTTLS); TLS is never
  downgraded.
* Data read back from Valkey (idempotency replays, revocations) is written only by this
  service under its key prefix; the Valkey ACL confines the application user to that prefix.
* Third-party front-end code on the docs page is pinned and verified with Subresource
  Integrity under a restrictive CSP.

## Secrets

* Secrets come only from the environment or files (`DZ_*_FILE`, e.g. container secrets);
  config values holding them are `SecretString`s whose `Debug`/serialization is redacted.
* `Authorization`, `Cookie`, `Set-Cookie` and `X-Api-Key` are marked sensitive for all
  tracing; request bodies are never logged.
* Tokens, reset tokens and API-key secrets are stored hashed; secret-bearing responses carry
  `Cache-Control: no-store` and are never persisted by the idempotency layer.
* `deploy/init-secrets.sh` generates random database and Valkey passwords, a Valkey ACL (no
  default user, prefix-scoped app user without admin/dangerous commands) and the Ed25519
  signing key; `deploy/secrets/` is git-ignored and private to the operator on the host.

## Audit trail

Administrative actions (user changes, API key creation/revocation) are written to
`audit_log` in the same transaction as the change, with actor, client IP and request id.
Triggers reject `UPDATE`, `DELETE` and `TRUNCATE` (`the_audit_log_is_append_only`).

## Transport

nginx terminates TLS 1.2/1.3 and HTTP/3 (template in `nginx/dz-bus.conf`) and overwrites
`X-Forwarded-For`; the API trusts forwarding headers only from configured proxy CIDRs and
walks the chain from the right (`forwarded_addresses_are_trusted_only_from_proxies`).
PostgreSQL and Valkey are on an internal network without Internet access.

## Containers

* Distroless runtime (no shell, no package manager), non-root user 65532, read-only root file
  system, all capabilities dropped, `no-new-privileges`, resource and PID limits.
* nginx runs unprivileged (uid 101, port 8080); data stores keep only the capabilities their
  entrypoints need to drop privileges.
* Base images pinned by digest (`docs/VERSIONS.md`).

## Supply chain

* `Cargo.lock` committed, `--locked` builds, toolchain pinned.
* `cargo deny` in CI and daily: RustSec advisories (the cargo-audit database), licence
  allow-list, banned crates (OpenSSL/native-tls: rustls only), crates.io as the only source.
* GitHub Actions pinned to commit SHAs; the workflow token is read-only.

## Known gaps / next steps

* E-mail address verification is not yet required to sign in (planned with notifications,
  M5).
* Multi-factor authentication for administrators: proposed for a later milestone.
* The WebSocket channel (M3) will authenticate with a short-lived ticket instead of putting
  the access token in the URL.
