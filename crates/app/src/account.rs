//! Self-service account use-cases (`/me`).

use std::sync::Arc;

use dz_domain::Lang;
use dz_domain::Violations;
use dz_domain::authz::{Action, Actor, Policy};
use dz_domain::ids::UserId;
use dz_domain::user::{Bio, PersonName, PhoneNumber, Profile, User};

use crate::error::{AppError, AppResult, AuthFailure};
use crate::ports::{Clock, ProfilePatch, UserPatch, UserRepository};

/// Raw self-service changes; `Some(None)` / `Some("")` clears the phone number.
#[derive(Debug, Clone, Default)]
pub struct UpdateMeInput {
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub phone_number: Option<Option<String>>,
}

#[derive(Debug, Clone, Default)]
pub struct UpdateProfileInput {
    pub bio: Option<String>,
    pub language: Option<Lang>,
    pub push_notifications_enabled: Option<bool>,
    pub email_notifications_enabled: Option<bool>,
    pub sms_notifications_enabled: Option<bool>,
}

pub struct AccountService {
    users: Arc<dyn UserRepository>,
    clock: Arc<dyn Clock>,
}

impl AccountService {
    #[must_use]
    pub fn new(users: Arc<dyn UserRepository>, clock: Arc<dyn Clock>) -> Self {
        Self { users, clock }
    }

    /// The caller's account and profile.
    pub async fn me(&self, actor: &Actor) -> AppResult<(User, Profile)> {
        let id = self.own_id(actor)?;
        let user = self.users.find(id).await?.ok_or(AppError::NotFound("user"))?;
        let profile = self.users.profile(id).await?.ok_or(AppError::NotFound("profile"))?;
        Ok((user, profile))
    }

    /// Updates the caller's names and phone number.
    pub async fn update_me(&self, actor: &Actor, input: UpdateMeInput) -> AppResult<User> {
        let id = self.own_id(actor)?;
        let mut v = Violations::new();
        let patch = UserPatch {
            first_name: input
                .first_name
                .as_deref()
                .and_then(|raw| v.check("first_name", PersonName::parse(raw))),
            last_name: input
                .last_name
                .as_deref()
                .and_then(|raw| v.check("last_name", PersonName::parse(raw))),
            phone_number: match input.phone_number {
                None => None,
                Some(None) => Some(None),
                Some(Some(raw)) if raw.trim().is_empty() => Some(None),
                Some(Some(raw)) => {
                    v.check("phone_number", PhoneNumber::parse(&raw)).map(Some)
                }
            },
        };
        v.into_result()?;
        if patch.is_empty() {
            return self.users.find(id).await?.ok_or(AppError::NotFound("user"));
        }
        self.users.update(id, patch, self.clock.now()).await
    }

    /// Updates the caller's profile preferences.
    pub async fn update_profile(
        &self,
        actor: &Actor,
        input: UpdateProfileInput,
    ) -> AppResult<Profile> {
        let id = self.own_id(actor)?;
        let mut v = Violations::new();
        let patch = ProfilePatch {
            bio: input.bio.as_deref().and_then(|raw| v.check("bio", Bio::parse(raw))),
            language: input.language,
            push_notifications_enabled: input.push_notifications_enabled,
            email_notifications_enabled: input.email_notifications_enabled,
            sms_notifications_enabled: input.sms_notifications_enabled,
        };
        v.into_result()?;
        if patch.is_empty() {
            return self.users.profile(id).await?.ok_or(AppError::NotFound("profile"));
        }
        self.users.update_profile(id, patch, self.clock.now()).await
    }

    fn own_id(&self, actor: &Actor) -> AppResult<UserId> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        actor.user_id().ok_or(AppError::Unauthenticated(AuthFailure::Missing))
    }
}
