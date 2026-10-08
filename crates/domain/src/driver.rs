//! The driver programme: driver profiles, their documents, and the state machine that governs
//! applications, reviews and suspensions (legacy L-24).

use std::fmt;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::error::{ConflictKind, DomainError, Violation};
use crate::ids::{DriverId, DriverStatusChangeId, UserId};
use crate::user::PhoneNumber;

/// Review status of a driver profile.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DriverStatus {
    /// Waiting for a review (new application, re-application or changed documents).
    Pending,
    /// May drive (buses in M2, trips in M3).
    Approved,
    /// The application was refused; the driver may re-apply.
    Rejected,
    /// Approval withdrawn for now; an administrator may reinstate the driver.
    Suspended,
}

impl DriverStatus {
    pub const ALL: [Self; 4] = [Self::Pending, Self::Approved, Self::Rejected, Self::Suspended];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Approved => "approved",
            Self::Rejected => "rejected",
            Self::Suspended => "suspended",
        }
    }

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        Self::ALL.into_iter().find(|s| s.as_str() == raw).ok_or_else(|| Violation::InvalidChoice {
            allowed: Self::ALL.iter().map(|s| s.as_str().into()).collect(),
        })
    }

    /// The status reached by `action` from `from` (`None`: no profile yet), following the
    /// transition table of the M2 design (§4). Anything else is
    /// `Conflict(InvalidTransition)`.
    pub fn transition(from: Option<Self>, action: DriverAction) -> Result<Self, DomainError> {
        use DriverAction as A;
        use DriverStatus as S;
        let to = match (from, action) {
            (None, A::Apply) => S::Pending,
            (Some(S::Pending), A::Approve) | (Some(S::Suspended), A::Reinstate) => S::Approved,
            (Some(S::Pending), A::Reject) => S::Rejected,
            (Some(S::Approved), A::Suspend) => S::Suspended,
            (Some(S::Rejected), A::Reapply) => S::Pending,
            // New documents must be reviewed again before an approved driver drives; the other
            // statuses keep their meaning (pending: the review sees the new documents).
            (Some(S::Pending | S::Approved), A::DocumentsChanged) => S::Pending,
            (Some(status @ (S::Rejected | S::Suspended)), A::DocumentsChanged) => status,
            _ => return Err(DomainError::Conflict(ConflictKind::InvalidTransition)),
        };
        Ok(to)
    }
}

impl fmt::Display for DriverStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// What can happen to a driver profile.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DriverAction {
    /// A user applies to become a driver (creates the profile).
    Apply,
    /// A reviewer accepts a pending application.
    Approve,
    /// A reviewer refuses a pending application (with a reason).
    Reject,
    /// A reviewer withdraws the approval of a driver (with a reason).
    Suspend,
    /// A reviewer restores the approval of a suspended driver.
    Reinstate,
    /// A rejected applicant applies again.
    Reapply,
    /// The driver changed an identity document (number or photo).
    DocumentsChanged,
}

impl DriverAction {
    pub const ALL: [Self; 7] = [
        Self::Apply,
        Self::Approve,
        Self::Reject,
        Self::Suspend,
        Self::Reinstate,
        Self::Reapply,
        Self::DocumentsChanged,
    ];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Apply => "apply",
            Self::Approve => "approve",
            Self::Reject => "reject",
            Self::Suspend => "suspend",
            Self::Reinstate => "reinstate",
            Self::Reapply => "reapply",
            Self::DocumentsChanged => "documents_changed",
        }
    }

    /// Whether the action must be explained to the driver ([`StatusReason`]).
    #[must_use]
    pub const fn requires_reason(self) -> bool {
        matches!(self, Self::Reject | Self::Suspend)
    }
}

/// An Algerian national identity number: exactly 18 digits (spaces ignored).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct NationalIdNumber(String);

impl NationalIdNumber {
    pub const DIGITS: usize = 18;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value: String = raw.chars().filter(|c| !c.is_whitespace()).collect();
        if value.is_empty() {
            return Err(Violation::Required);
        }
        if value.len() != Self::DIGITS || !value.bytes().all(|b| b.is_ascii_digit()) {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value))
    }

    #[must_use]
    pub fn from_trusted(value: String) -> Self {
        Self(value)
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A driving licence number: 1–20 characters `[A-Za-z0-9-]`, stored upper-case (so `ab-12`
/// and `AB-12` are the same licence).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LicenseNumber(String);

impl LicenseNumber {
    pub const MAX_CHARS: usize = 20;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim();
        if value.is_empty() {
            return Err(Violation::Required);
        }
        if value.chars().count() > Self::MAX_CHARS {
            return Err(Violation::TooLong { max: Self::MAX_CHARS as u64 });
        }
        if !value.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value.to_ascii_uppercase()))
    }

    #[must_use]
    pub fn from_trusted(value: String) -> Self {
        Self(value)
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Years of driving experience, 0 to 60.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct YearsOfExperience(u8);

impl YearsOfExperience {
    pub const MAX: u8 = 60;

    pub fn parse(raw: i64) -> Result<Self, Violation> {
        match u8::try_from(raw) {
            Ok(years @ 0..=Self::MAX) => Ok(Self(years)),
            _ => Err(Violation::OutOfRange { min: 0, max: i64::from(Self::MAX) }),
        }
    }

    #[must_use]
    pub const fn years(self) -> u8 {
        self.0
    }
}

/// Why a driver was rejected or suspended: trimmed, 1 to 1000 characters.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct StatusReason(String);

impl StatusReason {
    pub const MAX_CHARS: usize = 1000;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim();
        if value.is_empty() {
            return Err(Violation::Required);
        }
        if value.chars().count() > Self::MAX_CHARS {
            return Err(Violation::TooLong { max: Self::MAX_CHARS as u64 });
        }
        if value.chars().any(|c| c.is_control() && c != '\n' && c != '\r' && c != '\t') {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value.to_owned()))
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A driver profile. Identity documents are private: their photos are object-storage keys,
/// only ever exposed to the driver and to reviewers through presigned URLs (legacy L-03).
#[derive(Debug, Clone, PartialEq)]
pub struct Driver {
    pub id: DriverId,
    /// The account the profile belongs to (always the applicant, legacy L-02).
    pub user_id: UserId,
    pub phone_number: PhoneNumber,
    pub id_card_number: NationalIdNumber,
    pub id_card_photo_key: String,
    pub driver_license_number: LicenseNumber,
    pub driver_license_photo_key: String,
    pub years_of_experience: YearsOfExperience,
    pub status: DriverStatus,
    /// Reason of the last rejection or suspension; empty otherwise.
    pub status_reason: String,
    pub status_changed_at: DateTime<Utc>,
    /// Only approved drivers can be available.
    pub is_available: bool,
    /// Sum of the ratings received (1–5 each).
    pub rating_sum: u32,
    pub rating_count: u32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Driver {
    /// Average rating rounded to two decimals; `None` before the first rating.
    #[must_use]
    pub fn rating(&self) -> Option<f64> {
        (self.rating_count > 0).then(|| {
            let average = f64::from(self.rating_sum) / f64::from(self.rating_count);
            (average * 100.0).round() / 100.0
        })
    }
}

/// One entry of a driver's status history.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DriverStatusChange {
    pub id: DriverStatusChangeId,
    pub driver_id: DriverId,
    /// `None` for the application.
    pub from: Option<DriverStatus>,
    pub to: DriverStatus,
    /// Empty unless the change was a rejection or a suspension.
    pub reason: String,
    /// `None` for the system (or an account deleted since).
    pub changed_by: Option<UserId>,
    pub created_at: DateTime<Utc>,
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;

    use super::*;

    /// The complete transition table: every `(status, action)` pair, including the absence of
    /// a profile. `None` = `409 invalid_transition`.
    #[test]
    fn transition_table_is_exhaustive() {
        use DriverAction as A;
        use DriverStatus as S;
        let (p, a, r, s, x) =
            (Some(S::Pending), Some(S::Approved), Some(S::Rejected), Some(S::Suspended), None);
        #[rustfmt::skip]
        let table = [
            // from   apply approve reject suspend reinstate reapply documents_changed
            (None,   [p,    x,      x,     x,      x,        x,      x]),
            (p,      [x,    a,      r,     x,      x,        x,      p]),
            (a,      [x,    x,      x,     s,      x,        x,      p]),
            (r,      [x,    x,      x,     x,      x,        p,      r]),
            (s,      [x,    x,      x,     x,      a,        x,      s]),
        ];
        let actions = [
            A::Apply,
            A::Approve,
            A::Reject,
            A::Suspend,
            A::Reinstate,
            A::Reapply,
            A::DocumentsChanged,
        ];
        assert_eq!(actions, A::ALL, "columns follow DriverAction::ALL");
        let mut pairs = 0;
        for (from, row) in table {
            for (action, expected) in actions.into_iter().zip(row) {
                let got = DriverStatus::transition(from, action);
                match expected {
                    Some(to) => assert_eq!(got, Ok(to), "{from:?} × {action:?}"),
                    None => assert_eq!(
                        got,
                        Err(DomainError::Conflict(ConflictKind::InvalidTransition)),
                        "{from:?} × {action:?}"
                    ),
                }
                pairs += 1;
            }
        }
        assert_eq!(pairs, (DriverStatus::ALL.len() + 1) * DriverAction::ALL.len());
    }

    #[test]
    fn only_rejections_and_suspensions_need_a_reason() {
        let with_reason: Vec<_> =
            DriverAction::ALL.into_iter().filter(|a| a.requires_reason()).collect();
        assert_eq!(with_reason, [DriverAction::Reject, DriverAction::Suspend]);
    }

    #[test]
    fn statuses_round_trip() {
        for status in DriverStatus::ALL {
            assert_eq!(DriverStatus::parse(status.as_str()), Ok(status));
        }
        assert!(matches!(DriverStatus::parse("active"), Err(Violation::InvalidChoice { .. })));
    }

    #[test]
    fn national_ids_are_18_digits() {
        let id = NationalIdNumber::parse(" 1234 5678 9012 3456 78 ").unwrap();
        assert_eq!(id.as_str(), "123456789012345678");
        assert_eq!(NationalIdNumber::parse(""), Err(Violation::Required));
        for bad in ["12345678901234567", "1234567890123456789", "12345678901234567a", "١٢٣"] {
            assert_eq!(NationalIdNumber::parse(bad), Err(Violation::InvalidFormat), "{bad}");
        }
    }

    #[test]
    fn licence_numbers_are_upper_cased_and_restricted() {
        assert_eq!(LicenseNumber::parse(" ab-12 ").unwrap().as_str(), "AB-12");
        assert_eq!(LicenseNumber::parse("  "), Err(Violation::Required));
        assert_eq!(LicenseNumber::parse("AB 12"), Err(Violation::InvalidFormat));
        assert_eq!(LicenseNumber::parse("AB_12"), Err(Violation::InvalidFormat));
        assert_eq!(LicenseNumber::parse(&"9".repeat(21)), Err(Violation::TooLong { max: 20 }));
        assert!(LicenseNumber::parse(&"9".repeat(20)).is_ok());
    }

    #[test]
    fn experience_and_reasons_are_bounded() {
        assert_eq!(YearsOfExperience::parse(0).unwrap().years(), 0);
        assert_eq!(YearsOfExperience::parse(60).unwrap().years(), 60);
        for bad in [-1, 61, i64::MAX] {
            let expected = Err(Violation::OutOfRange { min: 0, max: 60 });
            assert_eq!(YearsOfExperience::parse(bad), expected, "{bad}");
        }
        assert_eq!(StatusReason::parse("  Expired licence ").unwrap().as_str(), "Expired licence");
        assert_eq!(StatusReason::parse(" \n "), Err(Violation::Required));
        assert_eq!(StatusReason::parse(&"x".repeat(1001)), Err(Violation::TooLong { max: 1000 }));
        assert_eq!(StatusReason::parse("bad\u{0}"), Err(Violation::InvalidFormat));
        assert!(StatusReason::parse("line one\nline two").is_ok());
    }

    fn driver(rating_sum: u32, rating_count: u32) -> Driver {
        let at = DateTime::<Utc>::UNIX_EPOCH;
        Driver {
            id: DriverId::generate(),
            user_id: UserId::generate(),
            phone_number: PhoneNumber::parse("0555123456").unwrap(),
            id_card_number: NationalIdNumber::parse("123456789012345678").unwrap(),
            id_card_photo_key: "driver_id_card/x".into(),
            driver_license_number: LicenseNumber::parse("L-1").unwrap(),
            driver_license_photo_key: "driver_license/x".into(),
            years_of_experience: YearsOfExperience::parse(3).unwrap(),
            status: DriverStatus::Pending,
            status_reason: String::new(),
            status_changed_at: at,
            is_available: false,
            rating_sum,
            rating_count,
            created_at: at,
            updated_at: at,
        }
    }

    #[test]
    fn ratings_are_averaged_to_two_decimals() {
        assert_eq!(driver(0, 0).rating(), None);
        assert_eq!(driver(5, 1).rating(), Some(5.0));
        assert_eq!(driver(14, 3).rating(), Some(4.67));
        assert_eq!(driver(13, 3).rating(), Some(4.33));
    }

    proptest! {
        /// Every reachable status is reached through the table only, and only `Apply` creates
        /// a profile.
        #[test]
        fn random_walks_stay_in_the_table(actions in prop::collection::vec(0usize..7, 0..40)) {
            let mut status: Option<DriverStatus> = None;
            for index in actions {
                let action = DriverAction::ALL[index];
                match DriverStatus::transition(status, action) {
                    Ok(next) => {
                        prop_assert!(status.is_some() || action == DriverAction::Apply);
                        if status.is_some() {
                            prop_assert_ne!(action, DriverAction::Apply);
                        }
                        status = Some(next);
                    }
                    Err(e) => prop_assert_eq!(
                        e,
                        DomainError::Conflict(ConflictKind::InvalidTransition)
                    ),
                }
            }
        }

        #[test]
        fn licence_numbers_are_idempotent(raw in "[A-Za-z0-9-]{1,20}") {
            let licence = LicenseNumber::parse(&raw).unwrap();
            prop_assert_eq!(LicenseNumber::parse(licence.as_str()).unwrap(), licence.clone());
            prop_assert_eq!(licence.as_str(), raw.to_ascii_uppercase());
        }
    }
}
