//! `/api/v1/drivers`: driver applications, the driver's own profile, reviews and the status
//! history.
//!
//! Profiles contain identity documents: the driver sees their own, reviewers (`driver:read`)
//! see every profile, and anyone else gets `404` for a profile id (its existence is not
//! revealed). Reviews need `driver:review`, follow the driver state machine (`409
//! invalid_transition` otherwise) and are audited. An approval names the version of the
//! profile the reviewer examined (`409 stale_state` once the documents changed).

use axum::Json;
use axum::extract::State;
use axum::response::Response;
use dz_app::drivers::{ApplyInput, DriverListQuery as DriverFilterInput, Review, UpdateDriverInput};
use dz_app::pagination::PageRequest;
use dz_domain::Violation;
use dz_domain::ids::{DriverId, UploadId};

use super::created;
use crate::dto::drivers::{
    ApproveDriverRequest, AvailabilityRequest, DriverApplicationRequest, DriverDto,
    DriverListQuery, DriverStatusChangeDto, ReviewReasonRequest, UpdateDriverRequest,
};
use crate::dto::{PageQuery, Paginated};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{Meta, PathId, RequirePermission, ValidatedJson, ValidatedQuery, perm};
use crate::state::AppState;

/// Apply to become a driver. The profile is created for the caller with both identity
/// documents, in one step; reviewers are notified. Upload the documents first.
#[utoipa::path(
    post, path = "/drivers/applications", tag = "drivers",
    security(("bearer" = [])),
    request_body = DriverApplicationRequest,
    responses(
        (status = 201, description = "Application submitted (`Location` points to the profile)", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:apply` (e.g. administrators, API keys)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The caller already has a profile (`driver_profile_exists`), the identity card or licence number belongs to another profile (`id_card_taken`, `license_taken`), or an upload was attached concurrently (`upload_already_used`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields, or unusable uploads (`invalid_upload`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 503, description = "File storage is not available (`storage_unavailable`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn apply(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverApply>,
    ValidatedJson(body): ValidatedJson<DriverApplicationRequest>,
) -> Result<Response, ApiError> {
    let input = ApplyInput {
        phone_number: body.phone_number,
        id_card_number: body.id_card_number,
        id_card_photo_upload_id: UploadId::from_uuid(body.id_card_photo_upload_id),
        driver_license_number: body.driver_license_number,
        driver_license_photo_upload_id: UploadId::from_uuid(body.driver_license_photo_upload_id),
        years_of_experience: body.years_of_experience,
    };
    let view = state.drivers.apply(&guard.actor, input).await?;
    let location = format!("/api/v1/drivers/{}", view.record.driver.id);
    Ok(created(&location, DriverDto::from(view)))
}

/// The caller's driver profile.
#[utoipa::path(
    get, path = "/drivers/me", tag = "drivers",
    security(("bearer" = [])),
    responses(
        (status = 200, description = "The caller's profile", body = DriverDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys have no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "The caller has no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_my_profile(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AccountSelfManage>,
) -> Result<Json<DriverDto>, ApiError> {
    Ok(Json(state.drivers.me(&guard.actor).await?.into()))
}

/// Update the caller's driver profile. A new identity document (number or photo) sends an
/// approved profile back to review and makes the driver unavailable; replaced photos are
/// deleted in the background.
#[utoipa::path(
    patch, path = "/drivers/me", tag = "drivers",
    security(("bearer" = [])),
    request_body = UpdateDriverRequest,
    responses(
        (status = 200, description = "The updated profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys have no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "The caller has no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "Number of another profile (`id_card_taken`, `license_taken`), upload attached concurrently (`upload_already_used`), or profile changed concurrently (`stale_state`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields, or unusable uploads (`invalid_upload`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 503, description = "File storage is not available (`storage_unavailable`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_my_profile(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AccountSelfManage>,
    ValidatedJson(body): ValidatedJson<UpdateDriverRequest>,
) -> Result<Json<DriverDto>, ApiError> {
    let input = UpdateDriverInput {
        phone_number: body.phone_number,
        years_of_experience: body.years_of_experience,
        id_card_number: body.id_card_number,
        id_card_photo_upload_id: body.id_card_photo_upload_id.map(UploadId::from_uuid),
        driver_license_number: body.driver_license_number,
        driver_license_photo_upload_id: body
            .driver_license_photo_upload_id
            .map(UploadId::from_uuid),
    };
    Ok(Json(state.drivers.update_me(&guard.actor, input).await?.into()))
}

/// Set the caller's availability for service (approved drivers only).
#[utoipa::path(
    put, path = "/drivers/me/availability", tag = "drivers",
    security(("bearer" = [])),
    request_body = AvailabilityRequest,
    responses(
        (status = 200, description = "The updated profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys have no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "The caller has no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The driver is not approved (`invalid_state`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid body", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn set_my_availability(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AccountSelfManage>,
    ValidatedJson(body): ValidatedJson<AvailabilityRequest>,
) -> Result<Json<DriverDto>, ApiError> {
    let view = state.drivers.set_availability(&guard.actor, body.is_available).await?;
    Ok(Json(view.into()))
}

/// Apply again after a rejection (`rejected → pending`); reviewers are notified.
#[utoipa::path(
    post, path = "/drivers/me/reapply", tag = "drivers",
    security(("bearer" = [])),
    responses(
        (status = 200, description = "The profile, pending again", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:apply`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "The caller has no driver profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The profile is not rejected (`invalid_transition`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn reapply(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverApply>,
) -> Result<Json<DriverDto>, ApiError> {
    Ok(Json(state.drivers.reapply(&guard.actor).await?.into()))
}

/// Every driver profile, newest first (reviewers).
#[utoipa::path(
    get, path = "/drivers", tag = "drivers",
    security(("bearer" = [])),
    params(DriverListQuery),
    responses(
        (status = 200, description = "A page of profiles", body = Paginated<DriverDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:read`", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid filters", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_drivers(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverRead>,
    ValidatedQuery(query): ValidatedQuery<DriverListQuery>,
) -> Result<Json<Paginated<DriverDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let filter = DriverFilterInput {
        status: query.status.map(Into::into),
        is_available: query.is_available,
    };
    let drivers = state.drivers.list(&guard.actor, filter, page).await?;
    Ok(Json(Paginated::from_page(drivers, DriverDto::from)))
}

/// One driver profile: the caller's own, or any for reviewers (`driver:read`).
#[utoipa::path(
    get, path = "/drivers/{id}", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id")),
    responses(
        (status = 200, description = "The profile", body = DriverDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys cannot read driver profiles", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile, or someone else's", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_driver(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AccountSelfManage>,
    PathId(id): PathId,
) -> Result<Json<DriverDto>, ApiError> {
    Ok(Json(state.drivers.get(&guard.actor, DriverId::from_uuid(id)).await?.into()))
}

/// The status history of a profile, newest first, with the author and reason of each change
/// (same visibility as the profile).
#[utoipa::path(
    get, path = "/drivers/{id}/status-history", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id"), PageQuery),
    responses(
        (status = 200, description = "A page of status changes", body = Paginated<DriverStatusChangeDto>),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys cannot read driver profiles", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile, or someone else's", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid cursor or limit", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn status_history(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AccountSelfManage>,
    PathId(id): PathId,
    ValidatedQuery(query): ValidatedQuery<PageQuery>,
) -> Result<Json<Paginated<DriverStatusChangeDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let history = state.drivers.status_history(&guard.actor, DriverId::from_uuid(id), page).await?;
    Ok(Json(Paginated::from_page(history, DriverStatusChangeDto::from)))
}

/// Applies a review decision to the profile `id`.
async fn decide(
    state: &AppState,
    guard: &RequirePermission<perm::DriverReview>,
    meta: &dz_app::ports::RequestMeta,
    id: uuid::Uuid,
    review: Review,
) -> Result<Json<DriverDto>, ApiError> {
    let view = state.drivers.review(&guard.actor, DriverId::from_uuid(id), review, meta).await?;
    Ok(Json(view.into()))
}

/// Approve a pending application (audited). The applicant gets the `driver` role, effective at
/// their next token refresh, and is notified. The approval is bound to the version of the
/// profile the reviewer examined (`expected_updated_at`): if the profile changed since, e.g.
/// the applicant replaced a document, nothing changes and the profile must be reviewed again.
#[utoipa::path(
    post, path = "/drivers/{id}/approve", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id")),
    request_body = ApproveDriverRequest,
    responses(
        (status = 200, description = "The approved profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:review`, or the caller's own profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The profile is not pending (`invalid_transition`), or it changed since the reviewer read it (`stale_state`: read it again and review the current documents)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Missing or invalid `expected_updated_at`", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn approve(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverReview>,
    Meta(meta): Meta,
    PathId(id): PathId,
    body: Option<ValidatedJson<ApproveDriverRequest>>,
) -> Result<Json<DriverDto>, ApiError> {
    // Approvals used to have no body: callers that send none learn what is now required.
    let Some(ValidatedJson(body)) = body else {
        return Err(ApiError::field("expected_updated_at", Violation::Required));
    };
    let review = Review::Approve { expected_updated_at: body.expected_updated_at };
    decide(&state, &guard, &meta, id, review).await
}

/// Reject a pending application with a reason (audited); the applicant is notified and may
/// re-apply.
#[utoipa::path(
    post, path = "/drivers/{id}/reject", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id")),
    request_body = ReviewReasonRequest,
    responses(
        (status = 200, description = "The rejected profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:review`, or the caller's own profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The profile is not pending (`invalid_transition`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Missing or too long `reason`", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn reject(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverReview>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<ReviewReasonRequest>,
) -> Result<Json<DriverDto>, ApiError> {
    decide(&state, &guard, &meta, id, Review::Reject { reason: body.reason }).await
}

/// Suspend an approved driver with a reason (audited). In the same transaction the driver
/// becomes unavailable and all their buses are taken off duty; the driver is notified and
/// keeps the `driver` role (to follow their status).
#[utoipa::path(
    post, path = "/drivers/{id}/suspend", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id")),
    request_body = ReviewReasonRequest,
    responses(
        (status = 200, description = "The suspended profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:review`, or the caller's own profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The driver is not approved (`invalid_transition`)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Missing or too long `reason`", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn suspend(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverReview>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<ReviewReasonRequest>,
) -> Result<Json<DriverDto>, ApiError> {
    decide(&state, &guard, &meta, id, Review::Suspend { reason: body.reason }).await
}

/// Reinstate a suspended driver (audited); the driver is notified.
#[utoipa::path(
    post, path = "/drivers/{id}/reinstate", tag = "drivers",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Driver id")),
    responses(
        (status = 200, description = "The approved profile", body = DriverDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Missing `driver:review`, or the caller's own profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such profile", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 409, description = "The driver is not suspended (`invalid_transition`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn reinstate(
    State(state): State<AppState>,
    guard: RequirePermission<perm::DriverReview>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<Json<DriverDto>, ApiError> {
    decide(&state, &guard, &meta, id, Review::Reinstate).await
}
