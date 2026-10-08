//! Repository port of the driver programme.
//!
//! Every write is one transaction: the profile change, its status-history row, the uploads it
//! attaches, the consequences of the new status (role, availability, buses) and its
//! [`WriteEffects`] (audit entries, outbox jobs). Status changes are compare-and-set on the
//! status read by the use-case (and, for approvals, on the reviewed `updated_at`): a
//! concurrent change makes the write fail with `Conflict(StaleState)` and nothing is written.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::Lang;
use dz_domain::driver::{
    Driver, DriverStatus, DriverStatusChange, LicenseNumber, NationalIdNumber, StatusReason,
    YearsOfExperience,
};
use dz_domain::ids::{DriverId, DriverStatusChangeId, UserId};
use dz_domain::user::{Email, PersonName, PhoneNumber};

use crate::error::AppResult;
use crate::pagination::{Page, PageRequest};
use crate::ports::{ClaimedUpload, WriteEffects};

/// The account behind a driver profile (or a reviewer to notify).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AccountSummary {
    pub id: UserId,
    pub email: Email,
    pub first_name: PersonName,
    pub last_name: PersonName,
    /// Language of the e-mails sent to the account.
    pub language: Lang,
}

/// A driver profile with its account.
#[derive(Debug, Clone, PartialEq)]
pub struct DriverRecord {
    pub driver: Driver,
    pub user: AccountSummary,
}

/// A status change to record. The profile must still have `from` (compare-and-set); `None`
/// only for the application, which creates the profile.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StatusChange {
    pub id: DriverStatusChangeId,
    pub from: Option<DriverStatus>,
    pub to: DriverStatus,
    /// Required for rejections and suspensions; the profile's `status_reason` becomes this
    /// reason (or empty).
    pub reason: Option<StatusReason>,
    /// The user causing the change (`None`: the system).
    pub changed_by: Option<UserId>,
    pub at: DateTime<Utc>,
    /// The `updated_at` the profile must still have (compare-and-set, with `from`): an
    /// approval only applies to the version of the documents the reviewer examined. `None`
    /// for every other change.
    pub expected_updated_at: Option<DateTime<Utc>>,
}

/// An application to insert, with its claimed documents.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NewDriver {
    pub id: DriverId,
    pub user_id: UserId,
    pub phone_number: PhoneNumber,
    pub id_card_number: NationalIdNumber,
    pub id_card_photo: ClaimedUpload,
    pub driver_license_number: LicenseNumber,
    pub driver_license_photo: ClaimedUpload,
    pub years_of_experience: YearsOfExperience,
    /// The first entry of the history (`None → pending`).
    pub application: StatusChange,
}

/// Self-service changes to a profile; `None` leaves a field unchanged. New document photos
/// are claimed uploads, marked attached in the transaction that stores their keys.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DriverPatch {
    pub phone_number: Option<PhoneNumber>,
    pub years_of_experience: Option<YearsOfExperience>,
    pub id_card_number: Option<NationalIdNumber>,
    pub id_card_photo: Option<ClaimedUpload>,
    pub driver_license_number: Option<LicenseNumber>,
    pub driver_license_photo: Option<ClaimedUpload>,
}

impl DriverPatch {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        *self == Self::default()
    }
}

/// Filters of the admin driver list.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct DriverFilter {
    pub status: Option<DriverStatus>,
    pub is_available: Option<bool>,
}

#[async_trait]
pub trait DriverRepository: Send + Sync {
    /// Inserts the profile, its first history entry, and marks both document uploads
    /// attached. Fails with `Conflict(DriverProfileExists)`, `Conflict(IdCardTaken)`,
    /// `Conflict(LicenseTaken)` and `Conflict(UploadAlreadyUsed)`.
    async fn insert(&self, driver: NewDriver, effects: WriteEffects) -> AppResult<DriverRecord>;
    async fn find(&self, id: DriverId) -> AppResult<Option<DriverRecord>>;
    /// The profile of an account.
    async fn find_by_user(&self, user_id: UserId) -> AppResult<Option<DriverRecord>>;
    /// Profiles, newest first.
    async fn list(&self, filter: DriverFilter, page: PageRequest) -> AppResult<Page<DriverRecord>>;
    /// Applies `patch` provided the profile still has the status and document photos of
    /// `expected`, records `change` when the status changes (`change.from` is
    /// `expected.status`), and persists `effects`. Leaving `approved` makes the driver
    /// unavailable. Fails with `NotFound("driver")`, `Conflict(StaleState)`,
    /// `Conflict(IdCardTaken)`, `Conflict(LicenseTaken)` and `Conflict(UploadAlreadyUsed)`.
    async fn update_profile(
        &self,
        expected: &Driver,
        patch: DriverPatch,
        change: Option<StatusChange>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord>;
    /// Moves the profile from `change.from` to `change.to` and records the change, provided
    /// the profile still has `change.from` and, when given, `change.expected_updated_at`. In
    /// the same transaction: reaching `approved` gives a passenger account the `driver` role
    /// (other roles are kept); leaving `approved` makes the driver unavailable; reaching
    /// `suspended` takes all the driver's buses off duty (`status = 'inactive'`, legacy L-25).
    /// Fails with `NotFound("driver")` and `Conflict(StaleState)`.
    async fn transition(
        &self,
        id: DriverId,
        change: StatusChange,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord>;
    /// Sets the availability of an approved driver. Fails with `NotFound("driver")` and
    /// `InvalidState` when the driver is not approved.
    async fn set_availability(
        &self,
        id: DriverId,
        available: bool,
        at: DateTime<Utc>,
    ) -> AppResult<DriverRecord>;
    /// The status history of a profile, newest first (empty for an unknown profile).
    async fn status_history(
        &self,
        id: DriverId,
        page: PageRequest,
    ) -> AppResult<Page<DriverStatusChange>>;
    /// The active accounts that review driver applications (administrators).
    async fn reviewers(&self) -> AppResult<Vec<AccountSummary>>;
}
