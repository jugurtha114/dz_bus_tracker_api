//! Repository ports of the network catalogue.
//!
//! Write methods persist their [`WriteEffects`] (audit entries, outbox jobs) in the
//! transaction of the change. Constraint violations come back as typed errors:
//! `Conflict(StopInUse)`, `Conflict(LineCodeTaken)`, `Conflict(LineInUse)`,
//! `Conflict(StopAlreadyOnLine)`, `Conflict(ScheduleOverlap)`, or field violations.

use std::collections::HashSet;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::geo::{GeoPoint, LineGeometry};
use dz_domain::ids::{LineId, ScheduleId, StopId};
use dz_domain::network::{
    FeatureTags, Fare, Frequency, HexColor, Line, LineCode, LineName, LineStop, Schedule, Stop,
    StopName, StopSequence, StopSequenceEntry, TimeOfDay, TimeWindow, Weekday,
};

use crate::error::AppResult;
use crate::pagination::{Page, PageRequest};
use crate::ports::{ClaimedUpload, WriteEffects};

// --- Stops ---------------------------------------------------------------------------------------

/// A stop to insert.
#[derive(Debug, Clone, PartialEq)]
pub struct NewStop {
    pub id: StopId,
    pub name: StopName,
    pub location: GeoPoint,
    pub address: String,
    pub wilaya: String,
    pub commune: String,
    pub description: String,
    pub features: FeatureTags,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

/// Changes to a stop; `None` leaves a field unchanged (empty texts clear optional texts).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct StopPatch {
    pub name: Option<StopName>,
    pub location: Option<GeoPoint>,
    pub address: Option<String>,
    pub wilaya: Option<String>,
    pub commune: Option<String>,
    pub description: Option<String>,
    pub features: Option<FeatureTags>,
    pub is_active: Option<bool>,
}

impl StopPatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        *self == Self::default()
    }
}

/// Filters of the stop list (all optional, combined with AND).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StopFilter {
    /// Substring of the name (case-insensitive).
    pub q: Option<String>,
    /// Exact wilaya (case-insensitive).
    pub wilaya: Option<String>,
    /// Exact commune (case-insensitive).
    pub commune: Option<String>,
    /// Stops served by this line.
    pub line_id: Option<LineId>,
    /// Whether `line_id` may name an inactive line (otherwise such a line serves no stop).
    pub include_inactive_lines: bool,
    pub is_active: Option<bool>,
}

/// A stop with its distance from the searched point.
#[derive(Debug, Clone, PartialEq)]
pub struct NearbyStop {
    pub stop: Stop,
    pub distance_m: f64,
}

#[async_trait]
pub trait StopRepository: Send + Sync {
    async fn insert(&self, stop: NewStop, effects: WriteEffects) -> AppResult<Stop>;
    async fn find(&self, id: StopId) -> AppResult<Option<Stop>>;
    /// Which of `ids` exist.
    async fn existing(&self, ids: &[StopId]) -> AppResult<HashSet<StopId>>;
    async fn list(&self, filter: &StopFilter, page: PageRequest) -> AppResult<Page<Stop>>;
    /// Active stops within `radius_m` metres of `center`, nearest first, at most `limit`.
    async fn nearby(
        &self,
        center: GeoPoint,
        radius_m: u32,
        limit: u32,
    ) -> AppResult<Vec<NearbyStop>>;
    /// Moving the stop recomputes the distances of every line serving it. Fails with
    /// `NotFound("stop")`, and with `Conflict(StaleState)` when lines keep gaining the moved
    /// stop concurrently.
    async fn update(
        &self,
        id: StopId,
        patch: StopPatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop>;
    /// Deletes the stop provided its photo is still `expected_photo` (`Conflict(StaleState)`
    /// otherwise, since `effects` delete that object). Fails with `NotFound("stop")` and with
    /// `Conflict(StopInUse)` while a line serves the stop.
    async fn delete(
        &self,
        id: StopId,
        expected_photo: Option<&str>,
        effects: WriteEffects,
    ) -> AppResult<()>;
    /// Replaces the photo (or removes it with `None`) provided it is still `expected`, and
    /// marks the new upload attached, in one transaction. Fails with `NotFound("stop")`,
    /// `Conflict(StaleState)` and `Conflict(UploadAlreadyUsed)`.
    async fn set_photo(
        &self,
        id: StopId,
        photo: Option<&ClaimedUpload>,
        expected: Option<&str>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop>;
    /// Lines serving the stop, ordered by code; inactive lines only when asked.
    async fn lines(&self, id: StopId, include_inactive: bool) -> AppResult<Vec<Line>>;
}

// --- Lines ---------------------------------------------------------------------------------------

/// A line to insert.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NewLine {
    pub id: LineId,
    pub code: LineCode,
    pub name: LineName,
    pub description: String,
    pub color: HexColor,
    pub frequency_minutes: Option<Frequency>,
    pub fare_dza: Option<Fare>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

/// Changes to a line (the code is immutable). `Some(None)` clears a nullable field.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LinePatch {
    pub name: Option<LineName>,
    pub description: Option<String>,
    pub color: Option<HexColor>,
    pub frequency_minutes: Option<Option<Frequency>>,
    pub fare_dza: Option<Option<Fare>>,
    pub is_active: Option<bool>,
}

impl LinePatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        *self == Self::default()
    }
}

/// Filters of the line list.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LineFilter {
    /// Substring of `code || ' ' || name` (case-insensitive).
    pub q: Option<String>,
    /// Lines serving this stop.
    pub stop_id: Option<StopId>,
    pub is_active: Option<bool>,
}

#[async_trait]
pub trait LineRepository: Send + Sync {
    /// Fails with `Conflict(LineCodeTaken)`.
    async fn insert(&self, line: NewLine, effects: WriteEffects) -> AppResult<Line>;
    async fn find(&self, id: LineId) -> AppResult<Option<Line>>;
    async fn list(&self, filter: &LineFilter, page: PageRequest) -> AppResult<Page<Line>>;
    /// Fails with `NotFound("line")`.
    async fn update(
        &self,
        id: LineId,
        patch: LinePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line>;
    /// Deletes the line with its stops list and schedules. Fails with `NotFound("line")` and
    /// with `Conflict(LineInUse)` while buses are assigned to it.
    async fn delete(&self, id: LineId, effects: WriteEffects) -> AppResult<()>;
    /// The stops of the line, by position (empty for an unknown line).
    async fn stops(&self, id: LineId) -> AppResult<Vec<LineStop>>;
    /// Replaces the whole ordered stop list atomically and recomputes every distance from the
    /// previous stop. Fails with `NotFound("line")` and with a violation on `stops` when a
    /// stop was deleted concurrently.
    async fn replace_stops(
        &self,
        id: LineId,
        stops: &StopSequence,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>>;
    /// Inserts a stop at `position` (default: the end), shifting later stops, and recomputes
    /// the distances. Fails with `NotFound("line")`, `Conflict(StopAlreadyOnLine)`, and field
    /// violations on `position` (past the end, line full), `stop_id` (unknown stop) and
    /// `time_from_previous_s` (set on the first stop).
    async fn add_stop(
        &self,
        id: LineId,
        entry: StopSequenceEntry,
        position: Option<i64>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>>;
    /// Removes a stop and closes the gap; the next stop's distance is recomputed and its time
    /// becomes the sum of both segments' times (when both are known). Fails with
    /// `NotFound("line")` and `NotFound("line_stop")`.
    async fn remove_stop(
        &self,
        id: LineId,
        stop_id: StopId,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>>;
    /// The route of the line, if set.
    async fn route(&self, id: LineId) -> AppResult<Option<LineGeometry>>;
    /// Sets (or removes with `None`) the route. Fails with `NotFound("line")`.
    async fn set_route(
        &self,
        id: LineId,
        route: Option<&LineGeometry>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line>;
}

// --- Schedules -----------------------------------------------------------------------------------

/// A schedule to insert.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NewSchedule {
    pub id: ScheduleId,
    pub line_id: LineId,
    pub day: Weekday,
    pub window: TimeWindow,
    pub frequency: Frequency,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

/// Changes to a schedule (the line is immutable).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SchedulePatch {
    pub day: Option<Weekday>,
    pub start: Option<TimeOfDay>,
    pub end: Option<TimeOfDay>,
    pub frequency: Option<Frequency>,
    pub is_active: Option<bool>,
}

impl SchedulePatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        *self == Self::default()
    }
}

#[async_trait]
pub trait ScheduleRepository: Send + Sync {
    /// Fails with `NotFound("line")` and `Conflict(ScheduleOverlap)`.
    async fn insert(&self, schedule: NewSchedule, effects: WriteEffects) -> AppResult<Schedule>;
    async fn find(&self, id: ScheduleId) -> AppResult<Option<Schedule>>;
    /// Schedules of a line by day and start time; inactive ones only when asked.
    async fn list_for_line(&self, line_id: LineId, include_inactive: bool)
    -> AppResult<Vec<Schedule>>;
    /// Applies the patch to the stored row. Fails with `NotFound("schedule")`,
    /// `Conflict(ScheduleOverlap)`, and a violation on `end_time` when the resulting window
    /// is empty (the row changed concurrently).
    async fn update(
        &self,
        id: ScheduleId,
        patch: SchedulePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Schedule>;
    /// Fails with `NotFound("schedule")`.
    async fn delete(&self, id: ScheduleId, effects: WriteEffects) -> AppResult<()>;
}
