//! Password strength policy (NIST SP 800-63B style: length + blocklist + context checks,
//! no arbitrary composition rules).

use crate::error::Violation;

/// The most common passwords seen in breach corpora, plus local (French/Algerian) favourites.
/// Comparison is case-insensitive.
const COMMON_PASSWORDS: &[&str] = &[
    "123456", "password", "12345678", "qwerty", "123456789", "12345", "1234", "111111",
    "1234567", "dragon", "123123", "baseball", "abc123", "football", "monkey", "letmein",
    "696969", "shadow", "master", "666666", "qwertyuiop", "123321", "mustang", "1234567890",
    "michael", "654321", "superman", "1qaz2wsx", "7777777", "121212", "000000", "qazwsx",
    "123qwe", "killer", "trustno1", "jordan", "jennifer", "zxcvbnm", "asdfgh", "hunter",
    "buster", "soccer", "harley", "batman", "andrew", "tigger", "sunshine", "iloveyou",
    "2000", "charlie", "robert", "thomas", "hockey", "ranger", "daniel", "starwars",
    "klaster", "112233", "george", "computer", "michelle", "jessica", "pepper", "1111",
    "zxcvbn", "555555", "11111111", "131313", "freedom", "777777", "pass", "maggie",
    "159753", "aaaaaa", "ginger", "princess", "joshua", "cheese", "amanda", "summer",
    "love", "ashley", "nicole", "chelsea", "biteme", "matthew", "access", "yankees",
    "987654321", "dallas", "austin", "thunder", "taylor", "matrix", "password1", "password123",
    "welcome", "admin", "admin123", "administrator", "root", "toor", "changeme", "passw0rd",
    "p@ssw0rd", "qwerty123", "1q2w3e4r", "1q2w3e4r5t", "q1w2e3r4", "azerty", "azertyuiop",
    "azerty123", "motdepasse", "motdepasse123", "soleil", "bonjour", "doudou", "loulou",
    "chouchou", "marseille", "nicolas", "julien", "algerie", "algeria", "dzair", "alger",
    "oran", "constantine", "annaba", "setif", "blida", "bejaia", "tizi", "kabylie",
    "mouloudia", "mca1921", "jsk", "usma", "bismillah", "allahakbar", "mohamed", "mohammed",
    "amine", "yacine", "karim", "samir", "nadia", "fatima", "sarah", "lyna",
    "dzbus", "dzbustracker", "bustracker", "autobus", "chauffeur", "passager", "etusa",
    "0123456789", "9876543210", "abcdef", "abcdefgh", "abcd1234", "aaaaaaaa", "qwerty1",
];

/// Configurable password policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PasswordPolicy {
    pub min_length: usize,
    pub max_length: usize,
}

impl Default for PasswordPolicy {
    fn default() -> Self {
        Self { min_length: 12, max_length: 128 }
    }
}

/// Context the password must not resemble (user attribute similarity).
#[derive(Debug, Clone, Copy, Default)]
pub struct PasswordContext<'a> {
    pub email_local_part: Option<&'a str>,
    pub first_name: Option<&'a str>,
    pub last_name: Option<&'a str>,
}

impl PasswordPolicy {
    /// Validates a candidate password, returning the first violated rule.
    pub fn validate(&self, password: &str, ctx: PasswordContext<'_>) -> Result<(), Violation> {
        let chars = password.chars().count();
        if chars < self.min_length {
            return Err(Violation::PasswordTooShort { min: self.min_length as u64 });
        }
        if chars > self.max_length {
            return Err(Violation::PasswordTooLong { max: self.max_length as u64 });
        }
        if password.chars().all(|c| c.is_ascii_digit()) {
            return Err(Violation::PasswordEntirelyNumeric);
        }
        let lowered = password.to_lowercase();
        if is_common(&lowered) {
            return Err(Violation::PasswordTooCommon);
        }
        let attributes = [ctx.email_local_part, ctx.first_name, ctx.last_name];
        if attributes.into_iter().flatten().any(|attr| is_similar(&lowered, attr)) {
            return Err(Violation::PasswordTooSimilar);
        }
        Ok(())
    }
}

/// A password is "common" when it is in the blocklist, is a blocklisted word followed by
/// digits/symbols, or is a single repeated character.
fn is_common(lowered: &str) -> bool {
    let stripped = lowered.trim_end_matches(|c: char| c.is_ascii_digit() || "!@#$%&*?._-".contains(c));
    let mut chars = lowered.chars();
    let first = chars.next();
    let single_char = first.is_some_and(|f| chars.all(|c| c == f));
    single_char
        || COMMON_PASSWORDS.contains(&lowered)
        || (stripped.len() >= 4 && COMMON_PASSWORDS.contains(&stripped))
}

/// Similar when the attribute (≥ 4 chars) is contained in the password or vice versa.
fn is_similar(lowered_password: &str, attribute: &str) -> bool {
    let attr = attribute.trim().to_lowercase();
    if attr.chars().count() < 4 {
        return false;
    }
    lowered_password.contains(&attr) || attr.contains(lowered_password)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> PasswordPolicy {
        PasswordPolicy::default()
    }

    #[test]
    fn accepts_a_strong_passphrase() {
        assert_eq!(policy().validate("correct horse battery", PasswordContext::default()), Ok(()));
    }

    #[test]
    fn enforces_length_bounds() {
        assert_eq!(
            policy().validate("short", PasswordContext::default()),
            Err(Violation::PasswordTooShort { min: 12 })
        );
        assert_eq!(
            policy().validate(&"x".repeat(129), PasswordContext::default()),
            Err(Violation::PasswordTooLong { max: 128 })
        );
    }

    #[test]
    fn rejects_numeric_common_and_repeated() {
        let ctx = PasswordContext::default();
        assert_eq!(policy().validate("123456789012", ctx), Err(Violation::PasswordEntirelyNumeric));
        assert_eq!(policy().validate("Motdepasse123!", ctx), Err(Violation::PasswordTooCommon));
        assert_eq!(policy().validate("zzzzzzzzzzzzzz", ctx), Err(Violation::PasswordTooCommon));
    }

    #[test]
    fn rejects_passwords_similar_to_user_attributes() {
        let ctx = PasswordContext {
            email_local_part: Some("benali.karim"),
            first_name: Some("Karim"),
            last_name: Some("Ben"),
        };
        assert_eq!(policy().validate("benali.karim2026", ctx), Err(Violation::PasswordTooSimilar));
        assert_eq!(policy().validate("ilove-karim-buses", ctx), Err(Violation::PasswordTooSimilar));
        // Short attributes ("Ben") are ignored to avoid false positives.
        assert_eq!(policy().validate("bentonite-quarry", ctx), Ok(()));
    }
}
