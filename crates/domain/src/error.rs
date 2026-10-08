//! Domain errors and validation violations.
//!
//! Violations are machine-readable (a stable `code` plus typed parameters) so that the HTTP edge
//! can render them as RFC 9457 problem details in the caller's language.

use std::borrow::Cow;

use serde::Serialize;

/// A single rule broken by an input value.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum Violation {
    Required,
    InvalidFormat,
    InvalidEmail,
    InvalidPhone,
    TooShort { min: u64 },
    TooLong { max: u64 },
    OutOfRange { min: i64, max: i64 },
    InvalidChoice { allowed: Vec<Cow<'static, str>> },
    PasswordTooShort { min: u64 },
    PasswordTooLong { max: u64 },
    PasswordTooCommon,
    PasswordEntirelyNumeric,
    PasswordTooSimilar,
    PasswordReused,
    /// A secret supplied for confirmation (e.g. the current password) does not match.
    Incorrect,
    UnknownField,
    /// The referenced upload cannot be used: unknown, someone else's, for another purpose,
    /// already used or expired, or its object is missing or differs from the declaration.
    InvalidUpload,
    /// The value appears more than once in a list that must not repeat it.
    Duplicate,
    /// The value refers to a resource that does not exist (e.g. an unknown stop id).
    UnknownReference,
    /// The value must be after the value of `field` (e.g. an end after its start).
    MustBeAfter { field: Cow<'static, str> },
    /// The field cannot be set in this context (e.g. the segment time of a line's first stop).
    NotAllowed,
}

impl Violation {
    /// Stable machine-readable code (also the i18n catalogue key).
    #[must_use]
    pub const fn code(&self) -> &'static str {
        match self {
            Self::Required => "required",
            Self::InvalidFormat => "invalid_format",
            Self::InvalidEmail => "invalid_email",
            Self::InvalidPhone => "invalid_phone",
            Self::TooShort { .. } => "too_short",
            Self::TooLong { .. } => "too_long",
            Self::OutOfRange { .. } => "out_of_range",
            Self::InvalidChoice { .. } => "invalid_choice",
            Self::PasswordTooShort { .. } => "password_too_short",
            Self::PasswordTooLong { .. } => "password_too_long",
            Self::PasswordTooCommon => "password_too_common",
            Self::PasswordEntirelyNumeric => "password_entirely_numeric",
            Self::PasswordTooSimilar => "password_too_similar",
            Self::PasswordReused => "password_reused",
            Self::Incorrect => "incorrect",
            Self::UnknownField => "unknown_field",
            Self::InvalidUpload => "invalid_upload",
            Self::Duplicate => "duplicate",
            Self::UnknownReference => "unknown_reference",
            Self::MustBeAfter { .. } => "must_be_after",
            Self::NotAllowed => "not_allowed",
        }
    }
}

/// A violation attached to the (dot/bracket) path of the offending field.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FieldViolation {
    pub field: Cow<'static, str>,
    pub violation: Violation,
}

/// A non-empty collection of field violations.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Violations(Vec<FieldViolation>);

impl Violations {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn single(field: impl Into<Cow<'static, str>>, violation: Violation) -> Self {
        let mut v = Self::new();
        v.push(field, violation);
        v
    }

    pub fn push(&mut self, field: impl Into<Cow<'static, str>>, violation: Violation) {
        self.0.push(FieldViolation { field: field.into(), violation });
    }

    /// Records the error of `result` under `field` and returns the value if valid.
    pub fn check<T>(&mut self, field: &'static str, result: Result<T, Violation>) -> Option<T> {
        match result {
            Ok(value) => Some(value),
            Err(violation) => {
                self.push(field, violation);
                None
            }
        }
    }

    pub fn extend(&mut self, other: Self) {
        self.0.extend(other.0);
    }

    /// Records the violations of a nested value under `prefix`: `lat` becomes `location.lat`,
    /// `[2]` becomes `features[2]` and the empty field (the value itself) becomes `prefix`.
    /// An empty prefix keeps the fields as they are.
    pub fn extend_nested(&mut self, prefix: &str, other: Self) {
        for FieldViolation { field, violation } in other.0 {
            let field = if prefix.is_empty() {
                field.into_owned()
            } else if field.is_empty() {
                prefix.to_owned()
            } else if field.starts_with('[') {
                format!("{prefix}{field}")
            } else {
                format!("{prefix}.{field}")
            };
            self.push(field, violation);
        }
    }

    /// Like [`Self::check`] for a value validated as a whole (several fields), nested under
    /// `prefix`.
    pub fn check_nested<T>(&mut self, prefix: &str, result: Result<T, Self>) -> Option<T> {
        match result {
            Ok(value) => Some(value),
            Err(violations) => {
                self.extend_nested(prefix, violations);
                None
            }
        }
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn iter(&self) -> impl Iterator<Item = &FieldViolation> {
        self.0.iter()
    }

    /// `Ok(())` when no violation was recorded.
    pub fn into_result(self) -> Result<(), DomainError> {
        if self.is_empty() { Ok(()) } else { Err(DomainError::Validation(self)) }
    }
}

impl IntoIterator for Violations {
    type Item = FieldViolation;
    type IntoIter = std::vec::IntoIter<FieldViolation>;

    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}

/// Why an action was denied by the authorization policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DenyReason {
    /// The actor's role does not grant the required permission.
    MissingPermission,
    /// The actor does not own the target resource.
    NotOwner,
    /// The resource or actor is not in a state that allows the action.
    InvalidState,
    /// The action needs an authenticated actor.
    AuthenticationRequired,
}

/// Kinds of uniqueness/state conflicts surfaced to clients.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConflictKind {
    EmailTaken,
    PhoneTaken,
    AlreadyExists,
    StaleState,
    /// The upload was attached by a concurrent request.
    UploadAlreadyUsed,
    /// The stop cannot be deleted while a line serves it.
    StopInUse,
    /// Another line already has this code.
    LineCodeTaken,
    /// The line cannot be deleted while buses are assigned to it.
    LineInUse,
    /// The stop is already on the line (a stop appears at most once per line).
    StopAlreadyOnLine,
    /// The schedule overlaps an active schedule of the same line on the same day.
    ScheduleOverlap,
    /// The caller already has a driver profile (one per account).
    DriverProfileExists,
    /// Another driver profile has this national identity number.
    IdCardTaken,
    /// Another driver profile has this driving licence number.
    LicenseTaken,
    /// The driver state machine does not allow this action from the current status.
    InvalidTransition,
}

impl ConflictKind {
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::EmailTaken => "email_taken",
            Self::PhoneTaken => "phone_taken",
            Self::AlreadyExists => "already_exists",
            Self::StaleState => "stale_state",
            Self::UploadAlreadyUsed => "upload_already_used",
            Self::StopInUse => "stop_in_use",
            Self::LineCodeTaken => "line_code_taken",
            Self::LineInUse => "line_in_use",
            Self::StopAlreadyOnLine => "stop_already_on_line",
            Self::ScheduleOverlap => "schedule_overlap",
            Self::DriverProfileExists => "driver_profile_exists",
            Self::IdCardTaken => "id_card_taken",
            Self::LicenseTaken => "license_taken",
            Self::InvalidTransition => "invalid_transition",
        }
    }
}

/// Errors raised by domain rules. Infrastructure failures never appear here.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum DomainError {
    #[error("validation failed ({} violation(s))", .0.len())]
    Validation(Violations),
    #[error("{0} not found")]
    NotFound(&'static str),
    #[error("conflict: {}", .0.code())]
    Conflict(ConflictKind),
    #[error("action denied: {0:?}")]
    Forbidden(DenyReason),
    #[error("invalid state transition: {0}")]
    InvalidState(&'static str),
}

impl From<Violations> for DomainError {
    fn from(v: Violations) -> Self {
        Self::Validation(v)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nested_violations_get_prefixed_paths() {
        let mut inner = Violations::new();
        inner.push("", Violation::Required);
        inner.push("lat", Violation::InvalidFormat);
        inner.push("[2]", Violation::Duplicate);
        let mut outer = Violations::new();
        outer.extend_nested("location", inner.clone());
        outer.extend_nested("", inner);
        let fields: Vec<_> = outer.iter().map(|f| f.field.to_string()).collect();
        assert_eq!(fields, ["location", "location.lat", "location[2]", "", "lat", "[2]"]);
        let mut v = Violations::new();
        assert_eq!(v.check_nested("x", Ok::<_, Violations>(1)), Some(1));
        let nested = Err(Violations::single("y", Violation::NotAllowed));
        assert_eq!(v.check_nested::<u8>("x", nested), None);
        assert_eq!(v.iter().next().map(|f| f.field.as_ref()), Some("x.y"));
    }

    #[test]
    fn new_codes_are_stable() {
        assert_eq!(Violation::MustBeAfter { field: "start_time".into() }.code(), "must_be_after");
        assert_eq!(Violation::UnknownReference.code(), "unknown_reference");
        assert_eq!(ConflictKind::ScheduleOverlap.code(), "schedule_overlap");
        assert_eq!(ConflictKind::StopAlreadyOnLine.code(), "stop_already_on_line");
        assert_eq!(ConflictKind::DriverProfileExists.code(), "driver_profile_exists");
        assert_eq!(ConflictKind::IdCardTaken.code(), "id_card_taken");
        assert_eq!(ConflictKind::LicenseTaken.code(), "license_taken");
        assert_eq!(ConflictKind::InvalidTransition.code(), "invalid_transition");
    }
}
