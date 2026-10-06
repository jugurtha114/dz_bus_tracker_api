//! Keyset (cursor) pagination.
//!
//! Lists are ordered by `(created_at DESC, id DESC)`; the cursor is the position of the last
//! item of the previous page. Cursors are opaque base64url strings for clients.

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use chrono::{DateTime, Utc};
use dz_domain::Violation;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppError;

/// Largest page a client may request.
pub const MAX_LIMIT: u32 = 100;
/// Page size when the client does not ask for one.
pub const DEFAULT_LIMIT: u32 = 20;

/// Position after which the next page starts.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Cursor {
    #[serde(rename = "t")]
    pub created_at: DateTime<Utc>,
    #[serde(rename = "i")]
    pub id: Uuid,
}

impl Cursor {
    #[must_use]
    pub fn encode(&self) -> String {
        // Serializing two primitive fields cannot fail.
        let json = serde_json::to_vec(self).unwrap_or_default();
        URL_SAFE_NO_PAD.encode(json)
    }

    /// Decodes a client-supplied cursor; any tampering yields a validation error.
    pub fn decode(raw: &str) -> Result<Self, AppError> {
        let invalid = || AppError::invalid("cursor", Violation::InvalidFormat);
        if raw.len() > 256 {
            return Err(invalid());
        }
        let bytes = URL_SAFE_NO_PAD.decode(raw).map_err(|_| invalid())?;
        serde_json::from_slice(&bytes).map_err(|_| invalid())
    }
}

/// A validated page request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PageRequest {
    pub limit: u32,
    pub after: Option<Cursor>,
}

impl PageRequest {
    /// Builds a request from raw query parameters.
    pub fn parse(limit: Option<u32>, cursor: Option<&str>) -> Result<Self, AppError> {
        let limit = limit.unwrap_or(DEFAULT_LIMIT);
        if !(1..=MAX_LIMIT).contains(&limit) {
            return Err(AppError::invalid(
                "limit",
                Violation::OutOfRange { min: 1, max: i64::from(MAX_LIMIT) },
            ));
        }
        let after = cursor.filter(|c| !c.is_empty()).map(Cursor::decode).transpose()?;
        Ok(Self { limit, after })
    }

    /// Number of rows to fetch: one extra row tells whether another page exists.
    #[must_use]
    pub fn fetch_limit(&self) -> i64 {
        i64::from(self.limit) + 1
    }
}

impl Default for PageRequest {
    fn default() -> Self {
        Self { limit: DEFAULT_LIMIT, after: None }
    }
}

/// One page of results.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Page<T> {
    pub items: Vec<T>,
    pub next_cursor: Option<Cursor>,
}

impl<T> Page<T> {
    /// Trims the look-ahead row fetched with [`PageRequest::fetch_limit`] and derives the cursor.
    pub fn from_rows(mut rows: Vec<T>, request: PageRequest, key: impl Fn(&T) -> Cursor) -> Self {
        let limit = request.limit as usize;
        let has_more = rows.len() > limit;
        rows.truncate(limit);
        let next_cursor = if has_more { rows.last().map(key) } else { None };
        Self { items: rows, next_cursor }
    }

    pub fn map<U>(self, f: impl FnMut(T) -> U) -> Page<U> {
        Page { items: self.items.into_iter().map(f).collect(), next_cursor: self.next_cursor }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cursor_round_trips_and_rejects_garbage() {
        let cursor = Cursor { created_at: Utc::now(), id: Uuid::now_v7() };
        assert_eq!(Cursor::decode(&cursor.encode()).unwrap(), cursor);
        assert!(Cursor::decode("not-base64!").is_err());
        assert!(Cursor::decode(&URL_SAFE_NO_PAD.encode(b"{}")).is_err());
    }

    #[test]
    fn limits_are_bounded() {
        assert_eq!(PageRequest::parse(None, None).unwrap().limit, DEFAULT_LIMIT);
        assert!(PageRequest::parse(Some(0), None).is_err());
        assert!(PageRequest::parse(Some(101), None).is_err());
        assert_eq!(PageRequest::parse(Some(100), Some("")).unwrap().after, None);
    }

    #[test]
    fn pages_detect_more_rows() {
        let request = PageRequest { limit: 2, after: None };
        let ids: Vec<Uuid> = (0..3).map(|_| Uuid::now_v7()).collect();
        let now = Utc::now();
        let page = Page::from_rows(ids.clone(), request, |id| Cursor { created_at: now, id: *id });
        assert_eq!(page.items.len(), 2);
        assert_eq!(page.next_cursor.map(|c| c.id), Some(ids[1]));
        let last = Page::from_rows(ids[..2].to_vec(), request, |id| Cursor { created_at: now, id: *id });
        assert_eq!(last.next_cursor, None);
    }
}
