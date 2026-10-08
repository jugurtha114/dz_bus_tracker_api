//! Bodies of the network catalogue: stops, lines, line stops, routes and schedules.
//!
//! Coordinates are `{"lat", "lng"}` objects (WGS 84 degrees), routes are GeoJSON
//! `LineString`s (positions `[lng, lat]`), distances are metres, durations seconds, times of
//! day `HH:MM` and weekdays ISO 8601 (1 = Monday … 7 = Sunday). Field values are validated by
//! the domain, so violations carry the same codes whatever the entry point.

use chrono::{DateTime, Utc};
use dz_app::network::{NearbyStopView, StopView};
use dz_domain::geo::{GeoPoint, LineGeometry};
use dz_domain::network::{Line, LineStop, Schedule, Stop};
use dz_domain::{Violation, Violations};
use serde::{Deserialize, Serialize};
use utoipa::{IntoParams, ToSchema};
use uuid::Uuid;
use validator::Validate;

use super::double_option;

/// A position in degrees (WGS 84): `lat` in [-90, 90], `lng` in [-180, 180].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LatLng {
    #[schema(example = 36.7538)]
    pub lat: f64,
    #[schema(example = 3.0588)]
    pub lng: f64,
}

impl From<GeoPoint> for LatLng {
    fn from(p: GeoPoint) -> Self {
        Self { lat: p.lat(), lng: p.lng() }
    }
}

/// Distances are reported to the decimetre.
fn round_m(metres: f64) -> f64 {
    (metres * 10.0).round() / 10.0
}

// --- Stops ---------------------------------------------------------------------------------------

/// A bus stop.
#[derive(Debug, Serialize, ToSchema)]
pub struct StopDto {
    pub id: Uuid,
    pub name: String,
    pub location: LatLng,
    pub address: String,
    pub wilaya: String,
    pub commune: String,
    pub description: String,
    /// Tags such as `shelter`, `bench`, `wheelchair_access`.
    pub features: Vec<String>,
    /// Inactive stops are only visible to stop administrators.
    pub is_active: bool,
    /// Presigned download URL of the photo (stable for an hour); `null` without photo or when
    /// file storage is not available.
    pub photo_url: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl From<StopView> for StopDto {
    fn from(view: StopView) -> Self {
        let s = view.stop;
        Self {
            id: s.id.as_uuid(),
            name: s.name.as_str().to_owned(),
            location: s.location.into(),
            address: s.address,
            wilaya: s.wilaya,
            commune: s.commune,
            description: s.description,
            features: s.features.into_vec(),
            is_active: s.is_active,
            photo_url: view.photo_url,
            created_at: s.created_at,
            updated_at: s.updated_at,
        }
    }
}

/// A stop found around a point.
#[derive(Debug, Serialize, ToSchema)]
pub struct NearbyStopDto {
    #[serde(flatten)]
    pub stop: StopDto,
    /// Distance from the searched point, in metres.
    #[schema(example = 182.4)]
    pub distance_m: f64,
}

impl From<NearbyStopView> for NearbyStopDto {
    fn from(n: NearbyStopView) -> Self {
        Self { stop: n.view.into(), distance_m: round_m(n.distance_m) }
    }
}

/// The essentials of a stop, as listed on a line.
#[derive(Debug, Serialize, ToSchema)]
pub struct StopSummaryDto {
    pub id: Uuid,
    pub name: String,
    pub location: LatLng,
    /// Inactive stops stay on their lines (buses pass them) but cannot be boarded.
    pub is_active: bool,
}

impl From<Stop> for StopSummaryDto {
    fn from(s: Stop) -> Self {
        Self {
            id: s.id.as_uuid(),
            name: s.name.as_str().to_owned(),
            location: s.location.into(),
            is_active: s.is_active,
        }
    }
}

/// Filters of `GET /stops`.
#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct StopListQuery {
    /// Part of the name (2–100 characters, case-insensitive).
    pub q: Option<String>,
    /// Wilaya (exact, case-insensitive).
    pub wilaya: Option<String>,
    /// Commune (exact, case-insensitive).
    pub commune: Option<String>,
    /// Only stops served by this line.
    pub line_id: Option<Uuid>,
    /// Activity filter, for stop administrators only (`403` otherwise).
    pub is_active: Option<bool>,
    pub cursor: Option<String>,
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}

/// Parameters of `GET /stops/nearby`.
#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct NearbyQuery {
    /// Latitude of the point (degrees).
    pub lat: f64,
    /// Longitude of the point (degrees).
    pub lng: f64,
    /// Search radius in metres (10–5000, default 500).
    pub radius_m: Option<i64>,
    /// Number of stops (1–50, default 20).
    pub limit: Option<i64>,
}

/// A new stop.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateStopRequest {
    /// 1–100 characters.
    #[schema(example = "Place des Martyrs")]
    pub name: String,
    pub location: LatLng,
    /// At most 255 characters.
    pub address: Option<String>,
    /// At most 100 characters.
    pub wilaya: Option<String>,
    /// At most 100 characters.
    pub commune: Option<String>,
    /// At most 2000 characters.
    pub description: Option<String>,
    /// At most 20 tags of 1–40 characters `[a-z0-9_]` (lower-cased).
    pub features: Option<Vec<String>>,
    /// Default `true`.
    pub is_active: Option<bool>,
}

/// Changes to a stop; absent fields are unchanged and an empty text clears a text field.
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateStopRequest {
    pub name: Option<String>,
    pub location: Option<LatLng>,
    pub address: Option<String>,
    pub wilaya: Option<String>,
    pub commune: Option<String>,
    pub description: Option<String>,
    /// Replaces the whole list.
    pub features: Option<Vec<String>>,
    pub is_active: Option<bool>,
}

/// Attaches a completed upload as a photo.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetPhotoRequest {
    /// Id returned by `POST /uploads` (purpose `stop_photo`), after the file was uploaded.
    pub upload_id: Uuid,
}

// --- Lines ---------------------------------------------------------------------------------------

/// A bus line.
#[derive(Debug, Serialize, ToSchema)]
pub struct LineDto {
    pub id: Uuid,
    /// Upper-case public code, immutable.
    #[schema(example = "L1")]
    pub code: String,
    pub name: String,
    pub description: String,
    /// `#RRGGBB`.
    #[schema(example = "#1E88E5")]
    pub color: String,
    /// Announced headway in minutes, when the line runs at a fixed frequency.
    pub frequency_minutes: Option<u16>,
    /// Fare in Algerian dinars.
    pub fare_dza: Option<u32>,
    /// Inactive lines are only visible to line administrators.
    pub is_active: bool,
    pub stops_count: u32,
    /// Whether `GET /lines/{id}/route` has a geometry.
    pub has_route: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl From<Line> for LineDto {
    fn from(l: Line) -> Self {
        Self {
            id: l.id.as_uuid(),
            code: l.code.as_str().to_owned(),
            name: l.name.as_str().to_owned(),
            description: l.description,
            color: l.color.as_str().to_owned(),
            frequency_minutes: l.frequency_minutes.map(|f| f.minutes()),
            fare_dza: l.fare_dza.map(|f| f.dzd()),
            is_active: l.is_active,
            stops_count: l.stops_count,
            has_route: l.has_route,
            created_at: l.created_at,
            updated_at: l.updated_at,
        }
    }
}

/// Filters of `GET /lines`.
#[derive(Debug, Deserialize, Validate, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct LineListQuery {
    /// Part of the code or name (2–100 characters, case-insensitive).
    pub q: Option<String>,
    /// Only lines serving this stop.
    pub stop_id: Option<Uuid>,
    /// Activity filter, for line administrators only (`403` otherwise).
    pub is_active: Option<bool>,
    pub cursor: Option<String>,
    #[validate(range(min = 1, max = 100))]
    pub limit: Option<u32>,
}

/// A new line.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateLineRequest {
    /// 1–20 characters `[A-Za-z0-9-]`, stored upper-case, unique, immutable.
    #[schema(example = "L1")]
    pub code: String,
    /// 1–100 characters.
    pub name: String,
    /// At most 2000 characters.
    pub description: Option<String>,
    /// `#RRGGBB` (default `#000000`).
    pub color: Option<String>,
    /// 1–1440 minutes.
    pub frequency_minutes: Option<i64>,
    /// Dinars, `>= 0`.
    pub fare_dza: Option<i64>,
    /// Default `true`.
    pub is_active: Option<bool>,
}

/// Changes to a line (`code` is immutable). `null` clears `frequency_minutes` and `fare_dza`;
/// `is_active` replaces the legacy activate/deactivate actions.
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateLineRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub color: Option<String>,
    #[serde(default, deserialize_with = "double_option")]
    #[schema(value_type = Option<i64>)]
    pub frequency_minutes: Option<Option<i64>>,
    #[serde(default, deserialize_with = "double_option")]
    #[schema(value_type = Option<i64>)]
    pub fare_dza: Option<Option<i64>>,
    pub is_active: Option<bool>,
}

/// A stop at its position on a line.
#[derive(Debug, Serialize, ToSchema)]
pub struct LineStopDto {
    /// 0-based position along the line.
    pub position: u16,
    pub stop: StopSummaryDto,
    /// Geodesic distance from the previous stop in metres; `null` for the first stop.
    pub distance_from_previous_m: Option<f64>,
    /// Scheduled travel time from the previous stop in seconds, when known.
    pub time_from_previous_s: Option<u32>,
}

impl From<LineStop> for LineStopDto {
    fn from(s: LineStop) -> Self {
        Self {
            position: s.position,
            stop: s.stop.into(),
            distance_from_previous_m: s.distance_from_previous_m.map(round_m),
            time_from_previous_s: s.time_from_previous_s,
        }
    }
}

/// One stop of a line's ordered list.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct LineStopEntryRequest {
    pub stop_id: Uuid,
    /// Travel time from the previous stop (0–86400 s); not allowed on the first stop.
    pub time_from_previous_s: Option<i64>,
}

/// The whole ordered stop list of a line (0–200 distinct, existing stops).
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceLineStopsRequest {
    pub stops: Vec<LineStopEntryRequest>,
}

/// Inserts one stop into a line.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AddLineStopRequest {
    pub stop_id: Uuid,
    /// 0-based position; later stops shift by one. Default: after the last stop.
    pub position: Option<i64>,
    /// Travel time from the previous stop (0–86400 s); not allowed at position 0.
    pub time_from_previous_s: Option<i64>,
}

/// GeoJSON geometry type of a line route.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub enum GeoJsonLineStringType {
    LineString,
}

/// A GeoJSON `LineString`: 2–10 000 positions `[lng, lat]` (no altitude), no two
/// consecutive positions equal.
#[derive(Debug, Deserialize, Serialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RouteDto {
    #[serde(rename = "type")]
    pub geometry_type: GeoJsonLineStringType,
    #[schema(example = json!([[3.0603, 36.7856], [3.0588, 36.7731]]))]
    pub coordinates: Vec<Vec<f64>>,
}

impl RouteDto {
    /// The positions as `[lng, lat]` pairs; a position of another length is reported on
    /// `coordinates[i]` (a bounded number of times).
    pub fn positions(&self) -> Result<Vec<[f64; 2]>, Violations> {
        let mut v = Violations::new();
        let mut positions = Vec::with_capacity(self.coordinates.len());
        for (i, position) in self.coordinates.iter().enumerate() {
            match *position.as_slice() {
                [lng, lat] => positions.push([lng, lat]),
                _ if v.len() < 20 => {
                    v.push(format!("coordinates[{i}]"), Violation::InvalidFormat);
                }
                _ => {}
            }
        }
        if v.is_empty() { Ok(positions) } else { Err(v) }
    }
}

impl From<LineGeometry> for RouteDto {
    fn from(g: LineGeometry) -> Self {
        Self {
            geometry_type: GeoJsonLineStringType::LineString,
            coordinates: g.points().iter().map(|p| vec![p.lng(), p.lat()]).collect(),
        }
    }
}

// --- Schedules -----------------------------------------------------------------------------------

/// A weekly service window of a line.
#[derive(Debug, Serialize, ToSchema)]
pub struct ScheduleDto {
    pub id: Uuid,
    pub line_id: Uuid,
    /// ISO 8601: 1 = Monday … 7 = Sunday.
    #[schema(example = 1)]
    pub day_of_week: u8,
    /// `HH:MM`.
    #[schema(example = "06:00")]
    pub start_time: String,
    /// `HH:MM`, after `start_time`.
    #[schema(example = "21:30")]
    pub end_time: String,
    /// Minutes between departures (1–1440).
    pub frequency_minutes: u16,
    /// Only active schedules are public; they may not overlap on the same day.
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl From<Schedule> for ScheduleDto {
    fn from(s: Schedule) -> Self {
        Self {
            id: s.id.as_uuid(),
            line_id: s.line_id.as_uuid(),
            day_of_week: s.day.iso(),
            start_time: s.window.start().to_string(),
            end_time: s.window.end().to_string(),
            frequency_minutes: s.frequency.minutes(),
            is_active: s.is_active,
            created_at: s.created_at,
            updated_at: s.updated_at,
        }
    }
}

/// A new schedule.
#[derive(Debug, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateScheduleRequest {
    /// ISO 8601: 1 = Monday … 7 = Sunday.
    #[schema(example = 1)]
    pub day_of_week: i64,
    /// `HH:MM` (24-hour clock).
    #[schema(example = "06:00")]
    pub start_time: String,
    /// `HH:MM`, after `start_time`.
    #[schema(example = "21:30")]
    pub end_time: String,
    /// 1–1440 minutes.
    #[schema(example = 15)]
    pub frequency_minutes: i64,
    /// Default `true`.
    pub is_active: Option<bool>,
}

/// Changes to a schedule (same rules as creation).
#[derive(Debug, Default, Deserialize, Validate, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateScheduleRequest {
    pub day_of_week: Option<i64>,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub frequency_minutes: Option<i64>,
    pub is_active: Option<bool>,
}
