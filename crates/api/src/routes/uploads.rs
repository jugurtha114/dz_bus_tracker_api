//! `/api/v1/uploads`: presigned uploads to private object storage.

use axum::Json;
use axum::extract::State;
use axum::http::header::{CACHE_CONTROL, LOCATION};
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use dz_domain::ids::UploadId;

use crate::dto::{CreateUploadRequest, UploadDto, UploadStatusViewDto};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{CurrentUser, PathId, ValidatedJson};
use crate::state::AppState;

/// Request an upload URL. The file is then sent directly to storage with the returned request
/// (type and exact size are signed) and attached to a resource by id before `expires_at`.
/// Uploads belong to a signed-in user: API keys cannot request them.
#[utoipa::path(
    post, path = "/uploads", tag = "uploads",
    security(("bearer" = [])),
    request_body = CreateUploadRequest,
    responses(
        (status = 201, description = "Pending upload with its presigned request (not cacheable)", body = UploadDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Purpose not allowed for the caller, or an API key", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Type not accepted or size out of range for the purpose", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 503, description = "File storage is not available (`storage_unavailable`)", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn create_upload(
    State(state): State<AppState>,
    user: CurrentUser,
    ValidatedJson(body): ValidatedJson<CreateUploadRequest>,
) -> Result<Response, ApiError> {
    let requested = state
        .uploads
        .request(&user.actor, body.purpose.into(), &body.content_type, body.size_bytes)
        .await?;
    let location = format!("/api/v1/uploads/{}", requested.upload.id);
    let mut response = (StatusCode::CREATED, Json(UploadDto::from(requested))).into_response();
    let headers = response.headers_mut();
    // The URL is a bearer credential for writing into storage: never cached nor replayed.
    headers.insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    if let Ok(value) = HeaderValue::from_str(&location) {
        headers.insert(LOCATION, value);
    }
    Ok(response)
}

/// One of the caller's uploads: whether it is still pending or already attached.
#[utoipa::path(
    get, path = "/uploads/{id}", tag = "uploads",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Upload id")),
    responses(
        (status = 200, description = "The upload", body = UploadStatusViewDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "API keys have no uploads", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such upload of the caller", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_upload(
    State(state): State<AppState>,
    user: CurrentUser,
    PathId(id): PathId,
) -> Result<Json<UploadStatusViewDto>, ApiError> {
    let upload = state.uploads.get(&user.actor, UploadId::from_uuid(id)).await?;
    Ok(Json(upload.into()))
}
