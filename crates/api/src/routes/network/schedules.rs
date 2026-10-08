//! Schedules: the weekly service windows of a line.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::Response;
use dz_app::network::{CreateScheduleInput, UpdateScheduleInput};
use dz_domain::ids::{LineId, ScheduleId};

use super::created;
use crate::dto::ItemList;
use crate::dto::network::{CreateScheduleRequest, ScheduleDto, UpdateScheduleRequest};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{Meta, PathId, RequirePermission, ValidatedJson, perm};
use crate::state::AppState;

/// The schedules of a line by day and start time (not paginated). Active schedules only,
/// unless the caller administers schedules.
#[utoipa::path(
    get, path = "/lines/{id}/schedules", tag = "schedules",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 200, description = "The schedules of the line", body = ItemList<ScheduleDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) line", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_line_schedules(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<ItemList<ScheduleDto>>, ApiError> {
    let schedules = state.schedules.list_for_line(&guard.actor, LineId::from_uuid(id)).await?;
    Ok(Json(ItemList::from_items(schedules, ScheduleDto::from)))
}

/// Add a schedule to a line (audited). This is the only way to create a schedule.
#[utoipa::path(
    post, path = "/lines/{id}/schedules", tag = "schedules",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    request_body = CreateScheduleRequest,
    responses(
        (status = 201, description = "Schedule created (`Location` points to it)", body = ScheduleDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `schedule:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Overlaps an active schedule of the line on that day (`schedule_overlap`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields (e.g. `end_time` not after `start_time`: `must_be_after`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn create_schedule(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ScheduleWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<CreateScheduleRequest>,
) -> Result<Response, ApiError> {
    let input = CreateScheduleInput {
        day_of_week: body.day_of_week,
        start_time: body.start_time,
        end_time: body.end_time,
        frequency_minutes: body.frequency_minutes,
        is_active: body.is_active,
    };
    let schedule =
        state.schedules.create(&guard.actor, LineId::from_uuid(id), input, &meta).await?;
    let location = format!("/api/v1/schedules/{}", schedule.id);
    Ok(created(&location, ScheduleDto::from(schedule)))
}

/// One schedule. Inactive schedules, and schedules of inactive lines, are only visible to
/// schedule administrators.
#[utoipa::path(
    get, path = "/schedules/{id}", tag = "schedules",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Schedule id")),
    responses(
        (status = 200, description = "The schedule", body = ScheduleDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) schedule", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_schedule(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<ScheduleDto>, ApiError> {
    let schedule = state.schedules.get(&guard.actor, ScheduleId::from_uuid(id)).await?;
    Ok(Json(schedule.into()))
}

/// Update a schedule partially (audited), with the same validation and overlap rules as
/// creation.
#[utoipa::path(
    patch, path = "/schedules/{id}", tag = "schedules",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Schedule id")),
    request_body = UpdateScheduleRequest,
    responses(
        (status = 200, description = "The updated schedule", body = ScheduleDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `schedule:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such schedule", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Would overlap an active schedule (`schedule_overlap`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_schedule(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ScheduleWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<UpdateScheduleRequest>,
) -> Result<Json<ScheduleDto>, ApiError> {
    let input = UpdateScheduleInput {
        day_of_week: body.day_of_week,
        start_time: body.start_time,
        end_time: body.end_time,
        frequency_minutes: body.frequency_minutes,
        is_active: body.is_active,
    };
    let schedule =
        state.schedules.update(&guard.actor, ScheduleId::from_uuid(id), input, &meta).await?;
    Ok(Json(schedule.into()))
}

/// Delete a schedule (audited).
#[utoipa::path(
    delete, path = "/schedules/{id}", tag = "schedules",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Schedule id")),
    responses(
        (status = 204, description = "Deleted"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `schedule:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such schedule", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn delete_schedule(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ScheduleWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.schedules.delete(&guard.actor, ScheduleId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}
