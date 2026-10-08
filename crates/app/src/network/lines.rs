//! Line use-cases: catalogue reads, administration, the ordered stop list and the route.

use std::sync::Arc;

use dz_domain::authz::{Action, Actor, CatalogResource, Policy};
use dz_domain::geo::LineGeometry;
use dz_domain::ids::{LineId, StopId};
use dz_domain::network::{
    DESCRIPTION_MAX_CHARS, Fare, Frequency, HexColor, Line, LineCode, LineName, LineStop,
    StopSequence, StopSequenceEntry, optional_text, segment_time,
};
use dz_domain::{Violation, Violations};
use serde_json::{Map, Value, json};

use super::ports::{LineFilter, LinePatch, LineRepository, NewLine, StopRepository};
use super::{activity_filter, search_term, sees_inactive};
use crate::audit;
use crate::error::{AppError, AppResult};
use crate::pagination::{Page, PageRequest};
use crate::ports::{Clock, RequestMeta, WriteEffects};

/// Raw filters of the line list.
#[derive(Debug, Clone, Default)]
pub struct LineListQuery {
    pub q: Option<String>,
    pub stop_id: Option<StopId>,
    /// Writers only.
    pub is_active: Option<bool>,
}

/// Raw input of a new line.
#[derive(Debug, Clone, Default)]
pub struct CreateLineInput {
    pub code: String,
    pub name: String,
    pub description: Option<String>,
    pub color: Option<String>,
    pub frequency_minutes: Option<i64>,
    pub fare_dza: Option<i64>,
    pub is_active: Option<bool>,
}

/// Raw changes to a line; `Some(None)` clears a nullable field.
#[derive(Debug, Clone, Default)]
pub struct UpdateLineInput {
    pub name: Option<String>,
    pub description: Option<String>,
    pub color: Option<String>,
    pub frequency_minutes: Option<Option<i64>>,
    pub fare_dza: Option<Option<i64>>,
    pub is_active: Option<bool>,
}

/// Raw input of `POST /lines/{id}/stops`.
#[derive(Debug, Clone, Copy)]
pub struct AddLineStopInput {
    pub stop_id: StopId,
    /// 0-based; default: after the last stop.
    pub position: Option<i64>,
    pub time_from_previous_s: Option<i64>,
}

pub struct LineService {
    lines: Arc<dyn LineRepository>,
    stops: Arc<dyn StopRepository>,
    clock: Arc<dyn Clock>,
}

impl LineService {
    #[must_use]
    pub fn new(
        lines: Arc<dyn LineRepository>,
        stops: Arc<dyn StopRepository>,
        clock: Arc<dyn Clock>,
    ) -> Self {
        Self { lines, stops, clock }
    }

    fn authorize_write(actor: &Actor) -> AppResult<()> {
        Policy::authorize(actor, &Action::WriteCatalog { resource: CatalogResource::Line })?;
        Ok(())
    }

    /// A line the actor may see: inactive lines are hidden from non-writers.
    async fn visible(&self, actor: &Actor, id: LineId) -> AppResult<Line> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        self.lines
            .find(id)
            .await?
            .filter(|l| l.is_active || sees_inactive(actor, CatalogResource::Line))
            .ok_or(AppError::NotFound("line"))
    }

    async fn existing(&self, id: LineId) -> AppResult<Line> {
        self.lines.find(id).await?.ok_or(AppError::NotFound("line"))
    }

    fn audit(
        actor: &Actor,
        meta: &RequestMeta,
        now: chrono::DateTime<chrono::Utc>,
        action: &'static str,
        id: LineId,
        details: Value,
    ) -> WriteEffects {
        let entry = audit::entry(actor, meta, now, action, "line", id.to_string(), details);
        WriteEffects::audited(entry)
    }

    /// Lines, newest first, filtered.
    pub async fn list(
        &self,
        actor: &Actor,
        query: LineListQuery,
        page: PageRequest,
    ) -> AppResult<Page<Line>> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        let is_active = activity_filter(actor, CatalogResource::Line, query.is_active)?;
        let mut v = Violations::new();
        let q = search_term(query.q.as_deref(), &mut v);
        v.into_result()?;
        let filter = LineFilter { q, stop_id: query.stop_id, is_active };
        self.lines.list(&filter, page).await
    }

    pub async fn get(&self, actor: &Actor, id: LineId) -> AppResult<Line> {
        self.visible(actor, id).await
    }

    pub async fn create(
        &self,
        actor: &Actor,
        input: CreateLineInput,
        meta: &RequestMeta,
    ) -> AppResult<Line> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let code = v.check("code", LineCode::parse(&input.code));
        let name = v.check("name", LineName::parse(&input.name));
        let description = input
            .description
            .and_then(|raw| v.check("description", optional_text(&raw, DESCRIPTION_MAX_CHARS)))
            .unwrap_or_default();
        let color = match input.color {
            Some(raw) => v.check("color", HexColor::parse(&raw)),
            None => Some(HexColor::default_color()),
        };
        let frequency_minutes = input
            .frequency_minutes
            .and_then(|raw| v.check("frequency_minutes", Frequency::parse(raw)));
        let fare_dza = input.fare_dza.and_then(|raw| v.check("fare_dza", Fare::parse(raw)));
        let (Some(code), Some(name), Some(color)) = (code, name, color) else {
            return Err(v.into());
        };
        v.into_result()?;

        let id = LineId::generate();
        let now = self.clock.now();
        let details = json!({ "code": code.as_str(), "name": name.as_str() });
        let effects = Self::audit(actor, meta, now, "line.create", id, details);
        let new = NewLine {
            id,
            code,
            name,
            description,
            color,
            frequency_minutes,
            fare_dza,
            is_active: input.is_active.unwrap_or(true),
            created_at: now,
        };
        let line = self.lines.insert(new, effects).await?;
        tracing::info!(line_id = %line.id, code = %line.code, "line created");
        Ok(line)
    }

    /// Applies a partial update; an empty update returns the line unchanged (not audited).
    pub async fn update(
        &self,
        actor: &Actor,
        id: LineId,
        input: UpdateLineInput,
        meta: &RequestMeta,
    ) -> AppResult<Line> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let name = input.name.as_deref().and_then(|raw| v.check("name", LineName::parse(raw)));
        let description = input
            .description
            .as_deref()
            .and_then(|raw| v.check("description", optional_text(raw, DESCRIPTION_MAX_CHARS)));
        let color = input.color.as_deref().and_then(|raw| v.check("color", HexColor::parse(raw)));
        let frequency_minutes = match input.frequency_minutes {
            None => None,
            Some(None) => Some(None),
            Some(Some(raw)) => v.check("frequency_minutes", Frequency::parse(raw)).map(Some),
        };
        let fare_dza = match input.fare_dza {
            None => None,
            Some(None) => Some(None),
            Some(Some(raw)) => v.check("fare_dza", Fare::parse(raw)).map(Some),
        };
        v.into_result()?;

        let mut changes = Map::new();
        if let Some(name) = &name {
            changes.insert("name".into(), json!(name.as_str()));
        }
        if let Some(description) = &description {
            changes.insert("description".into(), json!(description));
        }
        if let Some(color) = &color {
            changes.insert("color".into(), json!(color.as_str()));
        }
        if let Some(frequency) = frequency_minutes {
            changes.insert("frequency_minutes".into(), json!(frequency.map(Frequency::minutes)));
        }
        if let Some(fare) = fare_dza {
            changes.insert("fare_dza".into(), json!(fare.map(Fare::dzd)));
        }
        if let Some(is_active) = input.is_active {
            changes.insert("is_active".into(), json!(is_active));
        }
        let patch = LinePatch {
            name,
            description,
            color,
            frequency_minutes,
            fare_dza,
            is_active: input.is_active,
        };
        if patch.is_empty() {
            return self.existing(id).await;
        }
        let now = self.clock.now();
        let effects = Self::audit(actor, meta, now, "line.update", id, Value::Object(changes));
        self.lines.update(id, patch, now, effects).await
    }

    /// Deletes a line with its stop list and schedules (refused while buses are assigned).
    pub async fn delete(&self, actor: &Actor, id: LineId, meta: &RequestMeta) -> AppResult<()> {
        Self::authorize_write(actor)?;
        let line = self.existing(id).await?;
        let now = self.clock.now();
        let details = json!({ "code": line.code.as_str() });
        let effects = Self::audit(actor, meta, now, "line.delete", id, details);
        self.lines.delete(id, effects).await?;
        tracing::info!(line_id = %id, "line deleted");
        Ok(())
    }

    /// The stops of a visible line by position (inactive stops included: buses pass them).
    pub async fn stops(&self, actor: &Actor, id: LineId) -> AppResult<Vec<LineStop>> {
        self.visible(actor, id).await?;
        self.lines.stops(id).await
    }

    /// Replaces the whole ordered stop list (`(stop_id, time_from_previous_s)` pairs).
    pub async fn replace_stops(
        &self,
        actor: &Actor,
        id: LineId,
        entries: Vec<(StopId, Option<i64>)>,
        meta: &RequestMeta,
    ) -> AppResult<Vec<LineStop>> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let mut parsed = Vec::with_capacity(entries.len());
        for (i, (stop_id, time)) in entries.into_iter().enumerate() {
            let field = format!("stops[{i}].time_from_previous_s");
            let time = match time.map(segment_time).transpose() {
                Ok(time) => time,
                Err(violation) => {
                    v.push(field, violation);
                    None
                }
            };
            parsed.push(StopSequenceEntry { stop_id, time_from_previous_s: time });
        }
        let sequence = v.check_nested("stops", StopSequence::parse(parsed));
        let (Some(sequence), true) = (sequence, v.is_empty()) else {
            return Err(v.into());
        };
        self.existing(id).await?;
        let ids: Vec<StopId> = sequence.entries().iter().map(|e| e.stop_id).collect();
        let known = self.stops.existing(&ids).await?;
        let mut unknown = Violations::new();
        for (i, stop_id) in ids.iter().enumerate() {
            if !known.contains(stop_id) {
                unknown.push(format!("stops[{i}].stop_id"), Violation::UnknownReference);
            }
        }
        unknown.into_result()?;

        let now = self.clock.now();
        let stop_ids: Vec<String> = ids.iter().map(ToString::to_string).collect();
        let details = json!({ "stop_ids": stop_ids });
        let effects = Self::audit(actor, meta, now, "line.stops.replace", id, details);
        self.lines.replace_stops(id, &sequence, now, effects).await
    }

    /// Inserts one stop (default: at the end); later stops shift by one.
    pub async fn add_stop(
        &self,
        actor: &Actor,
        id: LineId,
        input: AddLineStopInput,
        meta: &RequestMeta,
    ) -> AppResult<Vec<LineStop>> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let time = input
            .time_from_previous_s
            .and_then(|raw| v.check("time_from_previous_s", segment_time(raw)));
        if input.position == Some(0) && time.is_some() {
            v.push("time_from_previous_s", Violation::NotAllowed);
        }
        v.into_result()?;
        self.existing(id).await?;
        if !self.stops.existing(&[input.stop_id]).await?.contains(&input.stop_id) {
            return Err(AppError::invalid("stop_id", Violation::UnknownReference));
        }
        let now = self.clock.now();
        let details = json!({ "stop_id": input.stop_id, "position": input.position });
        let effects = Self::audit(actor, meta, now, "line.stops.add", id, details);
        let entry = StopSequenceEntry { stop_id: input.stop_id, time_from_previous_s: time };
        self.lines.add_stop(id, entry, input.position, now, effects).await
    }

    /// Removes one stop; later stops shift back by one.
    pub async fn remove_stop(
        &self,
        actor: &Actor,
        id: LineId,
        stop_id: StopId,
        meta: &RequestMeta,
    ) -> AppResult<Vec<LineStop>> {
        Self::authorize_write(actor)?;
        let now = self.clock.now();
        let details = json!({ "stop_id": stop_id });
        let effects = Self::audit(actor, meta, now, "line.stops.remove", id, details);
        self.lines.remove_stop(id, stop_id, now, effects).await
    }

    /// The route of a visible line; `NotFound("route")` when unset.
    pub async fn route(&self, actor: &Actor, id: LineId) -> AppResult<LineGeometry> {
        self.visible(actor, id).await?;
        self.lines.route(id).await?.ok_or(AppError::NotFound("route"))
    }

    /// Sets the route from GeoJSON positions (`[lng, lat]`).
    pub async fn set_route(
        &self,
        actor: &Actor,
        id: LineId,
        positions: &[[f64; 2]],
        meta: &RequestMeta,
    ) -> AppResult<LineGeometry> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let geometry = v.check_nested("coordinates", LineGeometry::parse(positions));
        let Some(geometry) = geometry else {
            return Err(v.into());
        };
        let now = self.clock.now();
        let details = json!({ "points": geometry.points().len() });
        let effects = Self::audit(actor, meta, now, "line.route.set", id, details);
        self.lines.set_route(id, Some(&geometry), now, effects).await?;
        Ok(geometry)
    }

    /// Removes the route (idempotent; audited only when there was one).
    pub async fn delete_route(
        &self,
        actor: &Actor,
        id: LineId,
        meta: &RequestMeta,
    ) -> AppResult<()> {
        Self::authorize_write(actor)?;
        if !self.existing(id).await?.has_route {
            return Ok(());
        }
        let now = self.clock.now();
        let effects = Self::audit(actor, meta, now, "line.route.delete", id, json!({}));
        self.lines.set_route(id, None, now, effects).await?;
        Ok(())
    }
}
