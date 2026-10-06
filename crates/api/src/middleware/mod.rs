//! HTTP middleware.

pub mod auth;
pub mod client_ip;
pub mod etag;
pub mod idempotency;
pub mod metrics;
pub mod rate_limit;
pub mod request_id;
pub mod timeout;

/// Header carrying the request id (set by nginx or generated here).
pub const REQUEST_ID: &str = "x-request-id";
