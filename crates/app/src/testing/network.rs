//! In-memory network catalogue: the same contracts as `dz_infra::pg::network`, with the
//! database constraints (`line_stops_stop_id_fkey`, `lines_code_key`, `schedules_no_overlap`…)
//! checked by hand. Distances from the previous stop are haversine distances computed on read.

use std::collections::{HashMap, HashSet};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::geo::{GeoPoint, LineGeometry};
use dz_domain::ids::{LineId, ScheduleId, StopId};
use dz_domain::network::{
    Line, LineStop, Schedule, Stop, StopSequence, StopSequenceEntry, TimeWindow, insert_position,
};
use dz_domain::{ConflictKind, Violation};

use super::{InMemoryStore, mark_attached};
use crate::error::{AppError, AppResult};
use crate::network::ports::{
    LineFilter, LinePatch, LineRepository, NearbyStop, NewLine, NewSchedule, NewStop,
    ScheduleRepository, SchedulePatch, StopFilter, StopPatch, StopRepository,
};
use crate::pagination::{Cursor, Page, PageRequest};
use crate::ports::{ClaimedUpload, WriteEffects};

#[derive(Debug, Clone)]
struct LineRow {
    line: Line,
    route: Option<LineGeometry>,
}

/// The catalogue part of the in-memory database.
#[derive(Debug, Default)]
pub(super) struct NetworkState {
    stops: HashMap<StopId, Stop>,
    lines: HashMap<LineId, LineRow>,
    /// Ordered stops of each line with their segment time.
    line_stops: HashMap<LineId, Vec<StopSequenceEntry>>,
    schedules: HashMap<ScheduleId, Schedule>,
}

impl NetworkState {
    fn line(&self, id: LineId) -> Option<Line> {
        let row = self.lines.get(&id)?;
        let count = self.line_stops.get(&id).map_or(0, Vec::len);
        Some(Line {
            has_route: row.route.is_some(),
            stops_count: u32::try_from(count).unwrap(),
            ..row.line.clone()
        })
    }

    fn line_stops(&self, id: LineId) -> Vec<LineStop> {
        let entries = self.line_stops.get(&id).cloned().unwrap_or_default();
        let mut previous: Option<GeoPoint> = None;
        entries
            .iter()
            .enumerate()
            .map(|(position, entry)| {
                let stop = self.stops[&entry.stop_id].clone();
                let distance = previous.map(|p| p.haversine_m(stop.location));
                previous = Some(stop.location);
                LineStop {
                    position: u16::try_from(position).unwrap(),
                    stop,
                    distance_from_previous_m: distance,
                    time_from_previous_s: entry.time_from_previous_s,
                }
            })
            .collect()
    }

    fn serves(&self, line_id: LineId, stop_id: StopId) -> bool {
        self.line_stops.get(&line_id).is_some_and(|e| e.iter().any(|e| e.stop_id == stop_id))
    }

    fn touch_line(&mut self, id: LineId, at: DateTime<Utc>) -> AppResult<()> {
        let row = self.lines.get_mut(&id).ok_or(AppError::NotFound("line"))?;
        row.line.updated_at = at;
        Ok(())
    }

    fn check_overlap(&self, schedule: &Schedule) -> AppResult<()> {
        if self.schedules.values().any(|other| schedule.conflicts_with(other)) {
            return Err(AppError::Conflict(ConflictKind::ScheduleOverlap));
        }
        Ok(())
    }
}

/// Keyset pagination over rows sorted by `(created_at DESC, id DESC)`.
fn paginate<T>(
    mut rows: Vec<T>,
    page: PageRequest,
    key: impl Fn(&T) -> Cursor + Copy,
) -> Page<T> {
    rows.sort_by(|a, b| {
        let (a, b) = (key(a), key(b));
        (b.created_at, b.id).cmp(&(a.created_at, a.id))
    });
    let after = |row: &T| {
        let k = key(row);
        page.after.is_none_or(|c| (k.created_at, k.id) < (c.created_at, c.id))
    };
    let rows: Vec<T> = rows
        .into_iter()
        .filter(|row| after(row))
        .take(usize::try_from(page.fetch_limit()).unwrap())
        .collect();
    Page::from_rows(rows, page, key)
}

fn contains_ci(haystack: &str, needle: &str) -> bool {
    haystack.to_lowercase().contains(&needle.to_lowercase())
}

#[async_trait]
impl StopRepository for InMemoryStore {
    async fn insert(&self, new: NewStop, effects: WriteEffects) -> AppResult<Stop> {
        let mut state = self.state();
        let stop = Stop {
            id: new.id,
            name: new.name,
            location: new.location,
            address: new.address,
            wilaya: new.wilaya,
            commune: new.commune,
            description: new.description,
            features: new.features,
            is_active: new.is_active,
            photo_key: None,
            created_at: new.created_at,
            updated_at: new.created_at,
        };
        state.network.stops.insert(stop.id, stop.clone());
        state.persist(effects);
        Ok(stop)
    }

    async fn find(&self, id: StopId) -> AppResult<Option<Stop>> {
        Ok(self.state().network.stops.get(&id).cloned())
    }

    async fn existing(&self, ids: &[StopId]) -> AppResult<HashSet<StopId>> {
        let state = self.state();
        Ok(ids.iter().copied().filter(|id| state.network.stops.contains_key(id)).collect())
    }

    async fn list(&self, filter: &StopFilter, page: PageRequest) -> AppResult<Page<Stop>> {
        let state = self.state();
        let network = &state.network;
        let rows = network
            .stops
            .values()
            .filter(|s| filter.q.as_deref().is_none_or(|q| contains_ci(s.name.as_str(), q)))
            .filter(|s| filter.wilaya.as_deref().is_none_or(|w| s.wilaya.eq_ignore_ascii_case(w)))
            .filter(|s| filter.commune.as_deref().is_none_or(|c| s.commune.eq_ignore_ascii_case(c)))
            .filter(|s| {
                filter.line_id.is_none_or(|l| {
                    let visible = network
                        .lines
                        .get(&l)
                        .is_some_and(|r| filter.include_inactive_lines || r.line.is_active);
                    visible && network.serves(l, s.id)
                })
            })
            .filter(|s| filter.is_active.is_none_or(|a| s.is_active == a))
            .cloned()
            .collect();
        Ok(paginate(rows, page, |s| Cursor { created_at: s.created_at, id: s.id.as_uuid() }))
    }

    async fn nearby(
        &self,
        center: GeoPoint,
        radius_m: u32,
        limit: u32,
    ) -> AppResult<Vec<NearbyStop>> {
        let state = self.state();
        let mut found: Vec<NearbyStop> = state
            .network
            .stops
            .values()
            .filter(|s| s.is_active)
            .map(|s| NearbyStop { stop: s.clone(), distance_m: center.haversine_m(s.location) })
            .filter(|n| n.distance_m <= f64::from(radius_m))
            .collect();
        found.sort_by(|a, b| a.distance_m.total_cmp(&b.distance_m));
        found.truncate(usize::try_from(limit).unwrap());
        Ok(found)
    }

    async fn update(
        &self,
        id: StopId,
        patch: StopPatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop> {
        let mut state = self.state();
        let stop = state.network.stops.get_mut(&id).ok_or(AppError::NotFound("stop"))?;
        if let Some(name) = patch.name {
            stop.name = name;
        }
        if let Some(location) = patch.location {
            stop.location = location;
        }
        for (field, value) in [
            (&mut stop.address, patch.address),
            (&mut stop.wilaya, patch.wilaya),
            (&mut stop.commune, patch.commune),
            (&mut stop.description, patch.description),
        ] {
            if let Some(value) = value {
                *field = value;
            }
        }
        if let Some(features) = patch.features {
            stop.features = features;
        }
        if let Some(is_active) = patch.is_active {
            stop.is_active = is_active;
        }
        stop.updated_at = at;
        let stop = stop.clone();
        state.persist(effects);
        Ok(stop)
    }

    async fn delete(
        &self,
        id: StopId,
        expected_photo: Option<&str>,
        effects: WriteEffects,
    ) -> AppResult<()> {
        let mut state = self.state();
        let stop = state.network.stops.get(&id).ok_or(AppError::NotFound("stop"))?;
        if stop.photo_key.as_deref() != expected_photo {
            return Err(AppError::Conflict(ConflictKind::StaleState));
        }
        if state.network.line_stops.values().flatten().any(|e| e.stop_id == id) {
            return Err(AppError::Conflict(ConflictKind::StopInUse));
        }
        state.network.stops.remove(&id);
        state.persist(effects);
        Ok(())
    }

    async fn set_photo(
        &self,
        id: StopId,
        photo: Option<&ClaimedUpload>,
        expected: Option<&str>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop> {
        let mut state = self.state();
        let stop = state.network.stops.get(&id).ok_or(AppError::NotFound("stop"))?;
        if stop.photo_key.as_deref() != expected {
            return Err(AppError::Conflict(ConflictKind::StaleState));
        }
        if let Some(claimed) = photo {
            mark_attached(&mut state, claimed, at)?;
        }
        let stop = state.network.stops.get_mut(&id).unwrap();
        stop.photo_key = photo.map(|c| c.object_key.clone());
        stop.updated_at = at;
        let stop = stop.clone();
        state.persist(effects);
        Ok(stop)
    }

    async fn lines(&self, id: StopId, include_inactive: bool) -> AppResult<Vec<Line>> {
        let state = self.state();
        let network = &state.network;
        let mut lines: Vec<Line> = network
            .lines
            .keys()
            .filter(|l| network.serves(**l, id))
            .filter_map(|l| network.line(*l))
            .filter(|l| include_inactive || l.is_active)
            .collect();
        lines.sort_by(|a, b| a.code.as_str().cmp(b.code.as_str()));
        Ok(lines)
    }
}

#[async_trait]
impl LineRepository for InMemoryStore {
    async fn insert(&self, new: NewLine, effects: WriteEffects) -> AppResult<Line> {
        let mut state = self.state();
        if state.network.lines.values().any(|row| row.line.code == new.code) {
            return Err(AppError::Conflict(ConflictKind::LineCodeTaken));
        }
        let line = Line {
            id: new.id,
            code: new.code,
            name: new.name,
            description: new.description,
            color: new.color,
            frequency_minutes: new.frequency_minutes,
            fare_dza: new.fare_dza,
            is_active: new.is_active,
            has_route: false,
            stops_count: 0,
            created_at: new.created_at,
            updated_at: new.created_at,
        };
        state.network.lines.insert(line.id, LineRow { line: line.clone(), route: None });
        state.persist(effects);
        Ok(line)
    }

    async fn find(&self, id: LineId) -> AppResult<Option<Line>> {
        Ok(self.state().network.line(id))
    }

    async fn list(&self, filter: &LineFilter, page: PageRequest) -> AppResult<Page<Line>> {
        let state = self.state();
        let network = &state.network;
        let rows = network
            .lines
            .keys()
            .filter_map(|id| network.line(*id))
            .filter(|l| {
                filter.q.as_deref().is_none_or(|q| {
                    contains_ci(&format!("{} {}", l.code.as_str(), l.name.as_str()), q)
                })
            })
            .filter(|l| filter.stop_id.is_none_or(|s| network.serves(l.id, s)))
            .filter(|l| filter.is_active.is_none_or(|a| l.is_active == a))
            .collect();
        Ok(paginate(rows, page, |l| Cursor { created_at: l.created_at, id: l.id.as_uuid() }))
    }

    async fn update(
        &self,
        id: LineId,
        patch: LinePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line> {
        let mut state = self.state();
        let row = state.network.lines.get_mut(&id).ok_or(AppError::NotFound("line"))?;
        let line = &mut row.line;
        if let Some(name) = patch.name {
            line.name = name;
        }
        if let Some(description) = patch.description {
            line.description = description;
        }
        if let Some(color) = patch.color {
            line.color = color;
        }
        if let Some(frequency) = patch.frequency_minutes {
            line.frequency_minutes = frequency;
        }
        if let Some(fare) = patch.fare_dza {
            line.fare_dza = fare;
        }
        if let Some(is_active) = patch.is_active {
            line.is_active = is_active;
        }
        line.updated_at = at;
        state.persist(effects);
        Ok(state.network.line(id).unwrap())
    }

    async fn delete(&self, id: LineId, effects: WriteEffects) -> AppResult<()> {
        let mut state = self.state();
        if state.network.lines.remove(&id).is_none() {
            return Err(AppError::NotFound("line"));
        }
        state.network.line_stops.remove(&id);
        state.network.schedules.retain(|_, s| s.line_id != id);
        state.persist(effects);
        Ok(())
    }

    async fn stops(&self, id: LineId) -> AppResult<Vec<LineStop>> {
        Ok(self.state().network.line_stops(id))
    }

    async fn replace_stops(
        &self,
        id: LineId,
        stops: &StopSequence,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let mut state = self.state();
        state.network.touch_line(id, at)?;
        if stops.entries().iter().any(|e| !state.network.stops.contains_key(&e.stop_id)) {
            return Err(AppError::invalid("stops", Violation::UnknownReference));
        }
        state.network.line_stops.insert(id, stops.entries().to_vec());
        state.persist(effects);
        Ok(state.network.line_stops(id))
    }

    async fn add_stop(
        &self,
        id: LineId,
        entry: StopSequenceEntry,
        position: Option<i64>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let mut state = self.state();
        state.network.touch_line(id, at)?;
        if !state.network.stops.contains_key(&entry.stop_id) {
            return Err(AppError::invalid("stop_id", Violation::UnknownReference));
        }
        if state.network.serves(id, entry.stop_id) {
            return Err(AppError::Conflict(ConflictKind::StopAlreadyOnLine));
        }
        let entries = state.network.line_stops.entry(id).or_default();
        let position = usize::from(
            insert_position(entries.len(), position)
                .map_err(|violation| AppError::invalid("position", violation))?,
        );
        if position == 0 && entry.time_from_previous_s.is_some() {
            return Err(AppError::invalid("time_from_previous_s", Violation::NotAllowed));
        }
        // The stop that followed the insertion point now follows the new stop: its segment
        // time is unknown. A former first stop has no time anyway.
        if let Some(next) = entries.get_mut(position) {
            next.time_from_previous_s = None;
        }
        entries.insert(position, entry);
        state.persist(effects);
        Ok(state.network.line_stops(id))
    }

    async fn remove_stop(
        &self,
        id: LineId,
        stop_id: StopId,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let mut state = self.state();
        state.network.touch_line(id, at)?;
        let entries = state.network.line_stops.entry(id).or_default();
        let index = entries
            .iter()
            .position(|e| e.stop_id == stop_id)
            .ok_or(AppError::NotFound("line_stop"))?;
        let removed = entries.remove(index);
        if let Some(next) = entries.get_mut(index) {
            next.time_from_previous_s = match (index, removed.time_from_previous_s) {
                (0, _) => None,
                (_, Some(removed)) => next.time_from_previous_s.map(|t| t + removed),
                (_, None) => None,
            };
        }
        state.persist(effects);
        Ok(state.network.line_stops(id))
    }

    async fn route(&self, id: LineId) -> AppResult<Option<LineGeometry>> {
        Ok(self.state().network.lines.get(&id).and_then(|row| row.route.clone()))
    }

    async fn set_route(
        &self,
        id: LineId,
        route: Option<&LineGeometry>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line> {
        let mut state = self.state();
        let row = state.network.lines.get_mut(&id).ok_or(AppError::NotFound("line"))?;
        row.route = route.cloned();
        row.line.updated_at = at;
        state.persist(effects);
        Ok(state.network.line(id).unwrap())
    }
}

#[async_trait]
impl ScheduleRepository for InMemoryStore {
    async fn insert(&self, new: NewSchedule, effects: WriteEffects) -> AppResult<Schedule> {
        let mut state = self.state();
        if !state.network.lines.contains_key(&new.line_id) {
            return Err(AppError::NotFound("line"));
        }
        let schedule = Schedule {
            id: new.id,
            line_id: new.line_id,
            day: new.day,
            window: new.window,
            frequency: new.frequency,
            is_active: new.is_active,
            created_at: new.created_at,
            updated_at: new.created_at,
        };
        state.network.check_overlap(&schedule)?;
        state.network.schedules.insert(schedule.id, schedule.clone());
        state.persist(effects);
        Ok(schedule)
    }

    async fn find(&self, id: ScheduleId) -> AppResult<Option<Schedule>> {
        Ok(self.state().network.schedules.get(&id).cloned())
    }

    async fn list_for_line(
        &self,
        line_id: LineId,
        include_inactive: bool,
    ) -> AppResult<Vec<Schedule>> {
        let state = self.state();
        let mut schedules: Vec<Schedule> = state
            .network
            .schedules
            .values()
            .filter(|s| s.line_id == line_id && (include_inactive || s.is_active))
            .cloned()
            .collect();
        schedules.sort_by_key(|s| (s.day, s.window.start(), s.id));
        Ok(schedules)
    }

    async fn update(
        &self,
        id: ScheduleId,
        patch: SchedulePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Schedule> {
        let mut state = self.state();
        let current = state.network.schedules.get(&id).ok_or(AppError::NotFound("schedule"))?;
        let window = TimeWindow::new(
            patch.start.unwrap_or(current.window.start()),
            patch.end.unwrap_or(current.window.end()),
        )
        .map_err(|violation| AppError::invalid("end_time", violation))?;
        let updated = Schedule {
            day: patch.day.unwrap_or(current.day),
            window,
            frequency: patch.frequency.unwrap_or(current.frequency),
            is_active: patch.is_active.unwrap_or(current.is_active),
            updated_at: at,
            ..current.clone()
        };
        state.network.check_overlap(&updated)?;
        state.network.schedules.insert(id, updated.clone());
        state.persist(effects);
        Ok(updated)
    }

    async fn delete(&self, id: ScheduleId, effects: WriteEffects) -> AppResult<()> {
        let mut state = self.state();
        state.network.schedules.remove(&id).ok_or(AppError::NotFound("schedule"))?;
        state.persist(effects);
        Ok(())
    }
}

impl InMemoryStore {
    /// The stored stops of a line with their segment times, in order (for assertions).
    #[must_use]
    pub fn line_stop_entries(&self, id: LineId) -> Vec<StopSequenceEntry> {
        self.state().network.line_stops.get(&id).cloned().unwrap_or_default()
    }
}
