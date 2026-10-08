//! Driver profiles, their status history and the consequences of status changes.
//!
//! Status changes are compare-and-set (`UPDATE drivers … WHERE status = $expected`), so two
//! concurrent reviews cannot both apply: the second one updates no row and reports
//! `Conflict(StaleState)`. Approvals also compare `updated_at` with the version the reviewer
//! examined, so documents changed meanwhile are never approved. The row lock taken by that
//! `UPDATE` serialises the rest of the transaction (history, account role, buses) per driver.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::drivers::ports::{
    AccountSummary, DriverFilter, DriverPatch, DriverRecord, DriverRepository, NewDriver,
    StatusChange,
};
use dz_app::pagination::{Cursor, Page, PageRequest};
use dz_app::ports::WriteEffects;
use dz_app::{AppError, AppResult};
use dz_domain::driver::{
    Driver, DriverStatus, DriverStatusChange, LicenseNumber, NationalIdNumber, StatusReason,
    YearsOfExperience,
};
use dz_domain::ids::{DriverId, DriverStatusChangeId, UserId};
use dz_domain::user::{Email, PersonName, PhoneNumber};
use dz_domain::{ConflictKind, Lang};
use sqlx::{PgExecutor, Postgres, Transaction};
use uuid::Uuid;

use super::{PgStore, db_error, effects, uploads, violated_constraint};

fn corrupt(what: &str) -> AppError {
    AppError::Internal(anyhow::anyhow!("invalid {what} in database"))
}

/// A driver with its account, as selected by [`load`] and the list.
struct DriverRow {
    id: Uuid,
    user_id: Uuid,
    phone_number: String,
    id_card_number: String,
    id_card_photo_key: String,
    driver_license_number: String,
    driver_license_photo_key: String,
    years_of_experience: i16,
    status: String,
    status_reason: String,
    status_changed_at: DateTime<Utc>,
    is_available: bool,
    rating_sum: i32,
    rating_count: i32,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
    email: String,
    first_name: String,
    last_name: String,
    language: String,
}

fn status(raw: &str) -> AppResult<DriverStatus> {
    DriverStatus::parse(raw).map_err(|_| corrupt("driver status"))
}

impl DriverRow {
    fn into_record(self) -> AppResult<DriverRecord> {
        let count = |n: i32| u32::try_from(n).map_err(|_| corrupt("rating"));
        let driver = Driver {
            id: DriverId::from_uuid(self.id),
            user_id: UserId::from_uuid(self.user_id),
            phone_number: PhoneNumber::from_trusted(self.phone_number),
            id_card_number: NationalIdNumber::from_trusted(self.id_card_number),
            id_card_photo_key: self.id_card_photo_key,
            driver_license_number: LicenseNumber::from_trusted(self.driver_license_number),
            driver_license_photo_key: self.driver_license_photo_key,
            years_of_experience: YearsOfExperience::parse(i64::from(self.years_of_experience))
                .map_err(|_| corrupt("experience"))?,
            status: status(&self.status)?,
            status_reason: self.status_reason,
            status_changed_at: self.status_changed_at,
            is_available: self.is_available,
            rating_sum: count(self.rating_sum)?,
            rating_count: count(self.rating_count)?,
            created_at: self.created_at,
            updated_at: self.updated_at,
        };
        let user = AccountSummary {
            id: driver.user_id,
            email: Email::from_trusted(self.email),
            first_name: PersonName::from_trusted(self.first_name),
            last_name: PersonName::from_trusted(self.last_name),
            language: Lang::from_code(&self.language).unwrap_or_default(),
        };
        Ok(DriverRecord { driver, user })
    }
}

struct StatusChangeRow {
    id: Uuid,
    driver_id: Uuid,
    from_status: Option<String>,
    to_status: String,
    reason: String,
    changed_by: Option<Uuid>,
    created_at: DateTime<Utc>,
}

impl StatusChangeRow {
    fn into_change(self) -> AppResult<DriverStatusChange> {
        Ok(DriverStatusChange {
            id: DriverStatusChangeId::from_uuid(self.id),
            driver_id: DriverId::from_uuid(self.driver_id),
            from: self.from_status.as_deref().map(status).transpose()?,
            to: status(&self.to_status)?,
            reason: self.reason,
            changed_by: self.changed_by.map(UserId::from_uuid),
            created_at: self.created_at,
        })
    }
}

struct AccountRow {
    id: Uuid,
    email: String,
    first_name: String,
    last_name: String,
    language: String,
}

/// The profile `id` with its account.
async fn load<'e>(executor: impl PgExecutor<'e>, id: DriverId) -> AppResult<Option<DriverRecord>> {
    sqlx::query_as!(
        DriverRow,
        r#"
        SELECT d.id, d.user_id, d.phone_number, d.id_card_number, d.id_card_photo_key,
               d.driver_license_number, d.driver_license_photo_key, d.years_of_experience,
               d.status, d.status_reason, d.status_changed_at, d.is_available, d.rating_sum,
               d.rating_count, d.created_at, d.updated_at,
               u.email, u.first_name, u.last_name, p.language
        FROM drivers d
        JOIN users u ON u.id = d.user_id
        JOIN profiles p ON p.user_id = d.user_id
        WHERE d.id = $1
        "#,
        id.as_uuid(),
    )
    .fetch_optional(executor)
    .await
    .map_err(db_error)?
    .map(DriverRow::into_record)
    .transpose()
}

/// Reads back the profile written by the current transaction.
async fn reload(tx: &mut Transaction<'_, Postgres>, id: DriverId) -> AppResult<DriverRecord> {
    load(&mut **tx, id).await?.ok_or(AppError::NotFound("driver"))
}

/// Appends `change` to the history of `driver`.
async fn log_change(
    tx: &mut Transaction<'_, Postgres>,
    driver: DriverId,
    change: &StatusChange,
) -> AppResult<()> {
    sqlx::query!(
        r#"
        INSERT INTO driver_status_log (id, driver_id, from_status, to_status, reason, changed_by,
                                       created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        "#,
        change.id.as_uuid(),
        driver.as_uuid(),
        change.from.map(DriverStatus::as_str),
        change.to.as_str(),
        change.reason.as_ref().map_or("", StatusReason::as_str),
        change.changed_by.map(|u| u.as_uuid()),
        change.at,
    )
    .execute(&mut **tx)
    .await
    .map_err(db_error)?;
    Ok(())
}

/// What reaching `to` implies beyond the profile row (same transaction).
async fn apply_consequences(
    tx: &mut Transaction<'_, Postgres>,
    driver: DriverId,
    user: Uuid,
    to: DriverStatus,
    at: DateTime<Utc>,
) -> AppResult<()> {
    match to {
        // A privilege gain needs no session revocation: it takes effect at the next refresh.
        // Administrators keep their role.
        DriverStatus::Approved => {
            sqlx::query!(
                r#"
                UPDATE users SET role = 'driver', updated_at = $2
                WHERE id = $1 AND role = 'passenger'
                "#,
                user,
                at,
            )
            .execute(&mut **tx)
            .await
            .map_err(db_error)?;
        }
        // Legacy L-25: a suspended driver's buses are taken off duty (`buses_driver_idx`).
        DriverStatus::Suspended => {
            sqlx::query!(
                r#"
                UPDATE buses SET status = 'inactive', updated_at = $2
                WHERE driver_id = $1 AND status <> 'inactive'
                "#,
                driver.as_uuid(),
                at,
            )
            .execute(&mut **tx)
            .await
            .map_err(db_error)?;
        }
        DriverStatus::Pending | DriverStatus::Rejected => {}
    }
    Ok(())
}

/// `NotFound` when the profile does not exist, otherwise `Conflict(StaleState)`: a guarded
/// `UPDATE` matched no row because the profile changed concurrently.
async fn missing_or_stale(tx: &mut Transaction<'_, Postgres>, id: DriverId) -> AppError {
    let exists = sqlx::query_scalar!(
        r#"SELECT EXISTS (SELECT 1 FROM drivers WHERE id = $1) AS "exists!""#,
        id.as_uuid(),
    )
    .fetch_one(&mut **tx)
    .await;
    match exists {
        Ok(true) => AppError::Conflict(ConflictKind::StaleState),
        Ok(false) => AppError::NotFound("driver"),
        Err(e) => db_error(e),
    }
}

/// Maps the unique constraints of `drivers` to conflicts.
fn unique_conflict(error: sqlx::Error) -> AppError {
    match violated_constraint(&error) {
        Some("drivers_user_key") => AppError::Conflict(ConflictKind::DriverProfileExists),
        Some("drivers_id_card_number_key") => AppError::Conflict(ConflictKind::IdCardTaken),
        Some("drivers_driver_license_number_key") => {
            AppError::Conflict(ConflictKind::LicenseTaken)
        }
        _ => db_error(error),
    }
}

fn smallint(years: YearsOfExperience) -> i16 {
    i16::from(years.years())
}

#[async_trait]
impl DriverRepository for PgStore {
    async fn insert(&self, driver: NewDriver, effects: WriteEffects) -> AppResult<DriverRecord> {
        let change = &driver.application;
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO drivers (id, user_id, phone_number, id_card_number, id_card_photo_key,
                                 driver_license_number, driver_license_photo_key,
                                 years_of_experience, status, status_reason, status_changed_at,
                                 is_available, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, '', $10, false, $10, $10)
            "#,
            driver.id.as_uuid(),
            driver.user_id.as_uuid(),
            driver.phone_number.as_str(),
            driver.id_card_number.as_str(),
            driver.id_card_photo.object_key,
            driver.driver_license_number.as_str(),
            driver.driver_license_photo.object_key,
            smallint(driver.years_of_experience),
            change.to.as_str(),
            change.at,
        )
        .execute(&mut *tx)
        .await
        .map_err(unique_conflict)?;
        uploads::mark_attached(&mut tx, &driver.id_card_photo, change.at).await?;
        uploads::mark_attached(&mut tx, &driver.driver_license_photo, change.at).await?;
        log_change(&mut tx, driver.id, change).await?;
        let record = reload(&mut tx, driver.id).await?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(record)
    }

    async fn find(&self, id: DriverId) -> AppResult<Option<DriverRecord>> {
        load(self.pool(), id).await
    }

    async fn find_by_user(&self, user_id: UserId) -> AppResult<Option<DriverRecord>> {
        // Served by the unique index of `drivers_user_key`.
        let id = sqlx::query_scalar!("SELECT id FROM drivers WHERE user_id = $1", user_id.as_uuid())
            .fetch_optional(self.pool())
            .await
            .map_err(db_error)?;
        match id {
            Some(id) => load(self.pool(), DriverId::from_uuid(id)).await,
            None => Ok(None),
        }
    }

    async fn list(&self, filter: DriverFilter, page: PageRequest) -> AppResult<Page<DriverRecord>> {
        let rows = sqlx::query_as!(
            DriverRow,
            r#"
            SELECT d.id, d.user_id, d.phone_number, d.id_card_number, d.id_card_photo_key,
                   d.driver_license_number, d.driver_license_photo_key, d.years_of_experience,
                   d.status, d.status_reason, d.status_changed_at, d.is_available, d.rating_sum,
                   d.rating_count, d.created_at, d.updated_at,
                   u.email, u.first_name, u.last_name, p.language
            FROM drivers d
            JOIN users u ON u.id = d.user_id
            JOIN profiles p ON p.user_id = d.user_id
            WHERE ($1::text IS NULL OR d.status = $1)
              AND ($2::bool IS NULL OR d.is_available = $2)
              AND ($3::timestamptz IS NULL OR (d.created_at, d.id) < ($3, $4))
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT $5
            "#,
            filter.status.map(DriverStatus::as_str),
            filter.is_available,
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let records = rows.into_iter().map(DriverRow::into_record).collect::<AppResult<_>>()?;
        Ok(Page::from_rows(records, page, |r: &DriverRecord| Cursor {
            created_at: r.driver.created_at,
            id: r.driver.id.as_uuid(),
        }))
    }

    async fn update_profile(
        &self,
        expected: &Driver,
        patch: DriverPatch,
        change: Option<StatusChange>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Compare-and-set on the status and on the photos the effects delete.
        let updated = sqlx::query_scalar!(
            r#"
            UPDATE drivers SET
                phone_number = COALESCE($2, phone_number),
                years_of_experience = COALESCE($3, years_of_experience),
                id_card_number = COALESCE($4, id_card_number),
                id_card_photo_key = COALESCE($5, id_card_photo_key),
                driver_license_number = COALESCE($6, driver_license_number),
                driver_license_photo_key = COALESCE($7, driver_license_photo_key),
                status = COALESCE($8, status),
                status_reason = CASE WHEN $8::text IS NULL THEN status_reason ELSE $9 END,
                status_changed_at = CASE WHEN $8::text IS NULL THEN status_changed_at ELSE $10 END,
                is_available = is_available AND COALESCE($8, status) = 'approved',
                updated_at = $10
            WHERE id = $1 AND status = $11
              AND id_card_photo_key = $12 AND driver_license_photo_key = $13
            RETURNING user_id
            "#,
            expected.id.as_uuid(),
            patch.phone_number.as_ref().map(PhoneNumber::as_str),
            patch.years_of_experience.map(smallint),
            patch.id_card_number.as_ref().map(NationalIdNumber::as_str),
            patch.id_card_photo.as_ref().map(|c| c.object_key.as_str()),
            patch.driver_license_number.as_ref().map(LicenseNumber::as_str),
            patch.driver_license_photo.as_ref().map(|c| c.object_key.as_str()),
            change.as_ref().map(|c| c.to.as_str()),
            change.as_ref().and_then(|c| c.reason.as_ref()).map_or("", StatusReason::as_str),
            at,
            expected.status.as_str(),
            expected.id_card_photo_key,
            expected.driver_license_photo_key,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(unique_conflict)?;
        let Some(user) = updated else {
            return Err(missing_or_stale(&mut tx, expected.id).await);
        };
        for claimed in patch.id_card_photo.iter().chain(&patch.driver_license_photo) {
            uploads::mark_attached(&mut tx, claimed, at).await?;
        }
        if let Some(change) = &change {
            log_change(&mut tx, expected.id, change).await?;
            apply_consequences(&mut tx, expected.id, user, change.to, at).await?;
        }
        let record = reload(&mut tx, expected.id).await?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(record)
    }

    async fn transition(
        &self,
        id: DriverId,
        change: StatusChange,
        effects: WriteEffects,
    ) -> AppResult<DriverRecord> {
        let Some(from) = change.from else {
            return Err(AppError::Internal(anyhow::anyhow!("a transition needs a source status")));
        };
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Compare-and-set on the status and, for approvals, on the reviewed version.
        let updated = sqlx::query_scalar!(
            r#"
            UPDATE drivers SET
                status = $3,
                status_reason = $4,
                status_changed_at = $5,
                is_available = is_available AND $3 = 'approved',
                updated_at = $5
            WHERE id = $1 AND status = $2
              AND ($6::timestamptz IS NULL OR updated_at = $6)
            RETURNING user_id
            "#,
            id.as_uuid(),
            from.as_str(),
            change.to.as_str(),
            change.reason.as_ref().map_or("", StatusReason::as_str),
            change.at,
            change.expected_updated_at,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?;
        let Some(user) = updated else {
            return Err(missing_or_stale(&mut tx, id).await);
        };
        log_change(&mut tx, id, &change).await?;
        apply_consequences(&mut tx, id, user, change.to, change.at).await?;
        let record = reload(&mut tx, id).await?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(record)
    }

    async fn set_availability(
        &self,
        id: DriverId,
        available: bool,
        at: DateTime<Utc>,
    ) -> AppResult<DriverRecord> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let updated = sqlx::query!(
            r#"
            UPDATE drivers SET is_available = $2, updated_at = $3
            WHERE id = $1 AND status = 'approved'
            "#,
            id.as_uuid(),
            available,
            at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        if updated.rows_affected() == 0 {
            return Err(match missing_or_stale(&mut tx, id).await {
                AppError::Conflict(ConflictKind::StaleState) => {
                    AppError::InvalidState("driver not approved")
                }
                other => other,
            });
        }
        let record = reload(&mut tx, id).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(record)
    }

    async fn status_history(
        &self,
        id: DriverId,
        page: PageRequest,
    ) -> AppResult<Page<DriverStatusChange>> {
        // `driver_status_log_driver_idx` serves the filter and the order.
        let rows = sqlx::query_as!(
            StatusChangeRow,
            r#"
            SELECT id, driver_id, from_status, to_status, reason, changed_by, created_at
            FROM driver_status_log
            WHERE driver_id = $1
              AND ($2::timestamptz IS NULL OR (created_at, id) < ($2, $3))
            ORDER BY created_at DESC, id DESC
            LIMIT $4
            "#,
            id.as_uuid(),
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let changes = rows.into_iter().map(StatusChangeRow::into_change).collect::<AppResult<_>>()?;
        Ok(Page::from_rows(changes, page, |c: &DriverStatusChange| Cursor {
            created_at: c.created_at,
            id: c.id.as_uuid(),
        }))
    }

    async fn reviewers(&self) -> AppResult<Vec<AccountSummary>> {
        // `users_role_created_idx` finds the administrators.
        let rows = sqlx::query_as!(
            AccountRow,
            r#"
            SELECT u.id, u.email, u.first_name, u.last_name, p.language
            FROM users u
            JOIN profiles p ON p.user_id = u.id
            WHERE u.role = 'admin' AND u.is_active
            ORDER BY u.email
            "#,
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        Ok(rows
            .into_iter()
            .map(|r| AccountSummary {
                id: UserId::from_uuid(r.id),
                email: Email::from_trusted(r.email),
                first_name: PersonName::from_trusted(r.first_name),
                last_name: PersonName::from_trusted(r.last_name),
                language: Lang::from_code(&r.language).unwrap_or_default(),
            })
            .collect())
    }
}
