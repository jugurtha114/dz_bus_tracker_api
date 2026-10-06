//! `/api/v1/me*`: the caller's own account and profile.

use axum::Json;
use axum::extract::State;
use dz_app::account::{UpdateMeInput, UpdateProfileInput};

use crate::dto::{MeDto, ProfileDto, UpdateMeRequest, UpdateProfileRequest};
use crate::error::{ApiError, ProblemDocument};
use crate::extract::{CurrentUser, ValidatedJson};
use crate::state::AppState;

/// The caller's account and profile.
#[utoipa::path(
    get, path = "/me", tag = "me",
    security(("bearer" = [])),
    responses(
        (status = 200, description = "Account and profile", body = MeDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_me(State(state): State<AppState>, user: CurrentUser) -> Result<Json<MeDto>, ApiError> {
    let (account, profile) = state.accounts.me(&user.actor).await?;
    Ok(Json(MeDto { user: account.into(), profile: profile.into() }))
}

/// Update names and phone number.
#[utoipa::path(
    patch, path = "/me", tag = "me",
    security(("bearer" = [])),
    request_body = UpdateMeRequest,
    responses(
        (status = 200, description = "Updated account", body = MeDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_me(
    State(state): State<AppState>,
    user: CurrentUser,
    ValidatedJson(body): ValidatedJson<UpdateMeRequest>,
) -> Result<Json<MeDto>, ApiError> {
    state
        .accounts
        .update_me(
            &user.actor,
            UpdateMeInput {
                first_name: body.first_name,
                last_name: body.last_name,
                phone_number: body.phone_number,
            },
        )
        .await?;
    let (account, profile) = state.accounts.me(&user.actor).await?;
    Ok(Json(MeDto { user: account.into(), profile: profile.into() }))
}

/// The caller's profile preferences.
#[utoipa::path(
    get, path = "/me/profile", tag = "me",
    security(("bearer" = [])),
    responses(
        (status = 200, description = "Profile", body = ProfileDto),
        (status = 304, description = "Not modified (If-None-Match)"),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn get_profile(
    State(state): State<AppState>,
    user: CurrentUser,
) -> Result<Json<ProfileDto>, ApiError> {
    let (_, profile) = state.accounts.me(&user.actor).await?;
    Ok(Json(profile.into()))
}

/// Update profile preferences. A language change applies to new access tokens (after the
/// next refresh).
#[utoipa::path(
    patch, path = "/me/profile", tag = "me",
    security(("bearer" = [])),
    request_body = UpdateProfileRequest,
    responses(
        (status = 200, description = "Updated profile", body = ProfileDto),
        (status = 401, description = "Not signed in", body = ProblemDocument, content_type = "application/problem+json"),
        (status = 422, description = "Invalid fields", body = ProblemDocument, content_type = "application/problem+json"),
    )
)]
pub async fn update_profile(
    State(state): State<AppState>,
    user: CurrentUser,
    ValidatedJson(body): ValidatedJson<UpdateProfileRequest>,
) -> Result<Json<ProfileDto>, ApiError> {
    let profile = state
        .accounts
        .update_profile(
            &user.actor,
            UpdateProfileInput {
                bio: body.bio,
                language: body.language.map(Into::into),
                push_notifications_enabled: body.push_notifications_enabled,
                email_notifications_enabled: body.email_notifications_enabled,
                sms_notifications_enabled: body.sms_notifications_enabled,
            },
        )
        .await?;
    Ok(Json(profile.into()))
}
