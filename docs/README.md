# DZ Bus Tracker — Rust backend

The backend of DZ Bus Tracker: a Rust service (axum, tokio, sqlx, fred) over PostgreSQL 18 +
PostGIS and Valkey, replacing the legacy Django application in this repository (see
[ADR 0002](ADR/0002-clean-break-from-the-legacy-api.md)). It is developed milestone by
milestone; this README describes milestone **M1** (identity and administration platform).

| Document | Purpose |
|---|---|
| [PARITY_MATRIX.md](PARITY_MATRIX.md) | Every legacy capability → kept / redesigned / dropped, legacy defects and their fixes |
| [ADR/](ADR/) | Architecture decisions |
| [SECURITY.md](SECURITY.md) | Controls mapped to the OWASP API Security Top 10 |
| [VERSIONS.md](VERSIONS.md) | Pinned toolchain, crates, images, actions |
| [openapi.json](openapi.json) | The API contract (generated, diffed in CI); interactive at `/api/docs` |
| [../loadtest/](../loadtest/README.md) | SLOs and load-test scripts |

## Layout

```text
crates/domain    entities, validation, authorization policy (no I/O)
crates/config    typed settings from DZ_* variables and secret files
crates/app       use cases + ports (traits); in-memory fakes for unit tests
crates/infra     adapters: PostgreSQL, Valkey, Argon2, JWT, SMTP, jobs, telemetry
crates/api       HTTP: routes, extractors, middleware, DTOs, OpenAPI (package dz-http)
crates/testkit   integration/API test support over real PostGIS + Valkey
bin/dz-api       HTTP server (serve | healthcheck | openapi)
bin/dz-worker    background jobs + cron
bin/dz-cli       migrate | migration-status | create-admin | gen-signing-key
migrations/      SQL migrations (sqlx)
.sqlx/           offline query metadata (committed)
```

## Development

Requirements: Rust via rustup (the toolchain in `rust-toolchain.toml` installs itself),
Docker or Podman, and `sqlx-cli` 0.9 for schema work (`cargo install sqlx-cli --version 0.9.0
--no-default-features --features rustls,postgres`).

```sh
# Databases for local development
docker run -d --name dz-dev-pg -p 55432:5432 \
  -e POSTGRES_USER=dzbus -e POSTGRES_PASSWORD=dzbus -e POSTGRES_DB=dzbus \
  postgis/postgis:18-3.6-alpine
docker run -d --name dz-dev-valkey -p 56379:6379 valkey/valkey:9.1.2-alpine

export DATABASE_URL=postgres://dzbus:dzbus@localhost:55432/dzbus   # for sqlx macros
export DZ_ENV=development
export DZ_DATABASE__URL=$DATABASE_URL
export DZ_VALKEY__URL=redis://localhost:56379/0
export DZ_AUTH__ALLOW_EPHEMERAL_KEYS=true       # development only
export DZ_TELEMETRY__LOG_FORMAT=pretty

cargo run -p dz-cli -- migrate
printf 'a long admin passphrase\n' | cargo run -p dz-cli -- create-admin --email admin@example.test
cargo run -p dz-api                              # http://localhost:8080/api/docs
cargo run -p dz-worker                           # jobs and cron (e-mails are logged)
```

Without `DATABASE_URL`, set `SQLX_OFFLINE=true` to compile against `.sqlx/`.

### Checks (what CI runs)

```sh
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace                    # starts throw-away PostGIS/Valkey containers
cargo sqlx prepare --workspace --check -- --all-targets
cargo deny check
cargo run -q -p dz-api -- openapi | diff -u docs/openapi.json -
```

* **Tests** — unit tests use in-memory fakes; `crates/testkit/tests/` exercises every endpoint
  through the real router against PostGIS and Valkey. Each test gets its own database cloned
  from a migrated template. Set `DZ_TEST_DATABASE_URL` / `DZ_TEST_VALKEY_URL` to reuse
  running servers instead of containers, `DZ_TEST_KEEP_DB=1` to keep the database of a failed
  test.
* **Changing SQL** — add a forward-only migration (`sqlx migrate add <name>`), apply it
  (`sqlx migrate run`), run `cargo sqlx prepare --workspace -- --all-targets` and commit
  `.sqlx/` with the change.
* **Changing the API** — regenerate the contract:
  `cargo run -q -p dz-api -- openapi > docs/openapi.json`, and review the diff.

## Configuration

All settings are environment variables `DZ_<SECTION>__<KEY>` (see
[`deploy/dz.env.example`](../deploy/dz.env.example) for the production set and
`crates/config/src/lib.rs` for every key and default). Any variable can be read from a file
by appending `_FILE`. Unknown `DZ_*` variables and unsafe production values stop the process
at start-up with a list of every problem.

## Running with compose (Docker or Podman)

```sh
./deploy/init-secrets.sh                 # passwords, Valkey ACL, Ed25519 signing key
cp deploy/dz.env.example deploy/dz.env   # set URLs, CORS origins, DZ_AUTH__ACTIVE_KEY_ID
$EDITOR deploy/secrets/smtp_url
docker compose up -d --build             # or: podman compose up -d --build
printf 'a long admin passphrase\n' | docker compose run --rm -T migrate create-admin --email you@example.com
```

`compose.yaml` builds the image from `Containerfile` (Docker reads
`Containerfile.dockerignore`, Podman `.containerignore`), runs the migrations once, then the
API, the worker, PostGIS, Valkey and nginx. Only nginx publishes ports (80, and 443 tcp/udp
for TLS/HTTP/3). The repository root also contains the legacy `docker-compose.yml`; compose
prefers `compose.yaml` and prints a warning about the other file.

### TLS and HTTP/3

1. Point DNS at the host and start the stack; nginx serves ACME HTTP-01 challenges from the
   `acme-webroot` volume (`/.well-known/acme-challenge/`).
2. Obtain a certificate with any ACME client writing to the volumes, e.g.
   `docker run --rm -v dz-bus_acme-webroot:/var/www/acme -v dz-bus_letsencrypt:/etc/letsencrypt certbot/certbot certonly --webroot -w /var/www/acme -d api.example.com`.
3. Set `DZ_SERVER_NAME=api.example.com`, uncomment the TLS server in `nginx/dz-bus.conf`,
   replace the HTTP server's `include` with the redirect shown there, and restart nginx.

### Operations

* **Health** — `/health/live` (process up) and `/health/ready` (database, migrations, Valkey)
  on the API port; not routed by nginx. Prometheus metrics on port 9090 (`/metrics`) of the
  API and the worker.
* **Logs** — JSON lines on stdout; `request_id` correlates nginx, API and audit entries.
  Traces go to an OTLP collector when `DZ_TELEMETRY__OTLP_ENDPOINT` is set.
* **Migrations** — `docker compose run --rm migrate` (also `migration-status`). The API reports
  not-ready while the schema is behind.
* **Signing-key rotation** — `openssl genpkey -algorithm ed25519 -out deploy/secrets/jwt/<kid>.pem`
  (`chmod 0644`), set `DZ_AUTH__ACTIVE_KEY_ID=<kid>`, `docker compose up -d api`; delete the
  old key file after 15 minutes (the access-token lifetime) and restart again.
* **Scaling** — `docker compose up -d --scale api=3 --scale worker=2`; nginx picks up new API
  replicas through DNS, workers coordinate through PostgreSQL.
* **Backups** — PostgreSQL holds all durable state
  (`docker compose exec postgres pg_dump -U dzbus -Fc dzbus > backup.dump`); Valkey holds only
  short-lived data.
* **Graceful shutdown** — on SIGTERM the API stops accepting connections and drains for
  `DZ_HTTP__SHUTDOWN_GRACE_SECS` (25 s); the worker finishes in-flight jobs.
