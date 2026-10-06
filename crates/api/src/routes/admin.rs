//! `/api/v1/admin/*`: user management, API keys, audit log.
//!
//! Handlers declare their permission with [`RequirePermission`] (checked before the body is
//! parsed); the use-cases re-check resource rules through the central policy.

use axum::Json;
use axum::extract::State;
use axum::http::header::{CACHE_CONTROL, LOCATION};
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use dz_app::admin::{AuditQuery as AuditFilterInput, CreateApiKeyInput, UserListQuery as UserFilterInput};
use dz_app::pagination::PageRequest;
use dz_domain::ids::{ApiKeyId, UserId};

use crate::dto::{
    AdminUpdateUserRequest, ApiKeyDto, AuditEntryDto, AuditQuery, CreateApiKeyRequest,
    CreatedApiKeyDto, PageQuery, Paginated, UserDto, UserListQuery,
};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{Meta, PathId, RequirePermission, ValidatedJson, ValidatedQuery, perm};
use crate::state::AppState;

/// List user accounts (newest first).
#[utoipa::path(
    get, path = "/admin/users", tag = "admin",
    security(("bearer" = [])),
    params(UserListQuery),
    responses(
        (status = 200, description = "A page of users", body = Paginated<UserDto>),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 403, description = "Not an administrator", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid filters", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_users(
    State(state): State<AppState>,
    guard: RequirePermission<perm::UserRead>,
    ValidatedQuery(query): ValidatedQuery<UserListQuery>,
) -> Result<Json<Paginated<UserDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let filter = UserFilterInput {
        role: query.role.map(|r| r.as_str().to_owned()),
        is_active: query.is_active,
        email_prefix: query.email,
    };
    let users = state.admin_users.list(&guard.actor, filter, page).await?;
    Ok(Json(Paginated::from_page(users, UserDto::from)))
}

/// One user account.
#[utoipa::path(
    get, path = "/admin/users/{id}", tag = "admin",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "User id")),
    responses(
        (status = 200, description = "The user", body = UserDto),
        (status = 403, description = "Not an administrator", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such user", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_user(
    State(state): State<AppState>,
    guard: RequirePermission<perm::UserRead>,
    PathId(id): PathId,
) -> Result<Json<UserDto>, ApiError> {
    let user = state.admin_users.get(&guard.actor, UserId::from_uuid(id)).await?;
    Ok(Json(user.into()))
}

/// Activate/deactivate an account or change its role (audited; signs the user out).
#[utoipa::path(
    patch, path = "/admin/users/{id}", tag = "admin",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "User id")),
    request_body = AdminUpdateUserRequest,
    responses(
        (status = 200, description = "Updated user", body = UserDto),
        (status = 403, description = "Not an administrator, or targeting yourself", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such user", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_user(
    State(state): State<AppState>,
    guard: RequirePermission<perm::UserManage>,
    Meta(meta): Meta,
    PathId(id): PathId,
    ValidatedJson(body): ValidatedJson<AdminUpdateUserRequest>,
) -> Result<Json<UserDto>, ApiError> {
    let user = state
        .admin_users
        .update(
            &guard.actor,
            UserId::from_uuid(id),
            body.is_active,
            body.role.map(|r| r.as_str()),
            &meta,
        )
        .await?;
    Ok(Json(user.into()))
}

/// List machine-to-machine API keys.
#[utoipa::path(
    get, path = "/admin/api-keys", tag = "admin",
    security(("bearer" = [])),
    params(PageQuery),
    responses(
        (status = 200, description = "A page of keys (secrets are never returned)", body = Paginated<ApiKeyDto>),
        (status = 403, description = "Not an administrator", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_api_keys(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ApiKeyManage>,
    ValidatedQuery(query): ValidatedQuery<PageQuery>,
) -> Result<Json<Paginated<ApiKeyDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let keys = state.api_keys.list(&guard.actor, page).await?;
    Ok(Json(Paginated::from_page(keys, ApiKeyDto::from)))
}

/// Create a scoped API key. The secret is returned once (audited).
#[utoipa::path(
    post, path = "/admin/api-keys", tag = "admin",
    security(("bearer" = [])),
    request_body = CreateApiKeyRequest,
    responses(
        (status = 201, description = "Key created; store the secret now", body = CreatedApiKeyDto),
        (status = 403, description = "Not an administrator", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid name, scopes or expiry", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn create_api_key(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ApiKeyManage>,
    Meta(meta): Meta,
    ValidatedJson(body): ValidatedJson<CreateApiKeyRequest>,
) -> Result<Response, ApiError> {
    let created = state
        .api_keys
        .create(
            &guard.actor,
            CreateApiKeyInput { name: body.name, scopes: body.scopes, expires_at: body.expires_at },
            &meta,
        )
        .await?;
    let location = format!("/api/v1/admin/api-keys/{}", created.record.id);
    let mut response = (StatusCode::CREATED, Json(CreatedApiKeyDto::from(created))).into_response();
    let headers = response.headers_mut();
    headers.insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    if let Ok(value) = HeaderValue::from_str(&location) {
        headers.insert(LOCATION, value);
    }
    Ok(response)
}

/// Revoke an API key immediately (audited).
#[utoipa::path(
    delete, path = "/admin/api-keys/{id}", tag = "admin",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "API key id")),
    responses(
        (status = 204, description = "Revoked"),
        (status = 403, description = "Not an administrator", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such key", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn revoke_api_key(
    State(state): State<AppState>,
    guard: RequirePermission<perm::ApiKeyManage>,
    Meta(meta): Meta,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.api_keys.revoke(&guard.actor, ApiKeyId::from_uuid(id), &meta).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Read the append-only audit log (newest first).
#[utoipa::path(
    get, path = "/admin/audit-log", tag = "admin",
    security(("bearer" = []), ("api_key" = [])),
    params(AuditQuery),
    responses(
        (status = 200, description = "A page of audit entries", body = Paginated<AuditEntryDto>),
        (status = 403, description = "Missing audit_log:read", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_audit_log(
    State(state): State<AppState>,
    guard: RequirePermission<perm::AuditLogRead>,
    ValidatedQuery(query): ValidatedQuery<AuditQuery>,
) -> Result<Json<Paginated<AuditEntryDto>>, ApiError> {
    let page = PageRequest::parse(query.limit, query.cursor.as_deref())?;
    let filter = AuditFilterInput {
        actor_id: query.actor_id,
        resource_type: query.resource_type,
        resource_id: query.resource_id,
        action: query.action,
    };
    let entries = state.audit.list(&guard.actor, filter, page).await?;
    Ok(Json(Paginated::from_page(entries, AuditEntryDto::from)))
}
