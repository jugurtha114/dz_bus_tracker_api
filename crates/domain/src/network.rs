//! The transport network: stops, lines, the ordered stops of a line and line schedules, with
//! the value objects that validate their fields.

use std::collections::HashSet;
use std::fmt;

use chrono::{DateTime, Utc};

use crate::error::{Violation, Violations};
use crate::geo::GeoPoint;
use crate::ids::{LineId, ScheduleId, StopId};

macro_rules! text_value {
    ($(#[$meta:meta])* $name:ident, max = $max:literal) => {
        $(#[$meta])*
        #[derive(Debug, Clone, PartialEq, Eq, Hash)]
        pub struct $name(String);

        impl $name {
            pub const MAX_CHARS: usize = $max;

            /// Trims the value; it must be 1 to `MAX_CHARS` characters long.
            pub fn parse(raw: &str) -> Result<Self, Violation> {
                let value = raw.trim();
                if value.is_empty() {
                    return Err(Violation::Required);
                }
                check_length(value, Self::MAX_CHARS).map(|v| Self(v.to_owned()))
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
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str(&self.0)
            }
        }
    };
}

text_value!(
    /// Name of a stop (1–100 characters).
    StopName,
    max = 100
);

text_value!(
    /// Name of a line (1–100 characters), e.g. `Place des Martyrs – Bab Ezzouar`.
    LineName,
    max = 100
);

fn check_length(value: &str, max: usize) -> Result<&str, Violation> {
    if value.chars().count() > max {
        Err(Violation::TooLong { max: max as u64 })
    } else {
        Ok(value)
    }
}

/// Validates an optional free-text field (address, wilaya, description…): trimmed, at most
/// `max` characters, empty allowed (an empty value clears the field).
pub fn optional_text(raw: &str, max: usize) -> Result<String, Violation> {
    check_length(raw.trim(), max).map(str::to_owned)
}

/// Longest stop address.
pub const ADDRESS_MAX_CHARS: usize = 255;
/// Longest wilaya or commune name.
pub const AREA_MAX_CHARS: usize = 100;
/// Longest stop or line description.
pub const DESCRIPTION_MAX_CHARS: usize = 2000;

/// The public code of a line: 1–20 characters `[A-Za-z0-9-]`, stored upper-case (so `l1` and
/// `L1` are the same code). Immutable once the line exists.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LineCode(String);

impl LineCode {
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

impl fmt::Display for LineCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// A colour `#RRGGBB`, stored upper-case.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct HexColor(String);

impl HexColor {
    /// Colour of lines created without one.
    pub const DEFAULT: &'static str = "#000000";

    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let value = raw.trim();
        let hex = value.strip_prefix('#').ok_or(Violation::InvalidFormat)?;
        if hex.len() != 6 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(Violation::InvalidFormat);
        }
        Ok(Self(value.to_ascii_uppercase()))
    }

    #[must_use]
    pub fn default_color() -> Self {
        Self(Self::DEFAULT.to_owned())
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

/// Day of the week, ISO 8601: 1 = Monday … 7 = Sunday.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Weekday(u8);

impl Weekday {
    pub fn parse(raw: i64) -> Result<Self, Violation> {
        match u8::try_from(raw) {
            Ok(day @ 1..=7) => Ok(Self(day)),
            _ => Err(Violation::OutOfRange { min: 1, max: 7 }),
        }
    }

    #[must_use]
    pub const fn iso(self) -> u8 {
        self.0
    }
}

/// A time of day with minute precision, `00:00` to `23:59`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TimeOfDay(u16);

impl TimeOfDay {
    /// Parses `HH:MM` (24-hour clock, two digits each).
    pub fn parse(raw: &str) -> Result<Self, Violation> {
        let bytes = raw.as_bytes();
        let digits = |range: std::ops::Range<usize>| -> Option<u16> {
            let part = raw.get(range)?;
            part.bytes().all(|b| b.is_ascii_digit()).then(|| part.parse().ok())?
        };
        if bytes.len() != 5 || bytes[2] != b':' {
            return Err(Violation::InvalidFormat);
        }
        match (digits(0..2), digits(3..5)) {
            (Some(h), Some(m)) if h < 24 && m < 60 => Ok(Self(h * 60 + m)),
            _ => Err(Violation::InvalidFormat),
        }
    }

    /// Minutes since midnight; `None` from 24:00 on.
    #[must_use]
    pub const fn from_minutes(minutes: u16) -> Option<Self> {
        if minutes < 24 * 60 { Some(Self(minutes)) } else { None }
    }

    #[must_use]
    pub const fn minutes(self) -> u16 {
        self.0
    }

    #[must_use]
    pub const fn hour(self) -> u16 {
        self.0 / 60
    }

    #[must_use]
    pub const fn minute(self) -> u16 {
        self.0 % 60
    }
}

impl fmt::Display for TimeOfDay {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:02}:{:02}", self.hour(), self.minute())
    }
}

/// A service window `[start, end)` within one day (`start < end`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct TimeWindow {
    start: TimeOfDay,
    end: TimeOfDay,
}

impl TimeWindow {
    /// Fails with [`Violation::MustBeAfter`] (to report on the end) unless `start < end`.
    pub fn new(start: TimeOfDay, end: TimeOfDay) -> Result<Self, Violation> {
        if start < end {
            Ok(Self { start, end })
        } else {
            Err(Violation::MustBeAfter { field: "start_time".into() })
        }
    }

    #[must_use]
    pub const fn start(self) -> TimeOfDay {
        self.start
    }

    #[must_use]
    pub const fn end(self) -> TimeOfDay {
        self.end
    }

    /// Whether the half-open windows share a minute (adjacent windows do not overlap), as the
    /// `timerange && timerange` of the `schedules_no_overlap` constraint.
    #[must_use]
    pub fn overlaps(self, other: Self) -> bool {
        self.start < other.end && other.start < self.end
    }
}

/// Minutes between two departures, 1 to 1440.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Frequency(u16);

impl Frequency {
    pub const MAX_MINUTES: u16 = 1440;

    pub fn parse(raw: i64) -> Result<Self, Violation> {
        match u16::try_from(raw) {
            Ok(minutes @ 1..=Self::MAX_MINUTES) => Ok(Self(minutes)),
            _ => Err(Violation::OutOfRange { min: 1, max: i64::from(Self::MAX_MINUTES) }),
        }
    }

    #[must_use]
    pub const fn minutes(self) -> u16 {
        self.0
    }
}

/// A fare in Algerian dinars (whole DZD, `>= 0`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Fare(u32);

impl Fare {
    /// The column is a signed 32-bit integer.
    pub const MAX_DZD: u32 = i32::MAX as u32;

    pub fn parse(raw: i64) -> Result<Self, Violation> {
        match u32::try_from(raw) {
            Ok(dzd) if dzd <= Self::MAX_DZD => Ok(Self(dzd)),
            _ => Err(Violation::OutOfRange { min: 0, max: i64::from(Self::MAX_DZD) }),
        }
    }

    #[must_use]
    pub const fn dzd(self) -> u32 {
        self.0
    }
}

/// Travel time from the previous stop of a line, in seconds (0 to one day).
pub fn segment_time(raw: i64) -> Result<u32, Violation> {
    match u32::try_from(raw) {
        Ok(secs) if secs <= MAX_SEGMENT_TIME_S => Ok(secs),
        _ => Err(Violation::OutOfRange { min: 0, max: i64::from(MAX_SEGMENT_TIME_S) }),
    }
}

/// Longest travel time between two consecutive stops.
pub const MAX_SEGMENT_TIME_S: u32 = 86_400;

/// Short tags describing a stop (`shelter`, `bench`, `wheelchair_access`…): at most 20, each
/// 1–40 characters `[a-z0-9_]`, normalized to lower case, no repeats.
#[derive(Debug, Clone, Default, PartialEq, Eq, Hash)]
pub struct FeatureTags(Vec<String>);

impl FeatureTags {
    pub const MAX_TAGS: usize = 20;
    pub const MAX_CHARS: usize = 40;

    /// Violations are reported on the empty field (the count) and on `[i]`, to be nested
    /// under the field name.
    pub fn parse(raw: &[String]) -> Result<Self, Violations> {
        let mut v = Violations::new();
        if raw.len() > Self::MAX_TAGS {
            v.push("", Violation::OutOfRange { min: 0, max: Self::MAX_TAGS as i64 });
            return Err(v);
        }
        let mut seen = HashSet::new();
        let mut tags = Vec::with_capacity(raw.len());
        for (i, tag) in raw.iter().enumerate() {
            let tag = tag.trim().to_ascii_lowercase();
            let violation = if tag.is_empty() {
                Some(Violation::Required)
            } else if tag.chars().count() > Self::MAX_CHARS {
                Some(Violation::TooLong { max: Self::MAX_CHARS as u64 })
            } else if !tag.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
            {
                Some(Violation::InvalidFormat)
            } else if !seen.insert(tag.clone()) {
                Some(Violation::Duplicate)
            } else {
                None
            };
            match violation {
                Some(violation) => v.push(format!("[{i}]"), violation),
                None => tags.push(tag),
            }
        }
        if v.is_empty() { Ok(Self(tags)) } else { Err(v) }
    }

    #[must_use]
    pub fn from_trusted(tags: Vec<String>) -> Self {
        Self(tags)
    }

    #[must_use]
    pub fn as_slice(&self) -> &[String] {
        &self.0
    }

    #[must_use]
    pub fn into_vec(self) -> Vec<String> {
        self.0
    }
}

/// A bus stop.
#[derive(Debug, Clone, PartialEq)]
pub struct Stop {
    pub id: StopId,
    pub name: StopName,
    pub location: GeoPoint,
    pub address: String,
    pub wilaya: String,
    pub commune: String,
    pub description: String,
    pub features: FeatureTags,
    /// Inactive stops are hidden from the public catalogue; lines still pass them.
    pub is_active: bool,
    /// Object-storage key of the photo.
    pub photo_key: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// A bus line, with figures derived from its stops and route.
#[derive(Debug, Clone, PartialEq)]
pub struct Line {
    pub id: LineId,
    pub code: LineCode,
    pub name: LineName,
    pub description: String,
    pub color: HexColor,
    /// Headway announced for the line (minutes), when it runs at a fixed frequency.
    pub frequency_minutes: Option<Frequency>,
    pub fare_dza: Option<Fare>,
    pub is_active: bool,
    /// Whether a route geometry is set.
    pub has_route: bool,
    /// Number of stops on the line.
    pub stops_count: u32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Most stops a line can have.
pub const MAX_LINE_STOPS: usize = 200;

/// A stop at a position of a line (positions are 0-based and contiguous).
#[derive(Debug, Clone, PartialEq)]
pub struct LineStop {
    pub position: u16,
    pub stop: Stop,
    /// Straight-line distance from the previous stop (metres); `None` for the first stop.
    pub distance_from_previous_m: Option<f64>,
    /// Scheduled travel time from the previous stop (seconds), when known.
    pub time_from_previous_s: Option<u32>,
}

/// One entry of a line's ordered stop list, as requested.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StopSequenceEntry {
    pub stop_id: StopId,
    pub time_from_previous_s: Option<u32>,
}

/// A validated ordered stop list: at most [`MAX_LINE_STOPS`] stops, each at most once, and no
/// segment time on the first stop (it has no previous stop).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StopSequence(Vec<StopSequenceEntry>);

impl StopSequence {
    /// Violations are reported on the empty field (the count), `[i].stop_id` and
    /// `[i].time_from_previous_s`, to be nested under the field name.
    pub fn parse(entries: Vec<StopSequenceEntry>) -> Result<Self, Violations> {
        let mut v = Violations::new();
        if entries.len() > MAX_LINE_STOPS {
            v.push("", Violation::OutOfRange { min: 0, max: MAX_LINE_STOPS as i64 });
            return Err(v);
        }
        let mut seen = HashSet::new();
        for (i, entry) in entries.iter().enumerate() {
            if !seen.insert(entry.stop_id) {
                v.push(format!("[{i}].stop_id"), Violation::Duplicate);
            }
        }
        if entries.first().is_some_and(|first| first.time_from_previous_s.is_some()) {
            v.push("[0].time_from_previous_s", Violation::NotAllowed);
        }
        if v.is_empty() { Ok(Self(entries)) } else { Err(v) }
    }

    #[must_use]
    pub fn entries(&self) -> &[StopSequenceEntry] {
        &self.0
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.0.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

/// Where a stop inserted into a line of `len` stops goes: `requested` (0 to `len`) or, by
/// default, the end. Fails with the allowed range when the line is full or the position is
/// past the end.
pub fn insert_position(len: usize, requested: Option<i64>) -> Result<u16, Violation> {
    if len >= MAX_LINE_STOPS {
        return Err(Violation::OutOfRange { min: 0, max: MAX_LINE_STOPS as i64 - 1 });
    }
    let max = len as i64;
    match requested.unwrap_or(max) {
        position @ 0.. if position <= max => Ok(position as u16),
        _ => Err(Violation::OutOfRange { min: 0, max }),
    }
}

/// A weekly service window of a line: on `day`, between `window.start` and `window.end`, a bus
/// every `frequency` minutes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Schedule {
    pub id: ScheduleId,
    pub line_id: LineId,
    pub day: Weekday,
    pub window: TimeWindow,
    pub frequency: Frequency,
    /// Only active schedules are public and constrained not to overlap.
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Schedule {
    /// Whether two schedules would violate `schedules_no_overlap`: same line and day, both
    /// active, overlapping windows.
    #[must_use]
    pub fn conflicts_with(&self, other: &Self) -> bool {
        self.id != other.id
            && self.line_id == other.line_id
            && self.day == other.day
            && self.is_active
            && other.is_active
            && self.window.overlaps(other.window)
    }
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;

    use super::*;

    fn codes(v: &Violations) -> Vec<(String, &'static str)> {
        v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
    }

    #[test]
    fn line_codes_are_upper_cased_and_restricted() {
        assert_eq!(LineCode::parse(" l1-bis ").unwrap().as_str(), "L1-BIS");
        assert_eq!(LineCode::parse(""), Err(Violation::Required));
        assert_eq!(LineCode::parse("L 1"), Err(Violation::InvalidFormat));
        assert_eq!(LineCode::parse("L_1"), Err(Violation::InvalidFormat));
        assert_eq!(LineCode::parse("خط1"), Err(Violation::InvalidFormat));
        assert_eq!(LineCode::parse(&"A".repeat(21)), Err(Violation::TooLong { max: 20 }));
        assert!(LineCode::parse(&"9".repeat(20)).is_ok());
    }

    #[test]
    fn colors_are_hex_and_upper_cased() {
        assert_eq!(HexColor::parse("#1a2B3c").unwrap().as_str(), "#1A2B3C");
        for bad in ["1A2B3C", "#1A2B3", "#1A2B3CD", "#GGGGGG", "", "#"] {
            assert_eq!(HexColor::parse(bad), Err(Violation::InvalidFormat), "{bad}");
        }
        assert_eq!(HexColor::default_color().as_str(), "#000000");
    }

    #[test]
    fn names_and_texts_are_trimmed_and_bounded() {
        assert_eq!(StopName::parse("  Place des Martyrs ").unwrap().as_str(), "Place des Martyrs");
        assert_eq!(StopName::parse("   "), Err(Violation::Required));
        assert_eq!(StopName::parse(&"é".repeat(101)), Err(Violation::TooLong { max: 100 }));
        assert!(LineName::parse(&"ب".repeat(100)).is_ok());
        assert_eq!(optional_text("  ", 10), Ok(String::new()));
        assert_eq!(optional_text("12345678901", 10), Err(Violation::TooLong { max: 10 }));
    }

    #[test]
    fn numbers_are_range_checked() {
        assert_eq!(Weekday::parse(1).unwrap().iso(), 1);
        assert_eq!(Weekday::parse(7).unwrap().iso(), 7);
        for bad in [0, 8, -1, i64::MAX] {
            assert_eq!(Weekday::parse(bad), Err(Violation::OutOfRange { min: 1, max: 7 }));
        }
        assert_eq!(Frequency::parse(1440).unwrap().minutes(), 1440);
        assert!(Frequency::parse(0).is_err() && Frequency::parse(1441).is_err());
        assert_eq!(Fare::parse(0).unwrap().dzd(), 0);
        assert!(Fare::parse(-1).is_err() && Fare::parse(i64::from(u32::MAX)).is_err());
        assert_eq!(segment_time(86_400), Ok(86_400));
        assert!(segment_time(-1).is_err() && segment_time(86_401).is_err());
    }

    #[test]
    fn times_of_day_are_strict_hh_mm() {
        let t = TimeOfDay::parse("07:05").unwrap();
        assert_eq!((t.hour(), t.minute(), t.to_string()), (7, 5, "07:05".to_owned()));
        assert_eq!(TimeOfDay::parse("23:59").unwrap().minutes(), 23 * 60 + 59);
        for bad in ["24:00", "7:05", "07:5", "07-05", "07:60", "", "0705", "+7:05", "07:05:00"] {
            assert_eq!(TimeOfDay::parse(bad), Err(Violation::InvalidFormat), "{bad}");
        }
        assert_eq!(TimeOfDay::from_minutes(1440), None);
    }

    #[test]
    fn windows_need_start_before_end() {
        let at = |s| TimeOfDay::parse(s).unwrap();
        assert!(TimeWindow::new(at("06:00"), at("09:00")).is_ok());
        let err = TimeWindow::new(at("09:00"), at("09:00")).unwrap_err();
        assert_eq!(err, Violation::MustBeAfter { field: "start_time".into() });
        let morning = TimeWindow::new(at("06:00"), at("09:00")).unwrap();
        let day = TimeWindow::new(at("09:00"), at("17:00")).unwrap();
        let rush = TimeWindow::new(at("08:30"), at("10:00")).unwrap();
        assert!(!morning.overlaps(day), "adjacent windows do not overlap");
        assert!(morning.overlaps(rush) && rush.overlaps(day));
    }

    #[test]
    fn features_are_normalized_tags() {
        let tags = FeatureTags::parse(&["Shelter".into(), " bench ".into()]).unwrap();
        assert_eq!(tags.as_slice(), ["shelter".to_owned(), "bench".to_owned()]);
        let err = FeatureTags::parse(&[
            "wifi".into(),
            "WIFI".into(),
            "".into(),
            "two words".into(),
            "x".repeat(41),
        ])
        .unwrap_err();
        assert_eq!(
            codes(&err),
            vec![
                ("[1]".into(), "duplicate"),
                ("[2]".into(), "required"),
                ("[3]".into(), "invalid_format"),
                ("[4]".into(), "too_long"),
            ]
        );
        let many: Vec<String> = (0..21).map(|i| format!("t{i}")).collect();
        let count = vec![(String::new(), "out_of_range")];
        assert_eq!(codes(&FeatureTags::parse(&many).unwrap_err()), count);
    }

    fn entry(stop_id: StopId, time: Option<u32>) -> StopSequenceEntry {
        StopSequenceEntry { stop_id, time_from_previous_s: time }
    }

    #[test]
    fn stop_sequences_are_unique_bounded_and_start_without_segment() {
        let (a, b) = (StopId::generate(), StopId::generate());
        assert!(StopSequence::parse(Vec::new()).unwrap().is_empty());
        let seq = StopSequence::parse(vec![entry(a, None), entry(b, Some(120))]).unwrap();
        assert_eq!(seq.len(), 2);
        let err = StopSequence::parse(vec![entry(a, Some(5)), entry(b, None), entry(a, None)]);
        assert_eq!(
            codes(&err.unwrap_err()),
            vec![
                ("[2].stop_id".into(), "duplicate"),
                ("[0].time_from_previous_s".into(), "not_allowed"),
            ]
        );
        let too_many = (0..=MAX_LINE_STOPS).map(|_| entry(StopId::generate(), None)).collect();
        let count = vec![(String::new(), "out_of_range")];
        assert_eq!(codes(&StopSequence::parse(too_many).unwrap_err()), count);
    }

    #[test]
    fn insert_positions_default_to_the_end() {
        assert_eq!(insert_position(0, None), Ok(0));
        assert_eq!(insert_position(3, None), Ok(3));
        assert_eq!(insert_position(3, Some(0)), Ok(0));
        assert_eq!(insert_position(3, Some(3)), Ok(3));
        assert_eq!(insert_position(3, Some(4)), Err(Violation::OutOfRange { min: 0, max: 3 }));
        assert_eq!(insert_position(3, Some(-1)), Err(Violation::OutOfRange { min: 0, max: 3 }));
        assert_eq!(
            insert_position(MAX_LINE_STOPS, None),
            Err(Violation::OutOfRange { min: 0, max: 199 })
        );
    }

    fn schedule(line_id: LineId, day: u8, start: u16, end: u16, active: bool) -> Schedule {
        let at = DateTime::<Utc>::UNIX_EPOCH;
        Schedule {
            id: ScheduleId::generate(),
            line_id,
            day: Weekday::parse(i64::from(day)).unwrap(),
            window: TimeWindow::new(
                TimeOfDay::from_minutes(start).unwrap(),
                TimeOfDay::from_minutes(end).unwrap(),
            )
            .unwrap(),
            frequency: Frequency::parse(10).unwrap(),
            is_active: active,
            created_at: at,
            updated_at: at,
        }
    }

    #[test]
    fn only_active_schedules_of_the_same_line_and_day_conflict() {
        let line = LineId::generate();
        let base = schedule(line, 1, 360, 540, true);
        assert!(base.conflicts_with(&schedule(line, 1, 500, 600, true)));
        assert!(!base.conflicts_with(&schedule(line, 2, 500, 600, true)), "other day");
        assert!(!base.conflicts_with(&schedule(line, 1, 500, 600, false)), "inactive");
        assert!(!base.conflicts_with(&schedule(LineId::generate(), 1, 500, 600, true)));
        assert!(!base.conflicts_with(&schedule(line, 1, 540, 600, true)), "adjacent");
        assert!(!base.conflicts_with(&base), "a schedule does not conflict with itself");
    }

    proptest! {
        #[test]
        fn times_of_day_round_trip(minutes in 0u16..1440) {
            let t = TimeOfDay::from_minutes(minutes).unwrap();
            prop_assert_eq!(TimeOfDay::parse(&t.to_string()), Ok(t));
        }

        #[test]
        fn window_overlap_is_symmetric_and_matches_minute_sets(
            a in 0u16..1439, la in 1u16..1440, b in 0u16..1439, lb in 1u16..1440,
        ) {
            let window = |s: u16, l: u16| {
                let end = (s + l).min(1439);
                (s < end).then(|| {
                    TimeWindow::new(
                        TimeOfDay::from_minutes(s).unwrap(),
                        TimeOfDay::from_minutes(end).unwrap(),
                    )
                    .unwrap()
                })
            };
            if let (Some(x), Some(y)) = (window(a, la), window(b, lb)) {
                prop_assert_eq!(x.overlaps(y), y.overlaps(x));
                let minutes = |w: TimeWindow| w.start().minutes()..w.end().minutes();
                let shared = minutes(x).any(|m| minutes(y).contains(&m));
                prop_assert_eq!(x.overlaps(y), shared);
            }
        }

        #[test]
        fn valid_stop_sequences_have_unique_ids(
            picks in prop::collection::vec(0usize..8, 0..12),
            first_time in proptest::option::of(0u32..100),
        ) {
            let pool: Vec<StopId> = (0..8).map(|_| StopId::generate()).collect();
            let entries: Vec<StopSequenceEntry> = picks
                .iter()
                .enumerate()
                .map(|(i, &p)| entry(pool[p], if i == 0 { first_time } else { Some(60) }))
                .collect();
            let unique = picks.iter().collect::<HashSet<_>>().len() == picks.len();
            let first_ok = picks.is_empty() || first_time.is_none();
            match StopSequence::parse(entries.clone()) {
                Ok(seq) => {
                    prop_assert!(unique && first_ok);
                    prop_assert_eq!(seq.entries(), entries.as_slice());
                }
                Err(_) => prop_assert!(!unique || !first_ok),
            }
        }

        #[test]
        fn insert_positions_stay_within_the_line(len in 0usize..250, requested in -5i64..260) {
            match insert_position(len, Some(requested)) {
                Ok(p) => prop_assert!(len < MAX_LINE_STOPS && usize::from(p) <= len),
                Err(_) => {
                    let past_end = requested < 0 || requested as usize > len;
                    prop_assert!(len >= MAX_LINE_STOPS || past_end);
                }
            }
        }

        #[test]
        fn line_codes_are_idempotent(raw in "[A-Za-z0-9-]{1,20}") {
            let code = LineCode::parse(&raw).unwrap();
            prop_assert_eq!(LineCode::parse(code.as_str()).unwrap(), code.clone());
            prop_assert_eq!(code.as_str(), raw.to_ascii_uppercase());
        }
    }
}
