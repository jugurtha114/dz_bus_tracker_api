//! Infrastructure adapters implementing the `dz-app` ports.

pub mod health;
pub mod jobs;
pub mod jwt;
pub mod mail;
pub mod password;
pub mod pg;
pub mod shutdown;
pub mod telemetry;
pub mod valkey;
pub mod wiring;

pub use pg::PgStore;
