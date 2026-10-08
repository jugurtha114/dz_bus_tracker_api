//! Strongly typed identifiers.
//!
//! Every aggregate gets its own newtype around a UUID so that a `UserId` can never be passed
//! where a `BusId` is expected. New identifiers are UUIDv7 (time-ordered, index friendly);
//! identifiers imported from the legacy Django database are UUIDv4 and remain valid.

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

macro_rules! typed_id {
    ($($(#[$meta:meta])* $name:ident),+ $(,)?) => {$(
        $(#[$meta])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
        #[serde(transparent)]
        pub struct $name(Uuid);

        impl $name {
            /// Generates a fresh, time-ordered (UUIDv7) identifier.
            #[must_use]
            pub fn generate() -> Self {
                Self(Uuid::now_v7())
            }

            #[must_use]
            pub const fn from_uuid(id: Uuid) -> Self {
                Self(id)
            }

            #[must_use]
            pub const fn as_uuid(&self) -> Uuid {
                self.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                self.0.fmt(f)
            }
        }

        impl From<Uuid> for $name {
            fn from(id: Uuid) -> Self {
                Self(id)
            }
        }

        impl From<$name> for Uuid {
            fn from(id: $name) -> Self {
                id.0
            }
        }

        impl FromStr for $name {
            type Err = uuid::Error;

            fn from_str(s: &str) -> Result<Self, Self::Err> {
                Uuid::parse_str(s).map(Self)
            }
        }
    )+};
}

typed_id!(
    /// Identifier of a user account.
    UserId,
    /// Identifier of an authenticated session (a refresh-token family).
    SessionId,
    /// Identifier of a machine-to-machine API key.
    ApiKeyId,
    /// Identifier of an audit-log entry.
    AuditEntryId,
    /// Identifier of a driver profile.
    DriverId,
    /// Identifier of an entry of a driver's status history.
    DriverStatusChangeId,
    /// Identifier of a bus.
    BusId,
    /// Identifier of a bus line.
    LineId,
    /// Identifier of a bus stop.
    StopId,
    /// Identifier of a line schedule (a service window on one weekday).
    ScheduleId,
    /// Identifier of an upload to object storage.
    UploadId,
);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generated_ids_are_v7_and_ordered() {
        let a = UserId::generate();
        let b = UserId::generate();
        assert_eq!(a.as_uuid().get_version_num(), 7);
        assert!(a <= b, "UUIDv7 must be monotonic within a process");
    }

    #[test]
    fn parses_legacy_v4_ids() {
        let legacy = "6f1c1a3e-6a43-4c4b-9a43-2f9d1b4f8e21";
        let id: UserId = legacy.parse().unwrap();
        assert_eq!(id.to_string(), legacy);
    }
}
