//! Test support for the integration and API test suites.
//!
//! * **Backends.** When `DZ_TEST_DATABASE_URL` (a role allowed to `CREATE DATABASE`),
//!   `DZ_TEST_VALKEY_URL` and `DZ_TEST_S3_URL` are set — CI service containers, long-lived
//!   development containers — they are used as is. Otherwise disposable `postgis/postgis`,
//!   `valkey/valkey` and `rustfs/rustfs` containers are started once per test binary through
//!   testcontainers (Docker or Podman socket) and removed when it exits. Each variable is
//!   independent: any subset may be set.
//! * **`DZ_TEST_S3_URL`** is the S3 endpoint with root credentials allowed to create buckets,
//!   as user information: `http://<access key>:<secret key>@<host>:<port>`, e.g.
//!   `http://dzdevaccess:dzdevsecret-0123456789@127.0.0.1:59000` for
//!   `docker run -d -p 59000:9000 -e RUSTFS_ACCESS_KEY=dzdevaccess
//!   -e RUSTFS_SECRET_KEY=dzdevsecret-0123456789 rustfs/rustfs:1.0.1`. The keys must consist of
//!   URL-safe characters.
//! * **Isolation.** Every [`TestApp`] gets its own database, cloned from a migrated template
//!   (fast: no per-test migration run), its own Valkey key prefix and its own bucket
//!   (`dz-t-<uuid>`, removed with its objects when the app is dropped), so tests run in
//!   parallel without seeing each other's data, files, rate-limit buckets or revocations.
//!   Storage can be switched off per test with
//!   `TestApp::builder().configure(|s| s.storage.endpoint = None)`.
//! * **In-process HTTP.** Requests go through the complete production router and middleware
//!   stack with `tower::ServiceExt::oneshot`; no sockets, no ports.
//!
//! Test support is allowed to panic: a failed precondition should fail the test loudly.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::missing_panics_doc)]

mod app;
mod backends;
mod client;
mod database;

pub use app::{Account, PASSWORD, TestApp, TestAppBuilder};
pub use client::{TestRequest, TestResponse};
pub use database::TestDatabase;
