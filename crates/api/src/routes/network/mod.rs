//! `/api/v1/stops`, `/api/v1/lines` and `/api/v1/schedules`: the network catalogue.
//!
//! Reads are public (`catalog:read`, held by anonymous callers too) and show active rows only;
//! stop, line and schedule administrators also see inactive rows. Writes need `stop:write`,
//! `line:write` or `schedule:write` (administrators, or API keys with those scopes) and are
//! audited.

pub mod lines;
pub mod schedules;
pub mod stops;

// `201 Created` with `Location` and the created resource (shared with the other routes).
use super::created;
