//! DZ Bus Tracker application layer: use-cases orchestrating the domain through ports.
//!
//! Handlers (HTTP, WebSocket, worker, CLI) call these services; services call ports
//! ([`ports`]) that infrastructure adapters implement. Nothing here performs I/O directly.

pub mod account;
pub mod admin;
pub mod auth;
pub mod error;
pub mod jobs;
pub mod mail;
pub mod pagination;
pub mod ports;

#[cfg(any(test, feature = "test-support"))]
pub mod testing;

pub use error::{AppError, AppResult, AuthFailure};
