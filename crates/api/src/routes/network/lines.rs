//! Lines: catalogue reads, administration, ordered stops and route geometry.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::Response;
use dz_app::network::{
    AddLineStopInput, CreateLineInput, LineListQuery as LineFilterInput, UpdateLineInput,
};
use dz_app::AppError;
use dz_app::pagination::PageRequest;
use dz_domain::ids::{LineId, StopId};

use super::created;
use crate::dto::network::{
    AddLineStopRequest, CreateLineRequest, LineDto, LineListQuery, LineStopDto,
    ReplaceLineStopsRequest, RouteDto, UpdateLineRequest,
};
use crate::dto::{ItemList, Paginated};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{
    Meta, PathId, PathIds, RequirePermission, ValidatedJson, ValidatedQuery, perm,
};
use crate::state::AppState;

/// List lines (newest first). Active lines only, unless the caller administers lines.
#[utoipa::path(
    get, path = "/lines", tag = "lines",
    security((), ("bearer" = []), ("api_key" = [])),
    params(LineListQuery),
    responses(
        (status = 200, description = "A page of lines", body = Paginated<LineDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "`is_active` filter without being signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "`is_active` filter without `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid filters (e.g. `q` shorter than 2 characters)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_lines(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    ValidatedQuery(query): ValidatedQuery<LineListQuery>,
) -> Result<Json<Paginated<LineDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let filter = LineFilterInput {
        q: query.q,
        stop_id: query.stop_id.map(StopId::from_uuid),
        is_active: query.is_active,
    };
    let lines = state.lines.list(&guard.actor, filter, page).await?;
    Ok(Json(Paginated::from_page(lines, LineDto::from)))
}

/// Create a line (audited).
#[utoipa::path(
    post, path = "/lines", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    request_body = CreateLineRequest,
    responses(
        (status = 201, description = "Line created (`Location` points to it)", body = LineDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Another line has this code (`line_code_taken`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn create_line(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    ValidatedJson(body): ValidatedJson<CreateLineRequest>,
) -> Result<Response, ApiError> {
    let input = CreateLineInput {
        code: body.code,
        name: body.name,
        description: body.description,
        color: body.color,
        frequency_minutes: body.frequency_minutes,
        fare_dza: body.fare_dza,
        is_active: body.is_active,
    };
    let line = state.lines.create(&guard.actor, input, &meta).await?;
    let location = format!("/api/v1/lines/{}", line.id);
    Ok(created(&location, LineDto::from(line)))
}

/// One line, with its number of stops and whether it has a route.
#[utoipa::path(
    get, path = "/lines/{id}", tag = "lines",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 200, description = "The line", body = LineDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) line", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_line(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<LineDto>, ApiError> {
    let line = state.lines.get(&guard.actor, LineId::from_uuid(id)).await?;
    Ok(Json(line.into()))
}

/// Update a line partially (audited). The code cannot change; `is_active` activates or
/// deactivates the line.
#[utoipa::path(
    patch, path = "/lines/{id}", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    request_body = UpdateLineRequest,
    responses(
        (status = 200, description = "The updated line", body = LineDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields (`code` is `unknown_field`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_line(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<UpdateLineRequest>,
) -> Result<Json<LineDto>, ApiError> {
    let input = UpdateLineInput {
        name: body.name,
        description: body.description,
        color: body.color,
        frequency_minutes: body.frequency_minutes,
        fare_dza: body.fare_dza,
        is_active: body.is_active,
    };
    let line = state.lines.update(&guard.actor, LineId::from_uuid(id), input, &meta).await?;
    Ok(Json(line.into()))
}

/// Delete a line with its stop list and schedules (audited); refused while buses are assigned
/// to it.
#[utoipa::path(
    delete, path = "/lines/{id}", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 204, description = "Deleted"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Buses are assigned to the line (`line_in_use`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn delete_line(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.lines.delete(&guard.actor, LineId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// The stops of a line by position (not paginated: at most 200). Inactive stops are listed
/// with `is_active: false`.
#[utoipa::path(
    get, path = "/lines/{id}/stops", tag = "lines",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 200, description = "The ordered stops", body = ItemList<LineStopDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) line", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn line_stops(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<ItemList<LineStopDto>>, ApiError> {
    let stops = state.lines.stops(&guard.actor, LineId::from_uuid(id)).await?;
    Ok(Json(ItemList::from_items(stops, LineStopDto::from)))
}

/// Replace the whole ordered stop list atomically (audited). Distances from the previous stop
/// are recomputed.
#[utoipa::path(
    put, path = "/lines/{id}/stops", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    request_body = ReplaceLineStopsRequest,
    responses(
        (status = 200, description = "The new ordered stops", body = ItemList<LineStopDto>),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "More than 200 stops, a repeated (`duplicate`) or unknown (`unknown_reference`) stop, or a segment time on the first stop (`not_allowed`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn replace_line_stops(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<ReplaceLineStopsRequest>,
) -> Result<Json<ItemList<LineStopDto>>, ApiError> {
    let entries = body
        .stops
        .into_iter()
        .map(|e| (StopId::from_uuid(e.stop_id), e.time_from_previous_s))
        .collect();
    let stops =
        state.lines.replace_stops(&guard.actor, LineId::from_uuid(id), entries, &meta).await?;
    Ok(Json(ItemList::from_items(stops, LineStopDto::from)))
}

/// Insert one stop into a line (audited); later stops shift by one.
#[utoipa::path(
    post, path = "/lines/{id}/stops", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    request_body = AddLineStopRequest,
    responses(
        (status = 201, description = "The new ordered stops", body = ItemList<LineStopDto>),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The stop is already on the line (`stop_already_on_line`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Unknown stop, position past the end, line full, or a segment time at position 0", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn add_line_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<AddLineStopRequest>,
) -> Result<Response, ApiError> {
    let input = AddLineStopInput {
        stop_id: StopId::from_uuid(body.stop_id),
        position: body.position,
        time_from_previous_s: body.time_from_previous_s,
    };
    let stops = state.lines.add_stop(&guard.actor, LineId::from_uuid(id), input, &meta).await?;
    let location = format!("/api/v1/lines/{id}/stops");
    Ok(created(&location, ItemList::from_items(stops, LineStopDto::from)))
}

/// Remove a stop from a line (audited); later stops shift back and the distance of the next
/// stop is recomputed.
#[utoipa::path(
    delete, path = "/lines/{id}/stops/{stop_id}", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(
        ("id" = Uuid, Path, description = "Line id"),
        ("stop_id" = Uuid, Path, description = "Stop id"),
    ),
    responses(
        (status = 204, description = "Removed"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line, or the stop is not on it", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn remove_line_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathIds(id, stop_id): PathIds,
) -> Result<StatusCode, ApiError> {
    let (line, stop) = (LineId::from_uuid(id), StopId::from_uuid(stop_id));
    state.lines.remove_stop(&guard.actor, line, stop, &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// The route of a line as a GeoJSON `LineString`.
#[utoipa::path(
    get, path = "/lines/{id}/route", tag = "lines",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 200, description = "The route", body = RouteDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) line, or no route set", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_line_route(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<RouteDto>, ApiError> {
    let route = state.lines.route(&guard.actor, LineId::from_uuid(id)).await?;
    Ok(Json(route.into()))
}

/// Set the route of a line (audited). Replaces the legacy route segments, which any user could
/// write (L-04).
#[utoipa::path(
    put, path = "/lines/{id}/route", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    request_body = RouteDto,
    responses(
        (status = 200, description = "The stored route", body = RouteDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Not a valid `LineString`: 2–10 000 positions in range, no repeated consecutive position", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn set_line_route(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<RouteDto>,
) -> Result<Json<RouteDto>, ApiError> {
    let positions = body.positions().map_err(AppError::from)?;
    let line = LineId::from_uuid(id);
    let route = state.lines.set_route(&guard.actor, line, &positions, &meta).await?;
    Ok(Json(route.into()))
}

/// Remove the route of a line (idempotent, audited).
#[utoipa::path(
    delete, path = "/lines/{id}/route", tag = "lines",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Line id")),
    responses(
        (status = 204, description = "The line has no route any more"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `line:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such line", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn delete_line_route(
    State(state): State<AppState>,
    guard: RequirePermission<perm::LineWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.lines.delete_route(&guard.actor, LineId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}
