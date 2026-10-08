//! DZ Bus Tracker domain model.
//!
//! This crate is pure: no I/O, no async, no framework types. It holds identifiers, value
//! objects with their invariants, domain errors and the central authorization policy.

pub mod authz;
pub mod error;
pub mod geo;
pub mod ids;
pub mod lang;
pub mod network;
pub mod password;
pub mod upload;
pub mod user;

pub use error::{ConflictKind, DenyReason, DomainError, FieldViolation, Violation, Violations};
pub use lang::Lang;
