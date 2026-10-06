//! `/api/v1/auth/*`: registration, login, token refresh, logout, passwords, sessions.

use axum::Json;
use axum::extract::State;
use axum::http::header::{CACHE_CONTROL, LOCATION};
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use chrono::Utc;
use dz_app::auth::RegisterInput;
use dz_domain::ids::SessionId;
use secrecy::SecretString;

use crate::dto::{
    AuthResponse, ChangePasswordRequest, LoginRequest, PasswordResetConfirmRequest,
    PasswordResetRequest, RefreshRequest, RegisterRequest, SessionDto, TokenPairDto,
};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{ClientLang, CurrentUser, Meta, PathId, ValidatedJson};
use crate::state::AppState;

/// Responses that carry credentials must never be cached.
fn no_store(mut response: Response) -> Response {
    response.headers_mut().insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// Create a passenger account and sign it in.
#[utoipa::path(
    post, path = "/auth/register", tag = "auth",
    request_body = RegisterRequest,
    responses(
        (status = 201, description = "Account created and signed in", body = AuthResponse),
        (status = 409, description = "E-mail already used", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 429, description = "Too many attempts", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn register(
    State(state): State<AppState>,
    Meta(meta): Meta,
    ValidatedJson(body): ValidatedJson<RegisterRequest>,
) -> Result<Response, ApiError> {
    let signed = state
        .auth
        .register(
            RegisterInput {
                email: body.email,
                password: SecretString::from(body.password),
                first_name: body.first_name,
                last_name: body.last_name,
                phone_number: body.phone_number,
                language: body.language.map(Into::into),
            },
            &meta,
        )
        .await?;
    let response = AuthResponse {
        user: signed.user.into(),
        tokens: TokenPairDto::new(signed.tokens, Utc::now()),
    };
    let mut response = (StatusCode::CREATED, Json(response)).into_response();
    response.headers_mut().insert(LOCATION, HeaderValue::from_static("/api/v1/me"));
    Ok(no_store(response))
}

/// Sign in with e-mail and password.
#[utoipa::path(
    post, path = "/auth/login", tag = "auth",
    request_body = LoginRequest,
    responses(
        (status = 200, description = "Signed in", body = AuthResponse),
        (status = 401, description = "Invalid credentials (unknown account, wrong password, locked or disabled account)", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 429, description = "Too many attempts", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn login(
    State(state): State<AppState>,
    Meta(meta): Meta,
    ValidatedJson(body): ValidatedJson<LoginRequest>,
) -> Result<Response, ApiError> {
    let signed = state.auth.login(&body.email, &SecretString::from(body.password), &meta).await?;
    let response = AuthResponse {
        user: signed.user.into(),
        tokens: TokenPairDto::new(signed.tokens, Utc::now()),
    };
    Ok(no_store(Json(response).into_response()))
}

/// Exchange a refresh token for a new token pair. The presented refresh token is spent;
/// presenting it again revokes the whole session.
#[utoipa::path(
    post, path = "/auth/refresh", tag = "auth",
    request_body = RefreshRequest,
    responses(
        (status = 200, description = "New token pair", body = TokenPairDto),
        (status = 401, description = "Invalid, expired or reused refresh token", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn refresh(
    State(state): State<AppState>,
    ValidatedJson(body): ValidatedJson<RefreshRequest>,
) -> Result<Response, ApiError> {
    let pair = state.auth.refresh(&body.refresh_token).await?;
    Ok(no_store(Json(TokenPairDto::new(pair, Utc::now())).into_response()))
}

/// End the current session (its access and refresh tokens stop working immediately).
#[utoipa::path(
    post, path = "/auth/logout", tag = "auth",
    security(("bearer" = [])),
    responses(
        (status = 204, description = "Signed out"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn logout(State(state): State<AppState>, user: CurrentUser) -> Result<StatusCode, ApiError> {
    state.auth.logout(&user.claims, false).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// End every session of the caller (all devices).
#[utoipa::path(
    post, path = "/auth/logout-all", tag = "auth",
    security(("bearer" = [])),
    responses(
        (status = 204, description = "Signed out everywhere"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn logout_all(
    State(state): State<AppState>,
    user: CurrentUser,
) -> Result<StatusCode, ApiError> {
    state.auth.logout(&user.claims, true).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Change the password. Other sessions are signed out; the current one stays valid.
#[utoipa::path(
    post, path = "/auth/password/change", tag = "auth",
    security(("bearer" = [])),
    request_body = ChangePasswordRequest,
    responses(
        (status = 204, description = "Password changed"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Wrong current password or weak new password", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn change_password(
    State(state): State<AppState>,
    user: CurrentUser,
    ValidatedJson(body): ValidatedJson<ChangePasswordRequest>,
) -> Result<StatusCode, ApiError> {
    state
        .auth
        .change_password(
            &user.claims,
            &SecretString::from(body.current_password),
            &SecretString::from(body.new_password),
        )
        .await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Request a password-reset e-mail. Always accepted, whether or not the account exists.
#[utoipa::path(
    post, path = "/auth/password/reset", tag = "auth",
    request_body = PasswordResetRequest,
    responses(
        (status = 202, description = "If the account exists, an e-mail is on its way"),
        (status = 422, description = "Malformed e-mail", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 429, description = "Too many attempts", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn request_password_reset(
    State(state): State<AppState>,
    Meta(meta): Meta,
    ClientLang(lang): ClientLang,
    ValidatedJson(body): ValidatedJson<PasswordResetRequest>,
) -> Result<StatusCode, ApiError> {
    state.auth.request_password_reset(&body.email, lang, &meta).await?;
    Ok(StatusCode::ACCEPTED)
}

/// Set a new password with the token from the reset e-mail. Every session is signed out.
#[utoipa::path(
    post, path = "/auth/password/reset/confirm", tag = "auth",
    request_body = PasswordResetConfirmRequest,
    responses(
        (status = 204, description = "Password changed"),
        (status = 400, description = "Invalid or expired token", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Weak password", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn confirm_password_reset(
    State(state): State<AppState>,
    ValidatedJson(body): ValidatedJson<PasswordResetConfirmRequest>,
) -> Result<StatusCode, ApiError> {
    state.auth.confirm_password_reset(&body.token, &SecretString::from(body.new_password)).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// List the caller's active sessions (devices).
#[utoipa::path(
    get, path = "/auth/sessions", tag = "auth",
    security(("bearer" = [])),
    responses(
        (status = 200, description = "Active sessions, most recently used first", body = [SessionDto]),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn list_sessions(
    State(state): State<AppState>,
    user: CurrentUser,
) -> Result<Json<Vec<SessionDto>>, ApiError> {
    let sessions = state.auth.list_sessions(&user.claims).await?;
    Ok(Json(sessions.into_iter().map(Into::into).collect()))
}

/// Sign out one of the caller's sessions (e.g. a lost phone).
#[utoipa::path(
    delete, path = "/auth/sessions/{id}", tag = "auth",
    security(("bearer" = [])),
    params(("id" = Uuid, Path, description = "Session id")),
    responses(
        (status = 204, description = "Session revoked"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 404, description = "No such active session", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn revoke_session(
    State(state): State<AppState>,
    user: CurrentUser,
    PathId(id): PathId,
) -> Result<StatusCode, ApiError> {
    state.auth.revoke_session(&user.actor, SessionId::from_uuid(id)).await?;
    Ok(StatusCode::NO_CONTENT)
}
