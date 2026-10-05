//! Supported languages and `Accept-Language` negotiation.

use serde::{Deserialize, Serialize};

/// A language supported for user-facing text (errors, notifications).
///
/// French is the default, as in the legacy application.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Lang {
    #[default]
    Fr,
    Ar,
    En,
}

impl Lang {
    pub const ALL: [Self; 3] = [Self::Fr, Self::Ar, Self::En];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Fr => "fr",
            Self::Ar => "ar",
            Self::En => "en",
        }
    }

    /// Parses a language code (`fr`, `ar`, `en`), ignoring region subtags and case.
    #[must_use]
    pub fn from_code(code: &str) -> Option<Self> {
        let primary = code.split(['-', '_']).next()?.trim();
        if primary.eq_ignore_ascii_case("fr") {
            Some(Self::Fr)
        } else if primary.eq_ignore_ascii_case("ar") {
            Some(Self::Ar)
        } else if primary.eq_ignore_ascii_case("en") {
            Some(Self::En)
        } else {
            None
        }
    }

    /// Picks the best supported language from an `Accept-Language` header value
    /// (RFC 9110 §12.5.4). Returns `None` when nothing acceptable is supported.
    #[must_use]
    pub fn negotiate(accept_language: &str) -> Option<Self> {
        let mut best: Option<(u16, usize, Self)> = None;
        for (position, item) in accept_language.split(',').take(16).enumerate() {
            let mut parts = item.split(';');
            let Some(tag) = parts.next().map(str::trim) else {
                continue;
            };
            let quality = parts
                .find_map(|p| p.trim().strip_prefix("q="))
                .map_or(Some(1000), parse_qvalue);
            let (Some(quality), Some(lang)) = (quality, Self::from_code(tag)) else {
                continue;
            };
            if quality == 0 {
                continue;
            }
            // Higher quality wins; on ties the earlier entry wins.
            let better = best.is_none_or(|(q, pos, _)| quality > q || (quality == q && position < pos));
            if better {
                best = Some((quality, position, lang));
            }
        }
        best.map(|(_, _, lang)| lang)
    }
}

impl std::fmt::Display for Lang {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Parses an RFC 9110 qvalue into thousandths (0..=1000).
fn parse_qvalue(raw: &str) -> Option<u16> {
    let raw = raw.trim();
    let (int, frac) = raw.split_once('.').unwrap_or((raw, ""));
    if frac.len() > 3 || !frac.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let mut thousandths: u16 = 0;
    for (i, digit) in frac.bytes().enumerate() {
        let scale = [100, 10, 1][i];
        thousandths += u16::from(digit - b'0') * scale;
    }
    match int {
        "0" => Some(thousandths),
        "1" if thousandths == 0 => Some(1000),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn negotiates_by_quality() {
        assert_eq!(Lang::negotiate("en;q=0.5, ar;q=0.9"), Some(Lang::Ar));
        assert_eq!(Lang::negotiate("de, en-GB;q=0.8"), Some(Lang::En));
        assert_eq!(Lang::negotiate("fr-DZ"), Some(Lang::Fr));
        assert_eq!(Lang::negotiate("de, it"), None);
        assert_eq!(Lang::negotiate("en;q=0, ar;q=0.1"), Some(Lang::Ar));
        assert_eq!(Lang::negotiate("en;q=abc"), None);
    }

    #[test]
    fn ties_prefer_first() {
        assert_eq!(Lang::negotiate("ar, en"), Some(Lang::Ar));
    }
}
