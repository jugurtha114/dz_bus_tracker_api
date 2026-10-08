//! The network catalogue: stops, lines, the ordered stops of each line, line routes and
//! schedules.
//!
//! Reads are public (`catalog:read`) and show active rows only; holders of the matching write
//! permission (`stop:write`, `line:write`, `schedule:write`) also see inactive rows and may
//! filter on activity. Every write is audited in its own transaction.

pub mod ports;

mod lines;
mod schedules;
mod stops;

pub use lines::{AddLineStopInput, CreateLineInput, LineListQuery, LineService, UpdateLineInput};
pub use schedules::{CreateScheduleInput, ScheduleService, UpdateScheduleInput};
pub use stops::{
    CreateStopInput, NearbyQuery, NearbyStopView, StopListQuery, StopService, StopView,
    UpdateStopInput,
};

use dz_domain::authz::{Action, Actor, CatalogResource, Policy};
use dz_domain::{Violation, Violations};

use crate::error::AppResult;

/// Shortest and longest search term (`?q=`), in characters.
const SEARCH_MIN_CHARS: usize = 2;
const SEARCH_MAX_CHARS: usize = 100;

/// Whether `actor` sees the inactive rows of `resource`.
fn sees_inactive(actor: &Actor, resource: CatalogResource) -> bool {
    Policy::authorize(actor, &Action::ReadInactive { resource }).is_ok()
}

/// The activity filter of a list: only writers may filter on activity (`403`/`401` for the
/// others, rather than silently ignoring the filter); everyone else sees active rows.
fn activity_filter(
    actor: &Actor,
    resource: CatalogResource,
    is_active: Option<bool>,
) -> AppResult<Option<bool>> {
    match is_active {
        Some(_) => {
            Policy::authorize(actor, &Action::ReadInactive { resource })?;
            Ok(is_active)
        }
        None if sees_inactive(actor, resource) => Ok(None),
        None => Ok(Some(true)),
    }
}

/// Validates a search term: trimmed, 2–100 characters.
fn search_term(raw: Option<&str>, v: &mut Violations) -> Option<String> {
    let term = raw?.trim();
    let chars = term.chars().count();
    if chars < SEARCH_MIN_CHARS {
        v.push("q", Violation::TooShort { min: SEARCH_MIN_CHARS as u64 });
        None
    } else if chars > SEARCH_MAX_CHARS {
        v.push("q", Violation::TooLong { max: SEARCH_MAX_CHARS as u64 });
        None
    } else {
        Some(term.to_owned())
    }
}

#[cfg(test)]
mod tests;
