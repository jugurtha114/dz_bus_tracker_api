# Role
You are a principal Rust backend engineer. Your task is to port the DZ Bus Tracker backend (currently Django 5.2 + DRF + Channels + Celery, in this repository) to a new high-performance Rust service. Write production-grade code: secure, modular, consistent, tested and observable. When a requirement here conflicts with correctness or security, put correctness and security first and explain the deviation. If a decision is ambiguous and expensive to reverse, ask me before you implement it.

# 0. Ground truth first (mandatory before writing code)
The existing Python code is the functional specification. Before you design anything, read:
- `apps/*/models.py`: every entity, enum, unique constraint and relation.
- `apps/api/v1/**` and `apps/*/views.py`: every endpoint and custom action.
- `apps/api/permissions.py`, `apps/core/permissions.py`: the role and ownership rules.
- `apps/*/services*.py`, `apps/tracking/services/*`: the business logic (driver lifecycle, trips, ETA, waiting lists, gamification, ratings).
- `apps/tracking/consumers.py`, `config/asgi.py`: the WebSocket protocol and the groups/events.
- `config/celery.py`, `apps/*/tasks.py`: scheduled jobs.
- `apps/api/throttling.py`, `apps/api/pagination.py`, `config/settings/base.py`.

Then produce `docs/PARITY_MATRIX.md`. It maps every current endpoint, WS message, Celery task and model to its Rust equivalent, and marks each one keep / redesign / drop, with a reason. Do not invent tables or features that are absent from the source unless I approve them.

# 1. Constraints
- **Target:** Linux only (Ubuntu 26.04+ host), running in containers (Podman or Docker; both must work, rootless-friendly). Nothing gets installed on the host except the container runtime.
- **Edge:** nginx terminates TLS (certbot) and HTTP/3/QUIC. The Rust app listens on **plain HTTP (HTTP/1.1 + h2c)** on an internal port. It trusts `X-Forwarded-For`/`X-Real-IP` only from configured proxy CIDRs.
- **Versions:** use the **latest stable release** of every crate, image and tool. Check crates.io and Docker Hub at implementation time; do not rely on memory. Pin them with `rust-toolchain.toml` (stable channel, edition 2024), a committed `Cargo.lock` and image digests/tags. Record the chosen versions in `docs/VERSIONS.md`.
- **Scope now:** backend only. A Next.js web client and a React Native client come later, so the API must be clean, versioned and documented for them and for third-party integrators.

# 2. Stack (verify latest versions; justify any substitution)
- **HTTP/WS:** `axum` + `tokio` + `tower` / `tower-http` (trace, cors, compression, timeout, request-id, limit, sensitive-headers).
- **DB:** PostgreSQL (latest major) + **PostGIS**, accessed with `sqlx` (compile-time checked queries, offline mode `.sqlx/` committed, rustls TLS, migrations via `sqlx migrate`).
  - Coordinates move from decimal lat/lon to `geography(Point,4326)`.
  - Line routes are stored as `geography(LineString,4326)`.
  - Add GiST indexes.
- **Cache / pub-sub / rate limiting / job queue:** Valkey (latest), accessed with `fred` (latest) or `redis-rs`; pick one and justify it.
- **Serialization:** `serde`/`serde_json` for REST. WebSocket uses JSON by default, plus an optional `prost` protobuf encoding negotiated through `Sec-WebSocket-Protocol` (`dzbus.v1.json` / `dzbus.v1.proto`).
- **Auth:**
  - Tokens: `jsonwebtoken` (latest), EdDSA or ES256 signing with key rotation (`kid`). Short-lived access tokens; rotating refresh tokens stored hashed in the DB, with reuse detection and revocation on logout.
  - Passwords: `argon2id`. Add a migration path for existing Django PBKDF2 hashes: verify the old hash, then rehash on the next login.
- **Validation:** `validator` or `garde`. **Errors:** `thiserror` in the domain layer and RFC 9457 `application/problem+json` at the HTTP edge.
- **API docs:** `utoipa` generating OpenAPI 3.1, plus Scalar or Swagger UI served at `/api/docs`.
- **Config:** env-based typed config (`figment` or `config`), validated at startup; fail fast on bad config.
- **Observability:**
  - `tracing` + `tracing-subscriber` (JSON logs) + OpenTelemetry OTLP export (optional, env-toggled).
  - Prometheus `/metrics`.
  - `/health/live` and `/health/ready`, which checks the DB, Valkey and migration status.
- **Background jobs:** replace Celery with an in-process scheduler (`tokio-cron-scheduler` or equivalent) plus a durable job queue: Postgres `SKIP LOCKED` (e.g. `apalis`) or Valkey streams.
  - Jobs must be idempotent and safe to run on multiple replicas. Use advisory locks or a leader lease for cron jobs.
  - The worker can run as a separate binary/process (`dz-worker`) from the same workspace.

# 3. Architecture
Cargo workspace, modular-monolith first (it can be split into microservices later along these crate boundaries):
```
crates/
  domain/      # entities, value objects (LatLng, Role, DriverStatus...), domain errors; no I/O
  app/         # use-cases/services, ports (traits) for repos, cache, notifier, clock
  infra/       # sqlx repositories, Valkey adapters, FCM/SMS/email adapters, job queue
  api/         # axum routers, extractors, DTOs, OpenAPI, WS gateway, middleware
  proto/       # .proto files + prost build for WS telemetry
bin/
  dz-api/      # HTTP + WS server
  dz-worker/   # scheduled + queued jobs
  dz-cli/      # admin tasks: migrate, create-admin, import-from-django
```
- Hexagonal / ports-and-adapters design. Handlers stay thin, take DTOs and call use-cases. Repositories sit behind traits so they can be tested.
- Shared state is `Arc<AppState>` holding the pool, the cache client, config and services. No global mutable state.
- Graceful shutdown on SIGTERM/SIGINT: drain HTTP, close WS connections with code 1001, finish in-flight jobs.
- Consistent conventions throughout:
  - snake_case JSON
  - UUIDv7 IDs
  - RFC 3339 UTC timestamps (display timezone Africa/Algiers is a client concern)
  - cursor pagination (`?cursor=&limit=`, max 100) plus allow-listed filtering/sorting
  - `Idempotency-Key` support on POSTs that create resources
  - ETag / `If-None-Match` on cacheable GETs
- i18n: error messages and notifications in fr (default), ar and en, chosen from `Accept-Language` / the user profile.

# 4. Authorization (robust, flexible, central)
- Roles: `admin`, `driver`, `passenger`, plus a `service` role for machine-to-machine API keys (hashed, scoped, revocable). The model must allow adding roles and permissions without touching handlers.
- Permissions are typed (`enum Permission { BusApprove, LineWrite, TrackingPublish, ... }`), mapped from roles in a single policy module.
- Resource policies cover ownership and state, for example:
  - only an **approved** driver assigned to the bus may publish its location
  - a passenger may rate a driver only after interacting with that driver's bus within 48h, once per day
  - users edit only their own profile and device tokens
- Enforcement is through typed axum extractors/guards (e.g. `RequirePermission<P>`) plus `Policy::authorize(actor, action, resource)` in the use-case layer. Deny by default.
- Every authorization decision is testable. Write table-driven tests covering each role × action.
- Admin actions (approve/reject/suspend a driver or bus, adjust currency) write an append-only audit log.

# 5. Functional scope (in milestones; parity with the existing app)
Deliver in this order. Each milestone must compile, pass `cargo fmt --check`, `cargo clippy -D warnings` and its tests, and leave nothing unimplemented (no `todo!()`, no placeholder comments). Stop after each milestone with a summary so I can review before you continue.

**M1 – Foundation.** Workspace, config, errors, telemetry, health, migrations for the core schema (users, profiles, drivers, buses, lines, stops, line_stops, schedules), auth (register, login, refresh, logout, me, change and reset password), the RBAC/policy module, OpenAPI, Containerfile, compose and nginx.

**M2 – Catalogue.** Full CRUD and custom actions for lines, stops, schedules and disruptions:
- `stops/nearby` using PostGIS `ST_DWithin` + KNN `<->`
- line search
- journey planning between two stops
- driver registration and lifecycle (pending → approved, rejected or suspended; reapply), with a status log
- bus approval and activation

**M3 – Real-time tracking.**
- `POST` location updates and the WS ingress for drivers.
- Trip start/stop. Nearest stop within 500 m.
- The latest bus position is cached in Valkey (hash plus a geo index, TTL'd). Fan-out goes through Valkey pub/sub so it works across replicas.
- WS gateway at `/api/v1/ws`:
  - Auth by short-lived ticket (`POST /api/v1/ws/ticket` → one-time token in the query) instead of a long-lived JWT in the URL.
  - Subscribe/unsubscribe to `bus:{id}`, `line:{id}`, `stop:{id}` and the user's own channel.
  - Heartbeat ping/pong. Bounded per-connection send buffers (slow consumers are dropped, not allowed to block). Per-connection rate limits. Max message size.
  - The event names stay compatible with the current consumer (`bus_location_update`, `waiting_count_update`, `trip_update`, `notification`, ...).
- `GET /api/v1/tracking/active-buses` as GeoJSON FeatureCollection. It reads from Valkey and falls back to PostGIS; cache stampede is prevented with single-flight.
- Location history is written in batches. The table is partitioned by time (native partitioning), with a retention job.
- ETA: along the line's stop sequence, using live speed when it is plausible, otherwise historical segment times, otherwise the bus average. Speed-anomaly and route-deviation detection.

**M4 – Passenger features.** Waiting passengers, bus waiting lists (join/leave/summary), crowd-sourced waiting-count reports with verification, driver ratings (with the eligibility rules), and passenger counts.

**M5 – Notifications.** Device tokens; notification preferences per type and channel. Channels:
- push via the FCM HTTP v1 API (direct HTTP, no SDK)
- SMS through a provider trait (Twilio adapter)
- email via `lettre`
- in-app via WS

Also scheduled arrival alerts, and the jobs that replace the Celery beat schedule (see the parity matrix).

**M6 – Gamification and offline sync.** Reputation, virtual currency (a double-entry-style ledger with transactions applied atomically), driver performance, leaderboards (Valkey sorted sets), premium features, and the offline cache/sync endpoints. Ask me before building M6, because I may simplify it.

**M7 – Data migration.** `dz-cli import-from-django`: migrate the existing PostgreSQL data (users with their password hashes, decimal coordinates → geography), idempotent and resumable.

# 6. Performance and resilience targets
- Write SLOs and verify them with a load test (`k6` or `oha`, scripts committed under `loadtest/`):
  - p99 < 5 ms for cached reads (active buses, nearby stops) at 5k RPS on a 4-vCPU box
  - p99 < 25 ms for DB-backed writes
  - 50k concurrent WS clients per instance with a fan-out latency p99 < 50 ms
- No blocking calls on the async runtime (use `spawn_blocking` for CPU-heavy work such as argon2).
- Tune the DB pool. Prepared statements. Avoid N+1 queries (use joins or batched loads). Every hot path has an index; justify each one with `EXPLAIN`.
- Timeouts on every outbound call. Retries with jitter only for idempotent operations. Circuit breaking for third-party providers. Backpressure everywhere.
- Rate limiting is stored in Valkey (GCRA or sliding window), per user/IP/API key, with the current tiers: anon 30/min, user 60/min, location 100/min, burst 60/min.

# 7. Security
- OWASP API Top 10 checklist in `docs/SECURITY.md`.
- Strict CORS allow-list from config. Request body size limits. Input validation on every DTO. Parameterized SQL only. Secrets only from env/secret files, never logged (redact headers).
- Login brute-force protection, account lockout and generic auth error messages.
- File uploads (avatars, bus/stop/driver photos): S3-compatible object storage (`aws-sdk-s3` or `object_store`) with presigned URLs. MIME and size are validated. No user files on local disk.
- Non-root, read-only-rootfs container. `cargo audit` / `cargo deny` in CI.

# 8. Testing and quality
- Unit tests for the domain and policies. Integration tests against real Postgres+PostGIS and Valkey via `testcontainers`. API tests for every endpoint covering success, validation errors, 401, 403 and 404. WS protocol tests.
- Property tests (`proptest`) for geo/ETA math.
- CI: GitHub Actions running fmt, clippy, tests, `sqlx prepare --check`, `cargo deny`, the container build and an OpenAPI diff.

# 9. Deployment artifacts
- `Containerfile` (Dockerfile-compatible), multi-stage:
  - build with `cargo-chef` for layer caching
  - final image `gcr.io/distroless/cc-debian13` (or `debian:trixie-slim` if a shell is needed)
  - non-root, healthcheck via the binary (`dz-api healthcheck`)
- `compose.yaml` that works with both `docker compose` and `podman compose`:
  - services: api, worker, postgres+postgis, valkey, nginx
  - named volumes, healthchecks with `depends_on: condition: service_healthy`, resource limits, internal network
  - only nginx publishes ports
  - `.env.example` with every variable documented
- `nginx/dz-bus.conf`:
  - HTTP only (port 80), with the certbot `/.well-known/acme-challenge/` location
  - commented placeholders showing where the TLS + HTTP/3 (`listen 443 quic reuseport; http3 on;` + `Alt-Svc`) directives go after certbot
  - `limit_req` zones, WebSocket upgrade for `/api/v1/ws`, long WS read timeouts, gzip/brotli for JSON, upstream keepalive, real-IP forwarding, security headers
- `README.md`: one-command bootstrap, migration, admin creation, and how to run the tests and the load tests.

# 10. Output rules
- Work milestone by milestone and commit after each one with a clear message.
- For every file: full content, no omissions. If something is truly out of scope, say so explicitly in the milestone summary. Do not leave it silently missing.
- Explain your non-obvious decisions briefly in `docs/ADR/NNNN-*.md` (architecture decision records).
- If you find a bug or questionable rule in the existing Python logic, do not copy it blindly. List it and propose the fix.
