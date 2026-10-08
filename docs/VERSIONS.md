# Versions

Everything the backend is built and run with is pinned. This file records the pins and how to
move them; `Cargo.lock`, `rust-toolchain.toml`, `Containerfile`, `compose.yaml` and
`.github/workflows/ci.yml` are the sources of truth.

Last reviewed: 2026-10-08.

## Toolchain

| Item | Version | Pinned in |
|---|---|---|
| Rust | 1.99.0 (edition 2024, resolver 3) | `rust-toolchain.toml`, `Containerfile` (`RUST_VERSION`, image tag + digest) |
| cargo-chef | 0.1.78 | `Containerfile` (`CARGO_CHEF_VERSION`) |
| sqlx-cli | 0.9.0 | CI (`taiki-e/install-action`) |

## Main crates (exact versions in `Cargo.lock`)

| Area | Crate | Version |
|---|---|---|
| Runtime | tokio | 1.53.2 |
| HTTP | axum / tower / tower-http / hyper | 0.8.9 / 0.5.3 / 0.7.1 / 1.11.1 |
| Database | sqlx (postgres, rustls, offline macros) | 0.9.0 |
| Valkey | fred | 10.1.0 |
| OpenAPI | utoipa / utoipa-axum | 6.0.0 / 0.3.0 |
| Tokens | jsonwebtoken (rust_crypto, EdDSA) / ed25519-dalek | 11.1.0 / 3.0.0 |
| Passwords | argon2 / pbkdf2 (legacy import) | 0.6.0 / 0.13.0 |
| Validation | validator | 0.21.0 |
| Config | figment | 0.10.19 |
| Telemetry | tracing / opentelemetry(-otlp) / metrics-exporter-prometheus | 0.1.44 / 0.33.0 / 0.18.3 |
| Mail | lettre (rustls) | 0.11.23 |
| Object storage | rusty-s3 (SigV4 presigning, `rustcrypto` only) / jiff (its timestamps) | 0.10.2 / 0.2.37 |
| HTTP client (storage) | reqwest (`rustls-no-provider`) / rustls (ring provider) / rustls-platform-verifier | 0.13.5 / 0.23.45 / 0.7.1 |
| Scheduling | croner | 4.0.1 |
| CLI | clap | 4.6.7 |
| Tests | testcontainers | 0.28.0 |

`tower-http 0.6` and `ed25519-dalek 2` also appear in the lock file as transitive dependencies
of other crates (`cargo deny` reports duplicates as warnings).

reqwest is built without its default TLS backend (which would pull `aws-lc-rs`/`aws-lc-sys`):
the storage adapter hands it a rustls configuration with the ring provider, the same crypto
stack as sqlx, lettre and the test kit (`cargo tree -i aws-lc-sys` finds nothing).

## Container images

Images are referenced by tag **and** digest (multi-arch index digest), so a re-pushed tag cannot
change what runs.

| Image | Tag | Digest | Used by |
|---|---|---|---|
| `docker.io/library/rust` | `1.99.0-slim-trixie` | `sha256:24e632c09342c20abf8312cf4f61430a911c01ed3a5e4c02b87292b1c39c5273` | build stage |
| `gcr.io/distroless/cc-debian13` | `nonroot` | `sha256:e792ab3d241a468a4fd7519ddbbebe66b49b5f365771716ea688ad40b6c6f1c2` | runtime stage |
| `docker.io/postgis/postgis` | `18-3.6-alpine` (PostgreSQL 18, PostGIS 3.6) | `sha256:ffcf0c4b904e41b9779f8098007fb5a9484025319c18c70cf8e1bcebb742b9b7` | compose, CI, test kit |
| `docker.io/valkey/valkey` | `9.1.2-alpine` | `sha256:48332870af354a799964c0012ae1194a0bf2bf894eb508f945810596dc2d8d11` | compose, CI, test kit |
| `docker.io/rustfs/rustfs` | `1.0.1` (S3-compatible object storage) | `sha256:1803faef57627e2d9c2e7d89d655d712ddded5389040054987163043fecb6a3c` | compose (`storage` profile), CI, test kit |
| `docker.io/nginxinc/nginx-unprivileged` | `1.30.5-alpine` (stable branch) | `sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3` | compose |

The test kit uses tags without digests (`crates/testkit/src/backends.rs`) so that a developer
machine can reuse locally pulled images; CI and compose use digests.

## Front-end assets served by the API

| Asset | Version | Integrity |
|---|---|---|
| `@scalar/api-reference` (docs page at `/api/docs`) | 1.73.0 | `sha384-OKyMdsDX84ypSZEhVun8YElXk5c2GQaH3EXPOc6ItmVcLDUAvKHYwvDLvAgsqVtB` (SRI) |

## CI actions (pinned by commit)

| Action | Tag | Commit |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| Swatinem/rust-cache | v2.9.2 | `6323deb102c322ba6fcbdcafc7e3dddab59af2b6` |
| taiki-e/install-action | v2.87.25 | `183e4297cca2404691e9380e1307288dced5c82a` |
| EmbarkStudios/cargo-deny-action | v2.1.1 | `3c6349835b2b7b196a839186cb8b78e02f7b5f25` |
| docker/setup-buildx-action | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| docker/build-push-action | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |

## Updating

* **Crates:** `cargo update` (or `cargo update -p <crate>`), then `cargo deny check`,
  `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`; if any SQL
  changed, `cargo sqlx prepare --workspace -- --all-targets`.
* **Rust:** change `rust-toolchain.toml` and `RUST_VERSION` + the build image tag/digest in
  `Containerfile` together.
* **Images:** resolve the new digest (`docker buildx imagetools inspect <image>:<tag>`), update
  `Containerfile` / `compose.yaml` / CI, and this table.
* **Scalar:** recompute the SRI hash from the published `dist/browser/standalone.js`
  (`openssl dgst -sha384 -binary standalone.js | openssl base64 -A`).
