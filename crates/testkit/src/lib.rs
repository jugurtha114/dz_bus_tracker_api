//! Test support for the integration and API test suites.
//!
//! * **Backends.** When `DZ_TEST_DATABASE_URL` (a role allowed to `CREATE DATABASE`) and
//!   `DZ_TEST_VALKEY_URL` are set — CI service containers — they are used as is. Otherwise
//!   disposable `postgis/postgis` and `valkey/valkey` containers are started once per test
//!   binary through testcontainers (Docker or Podman socket) and removed when it exits.
//! * **Isolation.** Every [`TestApp`] gets its own database, cloned from a migrated template
//!   (fast: no per-test migration run), and its own Valkey key prefix, so tests run in
//!   parallel without seeing each other's data, rate-limit buckets or revocations.
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
