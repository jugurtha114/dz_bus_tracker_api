//! Schedule use-cases: the weekly service windows of a line. Active schedules of a line may not
//! overlap on the same day (enforced by the `schedules_no_overlap` exclusion constraint).

use std::sync::Arc;

use dz_domain::authz::{Action, Actor, CatalogResource, Policy};
use dz_domain::ids::{LineId, ScheduleId};
use dz_domain::network::{Frequency, Schedule, TimeOfDay, TimeWindow, Weekday};
use dz_domain::Violations;
use serde_json::{Map, Value, json};

use super::ports::{LineRepository, NewSchedule, SchedulePatch, ScheduleRepository};
use super::sees_inactive;
use crate::audit;
use crate::error::{AppError, AppResult};
use crate::ports::{Clock, RequestMeta, WriteEffects};

/// Raw input of a new schedule.
#[derive(Debug, Clone, Default)]
pub struct CreateScheduleInput {
    pub day_of_week: i64,
    /// `HH:MM`.
    pub start_time: String,
    /// `HH:MM`, after `start_time`.
    pub end_time: String,
    pub frequency_minutes: i64,
    pub is_active: Option<bool>,
}

/// Raw changes to a schedule; absent fields are unchanged.
#[derive(Debug, Clone, Default)]
pub struct UpdateScheduleInput {
    pub day_of_week: Option<i64>,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub frequency_minutes: Option<i64>,
    pub is_active: Option<bool>,
}

pub struct ScheduleService {
    schedules: Arc<dyn ScheduleRepository>,
    lines: Arc<dyn LineRepository>,
    clock: Arc<dyn Clock>,
}

impl ScheduleService {
    #[must_use]
    pub fn new(
        schedules: Arc<dyn ScheduleRepository>,
        lines: Arc<dyn LineRepository>,
        clock: Arc<dyn Clock>,
    ) -> Self {
        Self { schedules, lines, clock }
    }

    fn authorize_write(actor: &Actor) -> AppResult<()> {
        Policy::authorize(actor, &Action::WriteCatalog { resource: CatalogResource::Schedule })?;
        Ok(())
    }

    fn audit(
        actor: &Actor,
        meta: &RequestMeta,
        now: chrono::DateTime<chrono::Utc>,
        action: &'static str,
        id: ScheduleId,
        details: Value,
    ) -> WriteEffects {
        let entry = audit::entry(actor, meta, now, action, "schedule", id.to_string(), details);
        WriteEffects::audited(entry)
    }

    /// Whether the line is visible to the actor: active, or the actor maintains lines or
    /// schedules.
    async fn line_visible(&self, actor: &Actor, line_id: LineId) -> AppResult<bool> {
        let writer = sees_inactive(actor, CatalogResource::Line)
            || sees_inactive(actor, CatalogResource::Schedule);
        Ok(self.lines.find(line_id).await?.is_some_and(|line| line.is_active || writer))
    }

    /// Schedules of a visible line by day and start time (inactive ones for schedule writers).
    pub async fn list_for_line(&self, actor: &Actor, line_id: LineId) -> AppResult<Vec<Schedule>> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        if !self.line_visible(actor, line_id).await? {
            return Err(AppError::NotFound("line"));
        }
        let include_inactive = sees_inactive(actor, CatalogResource::Schedule);
        self.schedules.list_for_line(line_id, include_inactive).await
    }

    /// A schedule; inactive schedules and schedules of inactive lines are hidden from
    /// non-writers.
    pub async fn get(&self, actor: &Actor, id: ScheduleId) -> AppResult<Schedule> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        let schedule = self.schedules.find(id).await?.ok_or(AppError::NotFound("schedule"))?;
        let visible = sees_inactive(actor, CatalogResource::Schedule)
            || (schedule.is_active && self.line_visible(actor, schedule.line_id).await?);
        if visible { Ok(schedule) } else { Err(AppError::NotFound("schedule")) }
    }

    /// Adds a schedule to a line (the only way to create one, L-23).
    pub async fn create(
        &self,
        actor: &Actor,
        line_id: LineId,
        input: CreateScheduleInput,
        meta: &RequestMeta,
    ) -> AppResult<Schedule> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let day = v.check("day_of_week", Weekday::parse(input.day_of_week));
        let start = v.check("start_time", TimeOfDay::parse(&input.start_time));
        let end = v.check("end_time", TimeOfDay::parse(&input.end_time));
        let frequency = v.check("frequency_minutes", Frequency::parse(input.frequency_minutes));
        let window = match (start, end) {
            (Some(start), Some(end)) => v.check("end_time", TimeWindow::new(start, end)),
            _ => None,
        };
        let (Some(day), Some(window), Some(frequency)) = (day, window, frequency) else {
            return Err(v.into());
        };
        v.into_result()?;
        if self.lines.find(line_id).await?.is_none() {
            return Err(AppError::NotFound("line"));
        }

        let id = ScheduleId::generate();
        let now = self.clock.now();
        let is_active = input.is_active.unwrap_or(true);
        let details = json!({
            "line_id": line_id,
            "day_of_week": day.iso(),
            "start_time": window.start().to_string(),
            "end_time": window.end().to_string(),
            "frequency_minutes": frequency.minutes(),
            "is_active": is_active,
        });
        let effects = Self::audit(actor, meta, now, "schedule.create", id, details);
        let new =
            NewSchedule { id, line_id, day, window, frequency, is_active, created_at: now };
        self.schedules.insert(new, effects).await
    }

    /// Applies a partial update with the same validation and overlap rules as creation.
    pub async fn update(
        &self,
        actor: &Actor,
        id: ScheduleId,
        input: UpdateScheduleInput,
        meta: &RequestMeta,
    ) -> AppResult<Schedule> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let day = input.day_of_week.and_then(|raw| v.check("day_of_week", Weekday::parse(raw)));
        let mut time = |field, raw: Option<&str>| {
            raw.and_then(|raw| v.check(field, TimeOfDay::parse(raw)))
        };
        let start = time("start_time", input.start_time.as_deref());
        let end = time("end_time", input.end_time.as_deref());
        let frequency = input
            .frequency_minutes
            .and_then(|raw| v.check("frequency_minutes", Frequency::parse(raw)));
        v.into_result()?;
        let current = self.schedules.find(id).await?.ok_or(AppError::NotFound("schedule"))?;
        let patch = SchedulePatch { day, start, end, frequency, is_active: input.is_active };
        if patch.is_empty() {
            return Ok(current);
        }
        // The resulting window must be valid; the database re-checks it against the row it
        // actually updates (`schedules_time_order`).
        let window = TimeWindow::new(
            start.unwrap_or(current.window.start()),
            end.unwrap_or(current.window.end()),
        )
        .map_err(|violation| AppError::invalid("end_time", violation))?;

        let mut changes = Map::new();
        if let Some(day) = day {
            changes.insert("day_of_week".into(), json!(day.iso()));
        }
        if start.is_some() || end.is_some() {
            changes.insert("start_time".into(), json!(window.start().to_string()));
            changes.insert("end_time".into(), json!(window.end().to_string()));
        }
        if let Some(frequency) = frequency {
            changes.insert("frequency_minutes".into(), json!(frequency.minutes()));
        }
        if let Some(is_active) = input.is_active {
            changes.insert("is_active".into(), json!(is_active));
        }
        let now = self.clock.now();
        let effects = Self::audit(actor, meta, now, "schedule.update", id, Value::Object(changes));
        self.schedules.update(id, patch, now, effects).await
    }

    pub async fn delete(&self, actor: &Actor, id: ScheduleId, meta: &RequestMeta) -> AppResult<()> {
        Self::authorize_write(actor)?;
        let schedule = self.schedules.find(id).await?.ok_or(AppError::NotFound("schedule"))?;
        let now = self.clock.now();
        let details = json!({ "line_id": schedule.line_id });
        let effects = Self::audit(actor, meta, now, "schedule.delete", id, details);
        self.schedules.delete(id, effects).await
    }
}
