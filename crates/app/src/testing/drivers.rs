//! In-memory driver profiles: the same contracts as `dz_infra::pg::drivers`, with the database
//! constraints (`drivers_user_key`, `drivers_id_card_number_key`,
//! `drivers_driver_license_number_key`) checked by hand. There are no buses in memory, so a
//! suspension has no bus to take off duty here.

use std::collections::HashMap;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_domain::driver::{Driver, DriverStatus, DriverStatusChange};
use dz_domain::ids::{DriverId, UserId};
use dz_domain::ConflictKind;
use dz_domain::upload::UploadStatus;
use dz_domain::user::Role;

use super::{InMemoryStore, State, mark_attached};
use crate::drivers::ports::{
    AccountSummary, DriverFilter, DriverPatch, DriverRecord, DriverRepository, NewDriver,
    StatusChange,
};
use crate::error::{AppError, AppResult};
use crate::pagination::{Cursor, Page, PageRequest};
use crate::ports::{ClaimedUpload, WriteEffects};

/// The driver part of the in-memory database.
#[derive(Debug, Default)]
pub(super) struct DriversState {
    drivers: HashMap<DriverId, Driver>,
    history: Vec<DriverStatusChange>,
}

fn account(state: &State, id: UserId) -> AccountSummary {
    let row = &state.users[&id];
    AccountSummary {
        id,
        email: row.user.email.clone(),
        first_name: row.user.first_name.clone(),
        last_name: row.user.last_name.clone(),
        language: row.profile.language,
    }
}

fn record(state: &State, id: DriverId) -> AppResult<DriverRecord> {
    let driver = state.drivers.drivers.get(&id).ok_or(AppError::NotFound("driver"))?.clone();
    let user = account(state, driver.user_id);
    Ok(DriverRecord { driver, user })
}

/// What `UPDATE uploads … WHERE status = 'pending'` does for every claimed upload of a write,
/// all or nothing.
fn attach_all(state: &mut State, claimed: &[&ClaimedUpload], at: DateTime<Utc>) -> AppResult<()> {
    let pending = |c: &&ClaimedUpload| {
        state.uploads.get(&c.id).is_some_and(|u| u.status == UploadStatus::Pending)
    };
    if !claimed.iter().all(pending) {
        return Err(AppError::Conflict(ConflictKind::UploadAlreadyUsed));
    }
    for upload in claimed {
        mark_attached(state, upload, at)?;
    }
    Ok(())
}

/// The unique constraints of `drivers`, for a profile `id` with these numbers.
fn check_unique(state: &State, id: DriverId, driver: &Driver) -> AppResult<()> {
    let others = || state.drivers.drivers.values().filter(|d| d.id != id);
    if others().any(|d| d.user_id == driver.user_id) {
        return Err(AppError::Conflict(ConflictKind::DriverProfileExists));
    }
    if others().any(|d| d.id_card_number == driver.id_card_number) {
        return Err(AppError::Conflict(ConflictKind::IdCardTaken));
    }
    if others().any(|d| d.driver_license_number == driver.driver_license_number) {
        return Err(AppError::Conflict(ConflictKind::LicenseTaken));
    }
    Ok(())
}

/// Applies `change` to `driver` and its consequences on the account; returns the history row.
fn apply_change(
    state: &mut State,
    driver: &mut Driver,
    change: &StatusChange,
) -> DriverStatusChange {
    driver.status = change.to;
    driver.status_reason =
        change.reason.as_ref().map(|r| r.as_str().to_owned()).unwrap_or_default();
    driver.status_changed_at = change.at;
    driver.updated_at = change.at;
    if change.to != DriverStatus::Approved {
        driver.is_available = false;
    }
    // Approval gives a passenger account the driver role; other roles are kept.
    let promoted = change.to == DriverStatus::Approved;
    let account = state.users.get_mut(&driver.user_id);
    if let Some(row) = account.filter(|r| promoted && r.user.role == Role::Passenger) {
        row.user.role = Role::Driver;
        row.user.updated_at = change.at;
    }
    DriverStatusChange {
        id: change.id,
        driver_id: driver.id,
        from: change.from,
        to: change.to,
        reason: driver.status_reason.clone(),
        changed_by: change.changed_by,
        created_at: change.at,
    }
}

/// Keyset pagination, newest first, as the SQL queries do.
fn page_of<T>(mut rows: Vec<T>, page: PageRequest, key: impl Fn(&T) -> Cursor) -> Page<T> {
    let sort_key = |row: &T| {
        let cursor = key(row);
        (cursor.created_at, cursor.id)
    };
    rows.retain(|row| page.after.is_none_or(|c| sort_key(row) < (c.created_at, c.id)));
    rows.sort_by_key(|row| std::cmp::Reverse(sort_key(row)));
    rows.truncate(page.fetch_limit() as usize);
    Page::from_rows(rows, page, key)
}

fn driver_cursor(r: &DriverRecord) -> Cursor {
    Cursor { created_at: r.driver.created_at, id: r.driver.id.as_uuid() }
}

#[async_trait]
impl DriverRepository for InMemoryStore {
    async fn insert(&self, new: NewDriver, effects: WriteEffects) -> AppResult<DriverRecord> {
        let mut state = self.state();
        let at = new.application.at;
        let mut driver = Driver {
            id: new.id,
            user_id: new.user_id,
            phone_number: new.phone_number,
            id_card_number: new.id_card_number,
            id_card_photo_key: new.id_card_photo.object_key.clone(),
            driver_license_number: new.driver_license_number,
            driver_license_photo_key: new.driver_license_photo.object_key.clone(),
            years_of_experience: new.years_of_experience,
            status: new.application.to,
            status_reason: String::new(),
            status_changed_at: at,
            is_available: false,
            rating_sum: 0,
            rating_count: 0,
            created_at: at,
            updated_at: at,
        };
        check_unique(&state, new.id, &driver)?;
        attach_all(&mut state, &[&new.id_card_photo, &new.driver_license_photo], at)?;
        let entry = apply_change(&mut state, &mut driver, &new.application);
        state.drivers.drivers.insert(driver.id, driver);
        state.drivers.history.push(entry);
        state.persist(effects);
        record(&state, new.id)
    }

    async fn find(&self, id: DriverId) -> AppResult<Option<DriverRecord>> {
        let state = self.state();
        Ok(record(&state, id).ok())
    }

    async fn find_by_user(&self, user_id: UserId) -> AppResult<Option<DriverRecord>> {
        let state = self.state();
        let id = state.drivers.drivers.values().find(|d| d.user_id == user_id).map(|d| d.id);
        Ok(id.and_then(|id| record(&state, id).ok()))
    }

    async fn list(&self, filter: DriverFilter, page: PageRequest) -> AppResult<Page<DriverRecord>> {
        let state = self.state();
        let rows: Vec<DriverRecord> = state
            .drivers
            .drivers
            .values()
            .filter(|d| filter.status.is_none_or(|s| d.status == s))
            .filter(|d| filter.is_available.is_none_or(|a| d.is_available == a))
            .map(|d| record(&state, d.id))
            .collect::<AppResult<_>>()?;
        Ok(page_of(rows, page, driver_cursor))
    }

    async fn update_profile(
        &self,
        expected: &Driver,
        patch: DriverPatch,
        change: Option<StatusChange>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        let mut state = self.state();
        let id = expected.id;
        let mut driver =
            state.drivers.drivers.get(&id).ok_or(AppError::NotFound("driver"))?.clone();
        if driver.status != expected.status
            || driver.id_card_photo_key != expected.id_card_photo_key
            || driver.driver_license_photo_key != expected.driver_license_photo_key
        {
            return Err(AppError::Conflict(ConflictKind::StaleState));
        }
        if let Some(phone) = patch.phone_number {
            driver.phone_number = phone;
        }
        if let Some(years) = patch.years_of_experience {
            driver.years_of_experience = years;
        }
        if let Some(number) = patch.id_card_number {
            driver.id_card_number = number;
        }
        if let Some(number) = patch.driver_license_number {
            driver.driver_license_number = number;
        }
        let claimed: Vec<&ClaimedUpload> =
            patch.id_card_photo.iter().chain(patch.driver_license_photo.iter()).collect();
        if let Some(photo) = &patch.id_card_photo {
            driver.id_card_photo_key.clone_from(&photo.object_key);
        }
        if let Some(photo) = &patch.driver_license_photo {
            driver.driver_license_photo_key.clone_from(&photo.object_key);
        }
        driver.updated_at = at;
        check_unique(&state, id, &driver)?;
        attach_all(&mut state, &claimed, at)?;
        if let Some(change) = &change {
            let entry = apply_change(&mut state, &mut driver, change);
            state.drivers.history.push(entry);
        }
        state.drivers.drivers.insert(id, driver);
        state.persist(effects);
        record(&state, id)
    }

    async fn transition(
        &self,
        id: DriverId,
        change: StatusChange,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        let mut state = self.state();
        let mut driver =
            state.drivers.drivers.get(&id).ok_or(AppError::NotFound("driver"))?.clone();
        let changed = change.expected_updated_at.is_some_and(|at| at != driver.updated_at);
        if Some(driver.status) != change.from || changed {
            return Err(AppError::Conflict(ConflictKind::StaleState));
        }
        let entry = apply_change(&mut state, &mut driver, &change);
        state.drivers.drivers.insert(id, driver);
        state.drivers.history.push(entry);
        state.persist(effects);
        record(&state, id)
    }

    async fn set_availability(
        &self,
        id: DriverId,
        available: bool,
        at: DateTime<Utc>,
    ) -> AppResult<DriverRecord> {
        let mut state = self.state();
        let driver = state.drivers.drivers.get_mut(&id).ok_or(AppError::NotFound("driver"))?;
        if driver.status != DriverStatus::Approved {
            return Err(AppError::InvalidState("driver not approved"));
        }
        driver.is_available = available;
        driver.updated_at = at;
        record(&state, id)
    }

    async fn status_history(
        &self,
        id: DriverId,
        page: PageRequest,
    ) -> AppResult<Page<DriverStatusChange>> {
        let state = self.state();
        let rows = state.drivers.history.iter().filter(|e| e.driver_id == id).cloned().collect();
        Ok(page_of(rows, page, |e: &DriverStatusChange| Cursor {
            created_at: e.created_at,
            id: e.id.as_uuid(),
        }))
    }

    async fn reviewers(&self) -> AppResult<Vec<AccountSummary>> {
        let state = self.state();
        let mut reviewers: Vec<AccountSummary> = state
            .users
            .values()
            .filter(|r| r.user.role == Role::Admin && r.user.is_active)
            .map(|r| account(&state, r.user.id))
            .collect();
        reviewers.sort_by(|a, b| a.email.as_str().cmp(b.email.as_str()));
        Ok(reviewers)
    }
}

impl InMemoryStore {
    /// Changes the role of an account directly (e.g. an applicant promoted to administrator).
    pub fn set_role(&self, id: UserId, role: Role) {
        self.state().users.get_mut(&id).unwrap().user.role = role;
    }

    /// Whether an account is active, to simulate deactivated reviewers.
    pub fn set_active(&self, id: UserId, active: bool) {
        self.state().users.get_mut(&id).unwrap().user.is_active = active;
    }
}
