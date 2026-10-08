//! Self-service account use-cases (`/me`).

use std::sync::Arc;

use dz_domain::Lang;
use dz_domain::Violations;
use dz_domain::authz::{Action, Actor, Policy};
use dz_domain::ids::{UploadId, UserId};
use dz_domain::upload::UploadPurpose;
use dz_domain::user::{Bio, PersonName, PhoneNumber, Profile, User};

use crate::error::{AppError, AppResult, AuthFailure};
use crate::ports::{Clock, ProfilePatch, UserPatch, UserRepository, WriteEffects};
use crate::uploads::UploadService;

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

/// A profile with the presigned URL of its avatar (`None` without avatar or storage).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProfileView {
    pub profile: Profile,
    pub avatar_url: Option<String>,
}

pub struct AccountService {
    users: Arc<dyn UserRepository>,
    uploads: Arc<UploadService>,
    clock: Arc<dyn Clock>,
}

impl AccountService {
    #[must_use]
    pub fn new(
        users: Arc<dyn UserRepository>,
        uploads: Arc<UploadService>,
        clock: Arc<dyn Clock>,
    ) -> Self {
        Self { users, uploads, clock }
    }

    fn view(&self, profile: Profile) -> ProfileView {
        let avatar_url = self.uploads.download_url(profile.avatar_key.as_deref());
        ProfileView { profile, avatar_url }
    }

    async fn own_profile(&self, id: UserId) -> AppResult<Profile> {
        self.users.profile(id).await?.ok_or(AppError::NotFound("profile"))
    }

    /// The caller's account and profile.
    pub async fn me(&self, actor: &Actor) -> AppResult<(User, ProfileView)> {
        let id = self.own_id(actor)?;
        let user = self.users.find(id).await?.ok_or(AppError::NotFound("user"))?;
        let profile = self.own_profile(id).await?;
        Ok((user, self.view(profile)))
    }

    /// Sets the caller's avatar to a claimed `avatar` upload. The previous object, if any, is
    /// deleted by a job enqueued with the change (deferred past its upload URL's validity).
    pub async fn set_avatar(&self, actor: &Actor, upload_id: UploadId) -> AppResult<ProfileView> {
        let id = self.own_id(actor)?;
        let claimed = self.uploads.claim(id, upload_id, UploadPurpose::Avatar, "upload_id").await?;
        let previous = self.own_profile(id).await?.avatar_key;
        let effects = match previous.as_deref() {
            Some(key) => self.uploads.with_deletion(WriteEffects::default(), key).await?,
            None => WriteEffects::default(),
        };
        let profile = self
            .users
            .set_avatar(id, Some(&claimed), previous.as_deref(), self.clock.now(), effects)
            .await?;
        Ok(self.view(profile))
    }

    /// Removes the caller's avatar (idempotent); its object is deleted by a deferred job.
    pub async fn remove_avatar(&self, actor: &Actor) -> AppResult<()> {
        let id = self.own_id(actor)?;
        self.uploads.require_storage()?;
        let Some(previous) = self.own_profile(id).await?.avatar_key else {
            return Ok(());
        };
        let effects = self.uploads.with_deletion(WriteEffects::default(), &previous).await?;
        self.users.set_avatar(id, None, Some(&previous), self.clock.now(), effects).await?;
        Ok(())
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
    ) -> AppResult<ProfileView> {
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
        let profile = if patch.is_empty() {
            self.own_profile(id).await?
        } else {
            self.users.update_profile(id, patch, self.clock.now()).await?
        };
        Ok(self.view(profile))
    }

    fn own_id(&self, actor: &Actor) -> AppResult<UserId> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        actor.user_id().ok_or(AppError::Unauthenticated(AuthFailure::Missing))
    }
}
