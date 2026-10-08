//! Stops: catalogue reads, nearby search, administration and photos.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::Response;
use dz_app::network::{
    CreateStopInput, NearbyQuery as NearbyInput, StopListQuery as StopFilterInput,
    UpdateStopInput,
};
use dz_app::pagination::PageRequest;
use dz_domain::ids::{LineId, StopId, UploadId};

use super::created;
use crate::dto::network::{
    CreateStopRequest, LineDto, NearbyQuery, NearbyStopDto, SetPhotoRequest, StopDto,
    StopListQuery, UpdateStopRequest,
};
use crate::dto::{ItemList, Paginated};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{Meta, PathId, RequirePermission, ValidatedJson, ValidatedQuery, perm};
use crate::state::AppState;

/// List stops (newest first). Active stops only, unless the caller administers stops.
#[utoipa::path(
    get, path = "/stops", tag = "stops",
    security((), ("bearer" = []), ("api_key" = [])),
    params(StopListQuery),
    responses(
        (status = 200, description = "A page of stops", body = Paginated<StopDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "`is_active` filter without being signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "`is_active` filter without `stop:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid filters (e.g. `q` shorter than 2 characters)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_stops(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    ValidatedQuery(query): ValidatedQuery<StopListQuery>,
) -> Result<Json<Paginated<StopDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let filter = StopFilterInput {
        q: query.q,
        wilaya: query.wilaya,
        commune: query.commune,
        line_id: query.line_id.map(LineId::from_uuid),
        is_active: query.is_active,
    };
    let stops = state.stops.list(&guard.actor, filter, page).await?;
    Ok(Json(Paginated::from_page(stops, StopDto::from)))
}

/// Active stops around a point, nearest first (not paginated).
#[utoipa::path(
    get, path = "/stops/nearby", tag = "stops",
    security((), ("bearer" = []), ("api_key" = [])),
    params(NearbyQuery),
    responses(
        (status = 200, description = "Stops within the radius, with their distance", body = ItemList<NearbyStopDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 422, description = "Missing or out-of-range coordinates, radius or limit", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn nearby_stops(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    ValidatedQuery(query): ValidatedQuery<NearbyQuery>,
) -> Result<Json<ItemList<NearbyStopDto>>, ApiError> {
    let input = NearbyInput {
        lat: query.lat,
        lng: query.lng,
        radius_m: query.radius_m,
        limit: query.limit,
    };
    let found = state.stops.nearby(&guard.actor, input).await?;
    Ok(Json(ItemList::from_items(found, NearbyStopDto::from)))
}

/// Create a stop (audited).
#[utoipa::path(
    post, path = "/stops", tag = "stops",
    security(("bearer" = []), ("api_key" = [])),
    request_body = CreateStopRequest,
    responses(
        (status = 201, description = "Stop created (`Location` points to it)", body = StopDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `stop:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn create_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::StopWrite>,
    Meta(meta): Meta,
    ValidatedJson(body): ValidatedJson<CreateStopRequest>,
) -> Result<Response, ApiError> {
    let input = CreateStopInput {
        name: body.name,
        location: (body.location.lat, body.location.lng),
        address: body.address,
        wilaya: body.wilaya,
        commune: body.commune,
        description: body.description,
        features: body.features,
        is_active: body.is_active,
    };
    let view = state.stops.create(&guard.actor, input, &meta).await?;
    let location = format!("/api/v1/stops/{}", view.stop.id);
    Ok(created(&location, StopDto::from(view)))
}

/// One stop. Inactive stops are only visible to stop administrators.
#[utoipa::path(
    get, path = "/stops/{id}", tag = "stops",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    responses(
        (status = 200, description = "The stop", body = StopDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) stop", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<StopDto>, ApiError> {
    let view = state.stops.get(&guard.actor, StopId::from_uuid(id)).await?;
    Ok(Json(view.into()))
}

/// Update a stop partially (audited). Moving a stop recomputes the distances of its lines.
#[utoipa::path(
    patch, path = "/stops/{id}", tag = "stops",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    request_body = UpdateStopRequest,
    responses(
        (status = 200, description = "The updated stop", body = StopDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `stop:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such stop", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Lines kept gaining the moved stop concurrently (`stale_state`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::StopWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<UpdateStopRequest>,
) -> Result<Json<StopDto>, ApiError> {
    let input = UpdateStopInput {
        name: body.name,
        location: body.location.map(|l| (l.lat, l.lng)),
        address: body.address,
        wilaya: body.wilaya,
        commune: body.commune,
        description: body.description,
        features: body.features,
        is_active: body.is_active,
    };
    let view = state.stops.update(&guard.actor, StopId::from_uuid(id), input, &meta).await?;
    Ok(Json(view.into()))
}

/// Delete a stop that no line serves (audited). Its photo is deleted in the background.
#[utoipa::path(
    delete, path = "/stops/{id}", tag = "stops",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    responses(
        (status = 204, description = "Deleted"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `stop:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such stop", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "A line still serves the stop (`stop_in_use`), or its photo changed concurrently (`stale_state`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn delete_stop(
    State(state): State<AppState>,
    guard: RequirePermission<perm::StopWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.stops.delete(&guard.actor, StopId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Lines serving a stop, ordered by code (inactive lines for line administrators only).
#[utoipa::path(
    get, path = "/stops/{id}/lines", tag = "stops",
    security((), ("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    responses(
        (status = 200, description = "The lines serving the stop", body = ItemList<LineDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 404, description = "No such (visible) stop", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn stop_lines(
    State(state): State<AppState>,
    guard: RequirePermission<perm::CatalogRead>,
    PathId(id): PathId,
) -> Result<Json<ItemList<LineDto>>, ApiError> {
    let lines = state.stops.lines(&guard.actor, StopId::from_uuid(id)).await?;
    Ok(Json(ItemList::from_items(lines, LineDto::from)))
}

/// Set the photo of a stop to a completed upload (purpose `stop_photo`, audited). The previous
/// photo is deleted in the background. Uploads belong to a signed-in user: API keys cannot
/// attach photos.
#[utoipa::path(
    put, path = "/stops/{id}/photo", tag = "stops",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    request_body = SetPhotoRequest,
    responses(
        (status = 200, description = "The stop with its `photo_url`", body = StopDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `stop:write`, or an API key", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such stop", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The upload was attached concurrently (`upload_already_used`), or the photo changed concurrently (`stale_state`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "`upload_id` is not a usable `stop_photo` upload of the caller (`invalid_upload`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 503, description = "File storage is not available (`storage_unavailable`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn set_stop_photo(
    State(state): State<AppState>,
    guard: RequirePermission<perm::StopWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<SetPhotoRequest>,
) -> Result<Json<StopDto>, ApiError> {
    let upload = UploadId::from_uuid(body.upload_id);
    let view = state.stops.set_photo(&guard.actor, StopId::from_uuid(id), upload, &meta).await?;
    Ok(Json(view.into()))
}

/// Remove the photo of a stop (idempotent, audited). The file is deleted in the background.
#[utoipa::path(
    delete, path = "/stops/{id}/photo", tag = "stops",
    security(("bearer" = []), ("api_key" = [])),
    params(("id" = Uuid, Path, description = "Stop id")),
    responses(
        (status = 204, description = "The stop has no photo any more"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `stop:write`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such stop", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The photo changed concurrently (`stale_state`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 503, description = "File storage is not available (`storage_unavailable`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn delete_stop_photo(
    State(state): State<AppState>,
    guard: RequirePermission<perm::StopWrite>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.stops.remove_photo(&guard.actor, StopId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}
