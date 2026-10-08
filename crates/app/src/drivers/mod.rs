//! The driver programme: applications with identity documents, the driver's own profile,
//! reviews (approve, reject, suspend, reinstate) and the status history.
//!
//! Every status change follows [`DriverStatus::transition`] and is written with its history
//! entry, its consequences and its outbox jobs in one transaction: the driver is told about
//! the new status ([`Job::DriverStatusChanged`]) and reviewers are told about profiles waiting
//! for them ([`Job::DriverReviewRequested`]). Reviews are audited; self-service changes are
//! recorded in the status history with the driver as author.
//!
//! Driver profiles are private: only the driver and holders of `driver:read` see them, and
//! anyone else gets `404` (the existence of a profile is not revealed).

pub mod ports;

use std::sync::Arc;

use chrono::{DateTime, Utc};
use dz_domain::authz::{Action, Actor, Policy};
use dz_domain::driver::{
    DriverAction, DriverStatus, DriverStatusChange, LicenseNumber, NationalIdNumber,
    StatusReason, YearsOfExperience,
};
use dz_domain::ids::{DriverId, DriverStatusChangeId, UploadId, UserId};
use dz_domain::upload::UploadPurpose;
use dz_domain::user::PhoneNumber;
use dz_domain::{ConflictKind, DenyReason, Violations};
use serde_json::json;

use self::ports::{
    DriverFilter, DriverPatch, DriverRecord, DriverRepository, NewDriver, StatusChange,
};
use crate::audit;
use crate::error::{AppError, AppResult};
use crate::jobs::Job;
use crate::pagination::{Page, PageRequest};
use crate::ports::{ClaimedUpload, Clock, NewAuditEntry, RequestMeta, WriteEffects};
use crate::uploads::UploadService;

/// Attempts of a status change that keeps losing races against concurrent changes. Each
/// attempt re-reads the profile, so a change made invalid meanwhile ends as
/// `invalid_transition`, and an approval of a profile changed meanwhile as `stale_state`.
const TRANSITION_ATTEMPTS: usize = 3;

/// Request fields of the document photos (where claim problems are reported).
const ID_CARD_PHOTO: &str = "id_card_photo_upload_id";
const LICENSE_PHOTO: &str = "driver_license_photo_upload_id";

/// A driver profile with presigned URLs of its document photos (`None` without storage).
#[derive(Debug, Clone, PartialEq)]
pub struct DriverView {
    pub record: DriverRecord,
    pub id_card_photo_url: Option<String>,
    pub driver_license_photo_url: Option<String>,
}

/// Raw input of an application.
#[derive(Debug, Clone)]
pub struct ApplyInput {
    pub phone_number: String,
    pub id_card_number: String,
    pub id_card_photo_upload_id: UploadId,
    pub driver_license_number: String,
    pub driver_license_photo_upload_id: UploadId,
    pub years_of_experience: i64,
}

/// Raw changes to the caller's profile; absent fields are unchanged.
#[derive(Debug, Clone, Default)]
pub struct UpdateDriverInput {
    pub phone_number: Option<String>,
    pub years_of_experience: Option<i64>,
    pub id_card_number: Option<String>,
    pub id_card_photo_upload_id: Option<UploadId>,
    pub driver_license_number: Option<String>,
    pub driver_license_photo_upload_id: Option<UploadId>,
}

/// Filters of the admin list.
#[derive(Debug, Clone, Copy, Default)]
pub struct DriverListQuery {
    pub status: Option<DriverStatus>,
    pub is_available: Option<bool>,
}

/// A reviewer's decision.
#[derive(Debug, Clone)]
pub enum Review {
    /// Of the profile as the reviewer examined it: `expected_updated_at` is the `updated_at`
    /// they read. An approval never applies to documents the reviewer did not see: once the
    /// profile changed, it is refused with `stale_state`.
    Approve { expected_updated_at: DateTime<Utc> },
    /// With the reason given to the applicant.
    Reject { reason: String },
    /// With the reason given to the driver.
    Suspend { reason: String },
    Reinstate,
}

impl Review {
    const fn action(&self) -> DriverAction {
        match self {
            Self::Approve { .. } => DriverAction::Approve,
            Self::Reject { .. } => DriverAction::Reject,
            Self::Suspend { .. } => DriverAction::Suspend,
            Self::Reinstate => DriverAction::Reinstate,
        }
    }

    /// The audit action (`driver.<verb>`).
    const fn audit_action(&self) -> &'static str {
        match self {
            Self::Approve { .. } => "driver.approve",
            Self::Reject { .. } => "driver.reject",
            Self::Suspend { .. } => "driver.suspend",
            Self::Reinstate => "driver.reinstate",
        }
    }

    fn reason(&self) -> Option<&str> {
        match self {
            Self::Reject { reason } | Self::Suspend { reason } => Some(reason),
            Self::Approve { .. } | Self::Reinstate => None,
        }
    }

    /// The version of the profile the decision is bound to, if any.
    const fn expected_updated_at(&self) -> Option<DateTime<Utc>> {
        match self {
            Self::Approve { expected_updated_at } => Some(*expected_updated_at),
            Self::Reject { .. } | Self::Suspend { .. } | Self::Reinstate => None,
        }
    }
}

pub struct DriverService {
    drivers: Arc<dyn DriverRepository>,
    uploads: Arc<UploadService>,
    clock: Arc<dyn Clock>,
}

impl DriverService {
    #[must_use]
    pub fn new(
        drivers: Arc<dyn DriverRepository>,
        uploads: Arc<UploadService>,
        clock: Arc<dyn Clock>,
    ) -> Self {
        Self { drivers, uploads, clock }
    }

    fn view(&self, record: DriverRecord) -> DriverView {
        let driver = &record.driver;
        DriverView {
            id_card_photo_url: self.uploads.download_url(Some(&driver.id_card_photo_key)),
            driver_license_photo_url: self
                .uploads
                .download_url(Some(&driver.driver_license_photo_key)),
            record,
        }
    }

    /// The caller's own profile (`404` when they have none).
    async fn own(&self, user: UserId) -> AppResult<DriverRecord> {
        self.drivers.find_by_user(user).await?.ok_or(AppError::NotFound("driver"))
    }

    /// A profile the actor may read. Someone else's profile is indistinguishable from a
    /// missing one.
    async fn readable(&self, actor: &Actor, id: DriverId) -> AppResult<DriverRecord> {
        let record = self.drivers.find(id).await?.ok_or(AppError::NotFound("driver"))?;
        match Policy::authorize(actor, &Action::ReadDriver { owner: record.user.id }) {
            Ok(()) => Ok(record),
            Err(reason @ DenyReason::AuthenticationRequired) => Err(reason.into()),
            Err(_) => Err(AppError::NotFound("driver")),
        }
    }

    /// Applies to become a driver: the profile is created for the caller (legacy L-02) with
    /// both document photos, in one transaction (L-31). Reviewers are notified.
    pub async fn apply(&self, actor: &Actor, input: ApplyInput) -> AppResult<DriverView> {
        Policy::authorize(actor, &Action::ApplyAsDriver)?;
        let user = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        let mut v = Violations::new();
        let phone = v.check("phone_number", PhoneNumber::parse(&input.phone_number));
        let id_card = v.check("id_card_number", NationalIdNumber::parse(&input.id_card_number));
        let licence =
            v.check("driver_license_number", LicenseNumber::parse(&input.driver_license_number));
        let years =
            v.check("years_of_experience", YearsOfExperience::parse(input.years_of_experience));
        let (Some(phone), Some(id_card), Some(licence), Some(years)) =
            (phone, id_card, licence, years)
        else {
            return Err(v.into());
        };
        self.uploads.require_storage()?;
        if self.drivers.find_by_user(user).await?.is_some() {
            return Err(AppError::Conflict(ConflictKind::DriverProfileExists));
        }
        let (id_card_upload, licence_upload) =
            (input.id_card_photo_upload_id, input.driver_license_photo_upload_id);
        let id_card_photo = self
            .uploads
            .claim(user, id_card_upload, UploadPurpose::DriverIdCard, ID_CARD_PHOTO)
            .await;
        let licence_photo = self
            .uploads
            .claim(user, licence_upload, UploadPurpose::DriverLicense, LICENSE_PHOTO)
            .await;
        let (id_card_photo, licence_photo) = both(id_card_photo, licence_photo)?;

        let id = DriverId::generate();
        let now = self.clock.now();
        let to = DriverStatus::transition(None, DriverAction::Apply)?;
        let application = StatusChange {
            id: DriverStatusChangeId::generate(),
            from: None,
            to,
            reason: None,
            changed_by: Some(user),
            at: now,
            expected_updated_at: None,
        };
        let effects = notifications(WriteEffects::default(), id, Some(to), true);
        let new = NewDriver {
            id,
            user_id: user,
            phone_number: phone,
            id_card_number: id_card,
            id_card_photo,
            driver_license_number: licence,
            driver_license_photo: licence_photo,
            years_of_experience: years,
            application,
        };
        let record = self.drivers.insert(new, effects).await?;
        tracing::info!(driver_id = %id, "driver application submitted");
        Ok(self.view(record))
    }

    /// Claims a new document photo, if one is given.
    async fn claim_new(
        &self,
        user: UserId,
        upload: Option<UploadId>,
        purpose: UploadPurpose,
        field: &'static str,
    ) -> AppResult<Option<ClaimedUpload>> {
        match upload {
            Some(upload) => self.uploads.claim(user, upload, purpose, field).await.map(Some),
            None => Ok(None),
        }
    }

    /// The caller's profile.
    pub async fn me(&self, actor: &Actor) -> AppResult<DriverView> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        let user = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        Ok(self.view(self.own(user).await?))
    }

    /// Updates the caller's profile. Changing an identity document (number or photo) sends an
    /// approved profile back to review (`pending`) and makes the driver unavailable; reviewers
    /// are notified whenever the profile is pending after the change. Replaced photos are
    /// deleted by deferred jobs. An update that changes nothing returns the profile.
    pub async fn update_me(
        &self,
        actor: &Actor,
        input: UpdateDriverInput,
    ) -> AppResult<DriverView> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        let user = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        let mut v = Violations::new();
        let phone = input
            .phone_number
            .as_deref()
            .and_then(|raw| v.check("phone_number", PhoneNumber::parse(raw)));
        let years = input
            .years_of_experience
            .and_then(|raw| v.check("years_of_experience", YearsOfExperience::parse(raw)));
        let id_card = input
            .id_card_number
            .as_deref()
            .and_then(|raw| v.check("id_card_number", NationalIdNumber::parse(raw)));
        let licence = input
            .driver_license_number
            .as_deref()
            .and_then(|raw| v.check("driver_license_number", LicenseNumber::parse(raw)));
        v.into_result()?;

        let current = self.own(user).await?;
        let (id_card_upload, licence_upload) =
            (input.id_card_photo_upload_id, input.driver_license_photo_upload_id);
        if id_card_upload.is_some() || licence_upload.is_some() {
            self.uploads.require_storage()?;
        }
        let id_card_photo =
            self.claim_new(user, id_card_upload, UploadPurpose::DriverIdCard, ID_CARD_PHOTO).await;
        let licence_photo =
            self.claim_new(user, licence_upload, UploadPurpose::DriverLicense, LICENSE_PHOTO).await;
        let (id_card_photo, licence_photo) = both(id_card_photo, licence_photo)?;
        let driver = &current.driver;
        // Values equal to the stored ones are not changes.
        let patch = DriverPatch {
            phone_number: phone.filter(|p| *p != driver.phone_number),
            years_of_experience: years.filter(|y| *y != driver.years_of_experience),
            id_card_number: id_card.filter(|n| *n != driver.id_card_number),
            id_card_photo,
            driver_license_number: licence.filter(|n| *n != driver.driver_license_number),
            driver_license_photo: licence_photo,
        };
        if patch.is_empty() {
            return Ok(self.view(current));
        }
        let documents_changed = patch.id_card_number.is_some()
            || patch.id_card_photo.is_some()
            || patch.driver_license_number.is_some()
            || patch.driver_license_photo.is_some();

        let now = self.clock.now();
        let from = driver.status;
        let to = if documents_changed {
            DriverStatus::transition(Some(from), DriverAction::DocumentsChanged)?
        } else {
            from
        };
        let change = (to != from).then(|| StatusChange {
            id: DriverStatusChangeId::generate(),
            from: Some(from),
            to,
            reason: None,
            changed_by: Some(user),
            at: now,
            expected_updated_at: None,
        });
        let mut effects = notifications(
            WriteEffects::default(),
            driver.id,
            change.as_ref().map(|c| c.to),
            documents_changed && to == DriverStatus::Pending,
        );
        if patch.id_card_photo.is_some() {
            effects = self.uploads.with_deletion(effects, &driver.id_card_photo_key).await?;
        }
        if patch.driver_license_photo.is_some() {
            effects = self.uploads.with_deletion(effects, &driver.driver_license_photo_key).await?;
        }
        let record = self.drivers.update_profile(driver, patch, change, now, effects).await?;
        if to != from {
            tracing::info!(driver_id = %driver.id, %from, %to, "driver documents changed");
        }
        Ok(self.view(record))
    }

    /// Sets the caller's availability; approved drivers only (`invalid_state` otherwise).
    pub async fn set_availability(&self, actor: &Actor, available: bool) -> AppResult<DriverView> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        let user = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        let current = self.own(user).await?;
        let now = self.clock.now();
        let record = self.drivers.set_availability(current.driver.id, available, now).await?;
        Ok(self.view(record))
    }

    /// Applies again after a rejection (`rejected → pending`, legacy L-24); reviewers are
    /// notified.
    pub async fn reapply(&self, actor: &Actor) -> AppResult<DriverView> {
        Policy::authorize(actor, &Action::ApplyAsDriver)?;
        let user = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        let current = self.own(user).await?;
        let reapply = DriverAction::Reapply;
        let record = self.change_status(actor, current, reapply, None, None, |_| None).await?;
        Ok(self.view(record))
    }

    /// Every driver profile, newest first (reviewers).
    pub async fn list(
        &self,
        actor: &Actor,
        query: DriverListQuery,
        page: PageRequest,
    ) -> AppResult<Page<DriverView>> {
        Policy::authorize(actor, &Action::ListDrivers)?;
        let filter = DriverFilter { status: query.status, is_available: query.is_available };
        Ok(self.drivers.list(filter, page).await?.map(|r| self.view(r)))
    }

    /// One profile: the caller's own, or any for reviewers.
    pub async fn get(&self, actor: &Actor, id: DriverId) -> AppResult<DriverView> {
        Ok(self.view(self.readable(actor, id).await?))
    }

    /// The status history of a profile, newest first (same visibility as the profile).
    pub async fn status_history(
        &self,
        actor: &Actor,
        id: DriverId,
        page: PageRequest,
    ) -> AppResult<Page<DriverStatusChange>> {
        self.readable(actor, id).await?;
        self.drivers.status_history(id, page).await
    }

    /// Applies a reviewer's decision (audited). Approval gives the applicant the `driver`
    /// role; suspension takes the driver's buses off duty. An approval is bound to the version
    /// of the profile the reviewer examined: when the profile changed since (e.g. new
    /// documents, even while pending), it fails with `Conflict(StaleState)` and nothing changes.
    pub async fn review(
        &self,
        actor: &Actor,
        id: DriverId,
        review: Review,
        meta: &RequestMeta,
    ) -> AppResult<DriverView> {
        let current = self.drivers.find(id).await?.ok_or(AppError::NotFound("driver"))?;
        Policy::authorize(actor, &Action::ReviewDriver { owner: current.user.id })?;
        let reason = match review.reason() {
            Some(raw) => {
                Some(StatusReason::parse(raw).map_err(|e| AppError::invalid("reason", e))?)
            }
            None => None,
        };
        let audited = |change: &StatusChange| {
            let details = json!({
                "from": change.from.map(DriverStatus::as_str),
                "to": change.to.as_str(),
                "reason": change.reason.as_ref().map(StatusReason::as_str),
            });
            let resource = id.to_string();
            let action = review.audit_action();
            Some(audit::entry(actor, meta, change.at, action, "driver", resource, details))
        };
        let (action, expected) = (review.action(), review.expected_updated_at());
        let record = self.change_status(actor, current, action, reason, expected, audited).await?;
        tracing::info!(driver_id = %id, status = %record.driver.status, "driver reviewed");
        Ok(self.view(record))
    }

    /// Moves `current` through `action`, re-reading the profile when a concurrent change wins
    /// the race. A change bound to a version of the profile (`expected_updated_at`) is refused
    /// with `Conflict(StaleState)` as soon as the profile read has another version, before the
    /// first attempt or after a lost race: it is never retried on a profile that changed.
    /// `audit` builds the audit entry of the change, if it is audited.
    async fn change_status(
        &self,
        actor: &Actor,
        mut current: DriverRecord,
        action: DriverAction,
        reason: Option<StatusReason>,
        expected_updated_at: Option<DateTime<Utc>>,
        audit: impl Fn(&StatusChange) -> Option<NewAuditEntry>,
    ) -> AppResult<DriverRecord> {
        let id = current.driver.id;
        for _ in 0..TRANSITION_ATTEMPTS {
            let from = current.driver.status;
            // A profile that left the status the action applies to answers
            // `invalid_transition`, whatever the version the caller expected.
            let to = DriverStatus::transition(Some(from), action)?;
            if expected_updated_at.is_some_and(|expected| expected != current.driver.updated_at) {
                return Err(AppError::Conflict(ConflictKind::StaleState));
            }
            let now = self.clock.now();
            let change = StatusChange {
                id: DriverStatusChangeId::generate(),
                from: Some(from),
                to,
                reason: reason.clone(),
                changed_by: actor.user_id(),
                at: now,
                // Checked again by the write itself: the profile may change after this read.
                expected_updated_at,
            };
            let mut effects = WriteEffects::default();
            effects.audit.extend(audit(&change));
            let effects = notifications(effects, id, Some(to), to == DriverStatus::Pending);
            match self.drivers.transition(id, change, effects).await {
                Err(AppError::Conflict(ConflictKind::StaleState)) => {
                    current = self.drivers.find(id).await?.ok_or(AppError::NotFound("driver"))?;
                }
                result => return result,
            }
        }
        Err(AppError::Conflict(ConflictKind::StaleState))
    }
}

/// Adds the outbox jobs of a profile change: the driver is told about a new `status`, and
/// reviewers about a profile waiting for review. Review requests carry no dedup key: a job
/// that is already running may have read a stale status and be dropping its request, so
/// coalescing with it could lose this one (the runner drops requests for reviewed profiles).
fn notifications(
    effects: WriteEffects,
    id: DriverId,
    status: Option<DriverStatus>,
    review_requested: bool,
) -> WriteEffects {
    let mut effects = effects;
    if let Some(status) = status {
        effects = effects.with_job(Job::DriverStatusChanged { driver_id: id, status });
    }
    if review_requested {
        effects = effects.with_job(Job::DriverReviewRequested { driver_id: id });
    }
    effects
}

/// Both results, or the problems of both: field violations are merged so that a client sees
/// every unusable upload at once.
fn both<A, B>(a: AppResult<A>, b: AppResult<B>) -> AppResult<(A, B)> {
    match (a, b) {
        (Ok(a), Ok(b)) => Ok((a, b)),
        (Err(AppError::Validation(mut first)), Err(AppError::Validation(second))) => {
            first.extend(second);
            Err(AppError::Validation(first))
        }
        (Err(e), _) | (_, Err(e)) => Err(e),
    }
}

#[cfg(test)]
mod tests;
