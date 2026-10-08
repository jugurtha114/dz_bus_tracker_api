//! Bodies of the driver programme. Driver profiles carry identity documents: they are only
//! ever returned to the driver themself and to reviewers (`driver:read`), never to other users
//! (legacy L-03).

use chrono::{DateTime, Utc};
use dz_app::drivers::DriverView;
use dz_domain::driver::{DriverStatus, DriverStatusChange};
use serde::{Deserialize, Serialize};
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;
use validator::Validate;

/// Review status of a driver profile.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum DriverStatusDto {
    /// Waiting for a review.
    Pending,
    /// May drive.
    Approved,
    /// Application refused; the applicant may re-apply.
    Rejected,
    /// Approval withdrawn until a reviewer reinstates the driver.
    Suspended,
}

impl From<DriverStatus> for DriverStatusDto {
    fn from(s: DriverStatus) -> Self {
        match s {
            DriverStatus::Pending => Self::Pending,
            DriverStatus::Approved => Self::Approved,
            DriverStatus::Rejected => Self::Rejected,
            DriverStatus::Suspended => Self::Suspended,
        }
    }
}

impl From<DriverStatusDto> for DriverStatus {
    fn from(s: DriverStatusDto) -> Self {
        match s {
            DriverStatusDto::Pending => Self::Pending,
            DriverStatusDto::Approved => Self::Approved,
            DriverStatusDto::Rejected => Self::Rejected,
            DriverStatusDto::Suspended => Self::Suspended,
        }
    }
}

/// The account behind a driver profile.
#[derive(Debug, Serialize, ToSchema)]
pub struct DriverUserDto {
    pub id: Uuid,
    pub email: String,
    pub first_name: String,
    pub last_name: String,
}

/// A driver profile, for the driver themself and for reviewers only.
#[derive(Debug, Serialize, ToSchema)]
pub struct DriverDto {
    pub id: Uuid,
    pub user: DriverUserDto,
    /// E.164 (`+2135XXXXXXXX`).
    pub phone_number: String,
    /// National identity number (18 digits).
    pub id_card_number: String,
    /// Driving licence number (upper-case).
    pub driver_license_number: String,
    /// Presigned download URL of the identity card (stable for an hour); `null` when file
    /// storage is not available.
    pub id_card_photo_url: Option<String>,
    /// Presigned download URL of the driving licence; `null` when file storage is not
    /// available.
    pub driver_license_photo_url: Option<String>,
    pub years_of_experience: u8,
    pub status: DriverStatusDto,
    /// Reason of the rejection or suspension; `null` in the other statuses.
    pub status_reason: Option<String>,
    pub status_changed_at: DateTime<Utc>,
    /// Whether the driver is available for service (approved drivers only).
    pub is_available: bool,
    /// Average rating (1–5) rounded to two decimals; `null` before the first rating.
    pub rating: Option<f64>,
    pub rating_count: u32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl From<DriverView> for DriverDto {
    fn from(view: DriverView) -> Self {
        let DriverView { record, id_card_photo_url, driver_license_photo_url } = view;
        let (d, u) = (record.driver, record.user);
        Self {
            id: d.id.as_uuid(),
            rating: d.rating(),
            user: DriverUserDto {
                id: u.id.as_uuid(),
                email: u.email.as_str().to_owned(),
                first_name: u.first_name.as_str().to_owned(),
                last_name: u.last_name.as_str().to_owned(),
            },
            phone_number: d.phone_number.as_str().to_owned(),
            id_card_number: d.id_card_number.as_str().to_owned(),
            driver_license_number: d.driver_license_number.as_str().to_owned(),
            id_card_photo_url,
            driver_license_photo_url,
            years_of_experience: d.years_of_experience.years(),
            status: d.status.into(),
            status_reason: Some(d.status_reason).filter(|r| !r.is_empty()),
            status_changed_at: d.status_changed_at,
            is_available: d.is_available,
            rating_count: d.rating_count,
            created_at: d.created_at,
            updated_at: d.updated_at,
        }
    }
}

/// One entry of a driver's status history.
#[derive(Debug, Serialize, ToSchema)]
pub struct DriverStatusChangeDto {
    pub id: Uuid,
    /// `null` for the application itself.
    pub from_status: Option<DriverStatusDto>,
    pub to_status: DriverStatusDto,
    /// Reason of a rejection or suspension; `null` otherwise.
    pub reason: Option<String>,
    /// The user who made the change (the driver or a reviewer); `null` for the system.
    pub changed_by: Option<Uuid>,
    pub created_at: DateTime<Utc>,
}

impl From<DriverStatusChange> for DriverStatusChangeDto {
    fn from(c: DriverStatusChange) -> Self {
        Self {
            id: c.id.as_uuid(),
            from_status: c.from.map(Into::into),
            to_status: c.to.into(),
            reason: Some(c.reason).filter(|r| !r.is_empty()),
            changed_by: c.changed_by.map(|u| u.as_uuid()),
            created_at: c.created_at,
        }
    }
}

/// An application to become a driver. The profile is always the caller's. Upload both
/// documents first (`POST /uploads`, purposes `driver_id_card` and `driver_license`).
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct DriverApplicationRequest {
    /// Algerian mobile number (`05…`, `06…`, `07…`, `+213…`).
    #[validate(length(max = 20))]
    #[schema(example = "0555123456")]
    pub phone_number: String,
    /// National identity number: 18 digits (spaces ignored).
    #[validate(length(max = 40))]
    #[schema(example = "109850123456789012")]
    pub id_card_number: String,
    /// Upload of the identity card (purpose `driver_id_card`).
    pub id_card_photo_upload_id: Uuid,
    /// Driving licence number: 1–20 characters `[A-Za-z0-9-]`.
    #[validate(length(max = 40))]
    #[schema(example = "DZ-16-123456")]
    pub driver_license_number: String,
    /// Upload of the driving licence (purpose `driver_license`).
    pub driver_license_photo_upload_id: Uuid,
    /// 0–60.
    pub years_of_experience: i64,
}

/// Changes to the caller's driver profile. A new identity document (number or photo) sends an
/// approved profile back to review.
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateDriverRequest {
    #[validate(length(max = 20))]
    pub phone_number: Option<String>,
    /// 0–60.
    pub years_of_experience: Option<i64>,
    #[validate(length(max = 40))]
    pub id_card_number: Option<String>,
    /// A new upload of the identity card (purpose `driver_id_card`).
    pub id_card_photo_upload_id: Option<Uuid>,
    #[validate(length(max = 40))]
    pub driver_license_number: Option<String>,
    /// A new upload of the driving licence (purpose `driver_license`).
    pub driver_license_photo_upload_id: Option<Uuid>,
}

/// Availability of an approved driver.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AvailabilityRequest {
    pub is_available: bool,
}

/// The reason of a rejection or suspension, shown to the driver.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReviewReasonRequest {
    /// 1–1000 characters.
    #[schema(example = "The identity card scan is unreadable.")]
    pub reason: String,
}

/// The version of the profile the reviewer examined. An approval only applies to the documents
/// that were reviewed: if the profile changed since (e.g. the applicant replaced a document),
/// it is refused with `409 stale_state` and the profile must be reviewed again.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ApproveDriverRequest {
    /// `updated_at` of the profile as read by the reviewer (RFC 3339, as returned by
    /// `GET /drivers/{id}`, microsecond precision).
    #[schema(example = "2026-10-08T09:41:27.512947Z")]
    pub expected_updated_at: DateTime<Utc>,
}

/// Filters of the admin driver list.
#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct DriverListQuery {
    pub status: Option<DriverStatusDto>,
    pub is_available: Option<bool>,
    /// Opaque cursor from a previous page.
    pub cursor: Option<String>,
    /// Page size (1–100, default 20).
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}
