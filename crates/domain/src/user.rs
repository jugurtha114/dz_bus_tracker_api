//! User accounts: roles and validated value objects.

use std::fmt;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::error::Violation;
use crate::ids::UserId;
use crate::lang::Lang;

/// Role of an actor. `Service` is reserved for machine-to-machine API keys and can never be
/// assigned to a user account.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Admin,
    Driver,
    Passenger,
    Service,
}

impl Role {
    pub const USER_ROLES: [Self; 3] = [Self::Admin, Self::Driver, Self::Passenger];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Admin => "admin",
            Self::Driver => "driver",
            Self::Passenger => "passenger",
            Self::Service => "service",
        }
    }

    #[must_use]
    pub fn parse(raw: &str) -> Option<Self> {
        match raw {
            "admin" => Some(Self::Admin),
            "driver" => Some(Self::Driver),
            "passenger" => Some(Self::Passenger),
            "service" => Some(Self::Service),
            _ => None,
        }
    }

    /// Parses a role that may be stored on a user account.
    pub fn parse_user_role(raw: &str) -> Result<Self, Violation> {
        match Self::parse(raw) {
            Some(role) if role.is_user_role() => Ok(role),
            _ => Err(Violation::InvalidChoice {
                allowed: Self::USER_ROLES.iter().map(|r| r.as_str().into()).collect(),
            }),
        }
    }

    #[must_use]
    pub const fn is_user_role(self) -> bool {
        !matches!(self, Self::Service)
    }
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// A normalized e-mail address (trimmed, lower-cased, syntactically valid).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize)]
#[serde(transparent)]
pub struct Email(String);

impl Email {
    pub const MAX_LEN: usize = 254;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim().to_lowercase();
        if value.is_empty() {
            return Err(Violation::Required);
        }
        if value.len() > Self::MAX_LEN {
            return Err(Violation::TooLong { max: Self::MAX_LEN as u64 });
        }
        let Some((local, domain)) = value.split_once('@') else {
            return Err(Violation::InvalidEmail);
        };
        let local_ok = !local.is_empty()
            && local.len() <= 64
            && !local.starts_with('.')
            && !local.ends_with('.')
            && !local.contains("..")
            && local
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || "!#$%&'*+-/=?^_`{|}~.".contains(c));
        let labels: Vec<&str> = domain.split('.').collect();
        let domain_ok = labels.len() >= 2
            && domain.len() <= 253
            && labels.iter().all(|l| {
                !l.is_empty()
                    && l.len() <= 63
                    && !l.starts_with('-')
                    && !l.ends_with('-')
                    && l.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
            })
            && labels
                .last()
                .is_some_and(|tld| tld.len() >= 2 && tld.chars().all(|c| c.is_ascii_alphabetic()));
        if local_ok && domain_ok { Ok(Self(value)) } else { Err(Violation::InvalidEmail) }
    }

    /// Wraps a value that was already validated (e.g. loaded from the database).
    #[must_use]
    pub fn from_trusted(value: String) -> Self {
        Self(value)
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    /// The part before `@`, used by the password-similarity check.
    #[must_use]
    pub fn local_part(&self) -> &str {
        self.0.split('@').next().unwrap_or_default()
    }
}

impl fmt::Display for Email {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// An Algerian mobile number, normalized to E.164 (`+2135XXXXXXXX`, `+2136…`, `+2137…`).
///
/// Accepted inputs: `+213XXXXXXXXX`, `00213XXXXXXXXX`, `0XXXXXXXXX` (spaces, dots and dashes
/// are ignored), matching the legacy validator.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize)]
#[serde(transparent)]
pub struct PhoneNumber(String);

impl PhoneNumber {
    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let compact: String = raw.chars().filter(|c| !matches!(c, ' ' | '.' | '-')).collect();
        if compact.is_empty() {
            return Err(Violation::Required);
        }
        let national = compact
            .strip_prefix("+213")
            .or_else(|| compact.strip_prefix("00213"))
            .or_else(|| compact.strip_prefix('0'))
            .ok_or(Violation::InvalidPhone)?;
        let valid = national.len() == 9
            && national.chars().all(|c| c.is_ascii_digit())
            && matches!(national.as_bytes()[0], b'5' | b'6' | b'7');
        if valid { Ok(Self(format!("+213{national}"))) } else { Err(Violation::InvalidPhone) }
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

/// A first or last name: trimmed, at most 150 characters, no control characters.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize)]
#[serde(transparent)]
pub struct PersonName(String);

impl PersonName {
    pub const MAX_CHARS: usize = 150;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim();
        if value.chars().count() > Self::MAX_CHARS {
            return Err(Violation::TooLong { max: Self::MAX_CHARS as u64 });
        }
        if value.chars().any(char::is_control) {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value.to_owned()))
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

/// Free-form profile biography (at most 1000 characters).
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize)]
#[serde(transparent)]
pub struct Bio(String);

impl Bio {
    pub const MAX_CHARS: usize = 1000;

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim();
        if value.chars().count() > Self::MAX_CHARS {
            return Err(Violation::TooLong { max: Self::MAX_CHARS as u64 });
        }
        if value.chars().any(|c| c.is_control() && c != '\n' && c != '\r' && c != '\t') {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value.to_owned()))
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

/// A user account as seen by use-cases (never carries the password hash).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct User {
    pub id: UserId,
    pub email: Email,
    pub role: Role,
    pub first_name: PersonName,
    pub last_name: PersonName,
    pub phone_number: Option<PhoneNumber>,
    pub is_active: bool,
    pub email_verified_at: Option<DateTime<Utc>>,
    pub last_login_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl User {
    #[must_use]
    pub fn full_name(&self) -> String {
        format!("{} {}", self.first_name.as_str(), self.last_name.as_str()).trim().to_owned()
    }
}

/// Per-user preferences.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Profile {
    pub user_id: UserId,
    pub avatar_key: Option<String>,
    pub bio: Bio,
    pub language: Lang,
    pub push_notifications_enabled: bool,
    pub email_notifications_enabled: bool,
    pub sms_notifications_enabled: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn email_is_normalized() {
        let email = Email::parse("  John.Doe+bus@Example.DZ ").unwrap();
        assert_eq!(email.as_str(), "john.doe+bus@example.dz");
        assert_eq!(email.local_part(), "john.doe+bus");
    }

    #[test]
    fn rejects_bad_emails() {
        for bad in ["", "plain", "a@b", "a@@b.dz", ".a@b.dz", "a..b@c.dz", "a@-b.dz", "a@b.d1", "a b@c.dz"] {
            assert!(Email::parse(bad).is_err(), "{bad} should be rejected");
        }
    }

    #[test]
    fn phone_numbers_normalize_to_e164() {
        for raw in ["0555123456", "+213555123456", "00213555123456", "0555 12 34 56", "0555-12-34-56"] {
            assert_eq!(PhoneNumber::parse(raw).unwrap().as_str(), "+213555123456", "{raw}");
        }
    }

    #[test]
    fn rejects_non_mobile_or_malformed_phones() {
        for bad in ["0215123456", "055512345", "05551234567", "+33612345678", "abc"] {
            assert_eq!(PhoneNumber::parse(bad), Err(Violation::InvalidPhone), "{bad}");
        }
        assert_eq!(PhoneNumber::parse(""), Err(Violation::Required));
    }

    #[test]
    fn names_are_bounded() {
        assert!(PersonName::parse(&"a".repeat(150)).is_ok());
        assert_eq!(PersonName::parse(&"a".repeat(151)), Err(Violation::TooLong { max: 150 }));
        assert_eq!(PersonName::parse("bad\u{0}name"), Err(Violation::InvalidFormat));
        assert_eq!(PersonName::parse("  Amine ").unwrap().as_str(), "Amine");
    }

    #[test]
    fn service_role_is_not_assignable_to_users() {
        assert!(Role::parse_user_role("service").is_err());
        assert!(Role::parse_user_role("root").is_err());
        assert_eq!(Role::parse_user_role("driver"), Ok(Role::Driver));
    }
}
