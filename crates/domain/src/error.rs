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
}

impl ConflictKind {
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::EmailTaken => "email_taken",
            Self::PhoneTaken => "phone_taken",
            Self::AlreadyExists => "already_exists",
            Self::StaleState => "stale_state",
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
