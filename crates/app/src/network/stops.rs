//! Stop use-cases: catalogue reads, nearby search, administration and photos.

use std::sync::Arc;

use dz_domain::authz::{Action, Actor, CatalogResource, Policy};
use dz_domain::geo::GeoPoint;
use dz_domain::ids::{LineId, StopId, UploadId};
use dz_domain::network::{
    ADDRESS_MAX_CHARS, AREA_MAX_CHARS, DESCRIPTION_MAX_CHARS, FeatureTags, Line, Stop, StopName,
    optional_text,
};
use dz_domain::upload::UploadPurpose;
use dz_domain::{DenyReason, Violation, Violations};
use serde_json::{Map, Value, json};

use super::ports::{NewStop, StopFilter, StopPatch, StopRepository};
use super::{activity_filter, search_term, sees_inactive};
use crate::audit;
use crate::error::{AppError, AppResult};
use crate::pagination::{Page, PageRequest};
use crate::ports::{Clock, RequestMeta, WriteEffects};
use crate::uploads::UploadService;

/// Smallest, default and largest radius of a nearby search, in metres.
pub const NEARBY_RADIUS_M: (u32, u32, u32) = (10, 500, 5000);
/// Default and largest number of stops of a nearby search.
pub const NEARBY_LIMIT: (u32, u32) = (20, 50);

/// A stop with the presigned URL of its photo (`None` without photo or storage).
#[derive(Debug, Clone, PartialEq)]
pub struct StopView {
    pub stop: Stop,
    pub photo_url: Option<String>,
}

/// A stop found by a nearby search.
#[derive(Debug, Clone, PartialEq)]
pub struct NearbyStopView {
    pub view: StopView,
    pub distance_m: f64,
}

/// Raw filters of the stop list.
#[derive(Debug, Clone, Default)]
pub struct StopListQuery {
    pub q: Option<String>,
    pub wilaya: Option<String>,
    pub commune: Option<String>,
    pub line_id: Option<LineId>,
    /// Writers only.
    pub is_active: Option<bool>,
}

/// Raw parameters of a nearby search.
#[derive(Debug, Clone, Copy, Default)]
pub struct NearbyQuery {
    pub lat: f64,
    pub lng: f64,
    pub radius_m: Option<i64>,
    pub limit: Option<i64>,
}

/// Raw input of a new stop.
#[derive(Debug, Clone, Default)]
pub struct CreateStopInput {
    pub name: String,
    /// `(lat, lng)` in degrees.
    pub location: (f64, f64),
    pub address: Option<String>,
    pub wilaya: Option<String>,
    pub commune: Option<String>,
    pub description: Option<String>,
    pub features: Option<Vec<String>>,
    pub is_active: Option<bool>,
}

/// Raw changes to a stop; absent fields are unchanged.
#[derive(Debug, Clone, Default)]
pub struct UpdateStopInput {
    pub name: Option<String>,
    /// `(lat, lng)` in degrees.
    pub location: Option<(f64, f64)>,
    pub address: Option<String>,
    pub wilaya: Option<String>,
    pub commune: Option<String>,
    pub description: Option<String>,
    pub features: Option<Vec<String>>,
    pub is_active: Option<bool>,
}

pub struct StopService {
    stops: Arc<dyn StopRepository>,
    uploads: Arc<UploadService>,
    clock: Arc<dyn Clock>,
}

impl StopService {
    #[must_use]
    pub fn new(
        stops: Arc<dyn StopRepository>,
        uploads: Arc<UploadService>,
        clock: Arc<dyn Clock>,
    ) -> Self {
        Self { stops, uploads, clock }
    }

    fn view(&self, stop: Stop) -> StopView {
        let photo_url = self.uploads.download_url(stop.photo_key.as_deref());
        StopView { stop, photo_url }
    }

    /// A stop the actor may see: inactive stops are hidden from non-writers.
    async fn visible(&self, actor: &Actor, id: StopId) -> AppResult<Stop> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        self.stops
            .find(id)
            .await?
            .filter(|s| s.is_active || sees_inactive(actor, CatalogResource::Stop))
            .ok_or(AppError::NotFound("stop"))
    }

    /// Any stop, for writers (authorization already checked).
    async fn existing(&self, id: StopId) -> AppResult<Stop> {
        self.stops.find(id).await?.ok_or(AppError::NotFound("stop"))
    }

    fn authorize_write(actor: &Actor) -> AppResult<()> {
        Policy::authorize(actor, &Action::WriteCatalog { resource: CatalogResource::Stop })?;
        Ok(())
    }

    /// Stops, newest first, filtered.
    pub async fn list(
        &self,
        actor: &Actor,
        query: StopListQuery,
        page: PageRequest,
    ) -> AppResult<Page<StopView>> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        let is_active = activity_filter(actor, CatalogResource::Stop, query.is_active)?;
        let mut v = Violations::new();
        let q = search_term(query.q.as_deref(), &mut v);
        let wilaya = area_filter("wilaya", query.wilaya.as_deref(), &mut v);
        let commune = area_filter("commune", query.commune.as_deref(), &mut v);
        v.into_result()?;
        // An inactive line hides its stop list from non-writers here too (§1.2).
        let filter = StopFilter {
            q,
            wilaya,
            commune,
            line_id: query.line_id,
            include_inactive_lines: sees_inactive(actor, CatalogResource::Line),
            is_active,
        };
        Ok(self.stops.list(&filter, page).await?.map(|s| self.view(s)))
    }

    /// Active stops around a point, nearest first.
    pub async fn nearby(
        &self,
        actor: &Actor,
        query: NearbyQuery,
    ) -> AppResult<Vec<NearbyStopView>> {
        Policy::authorize(actor, &Action::ReadCatalog)?;
        let mut v = Violations::new();
        let center = v.check_nested("", GeoPoint::parse(query.lat, query.lng));
        let (min_radius, default_radius, max_radius) = NEARBY_RADIUS_M;
        let radius = bounded(query.radius_m, min_radius, default_radius, max_radius);
        let radius = v.check("radius_m", radius);
        let (default_limit, max_limit) = NEARBY_LIMIT;
        let limit = v.check("limit", bounded(query.limit, 1, default_limit, max_limit));
        let (Some(center), Some(radius), Some(limit)) = (center, radius, limit) else {
            return Err(v.into());
        };
        let found = self.stops.nearby(center, radius, limit).await?;
        Ok(found
            .into_iter()
            .map(|n| NearbyStopView { view: self.view(n.stop), distance_m: n.distance_m })
            .collect())
    }

    pub async fn get(&self, actor: &Actor, id: StopId) -> AppResult<StopView> {
        Ok(self.view(self.visible(actor, id).await?))
    }

    /// Lines serving a visible stop, ordered by code (inactive lines for line writers only).
    pub async fn lines(&self, actor: &Actor, id: StopId) -> AppResult<Vec<Line>> {
        self.visible(actor, id).await?;
        self.stops.lines(id, sees_inactive(actor, CatalogResource::Line)).await
    }

    pub async fn create(
        &self,
        actor: &Actor,
        input: CreateStopInput,
        meta: &RequestMeta,
    ) -> AppResult<StopView> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let name = v.check("name", StopName::parse(&input.name));
        let (lat, lng) = input.location;
        let location = v.check_nested("location", GeoPoint::parse(lat, lng));
        let mut text = |field, raw: Option<String>, max| {
            raw.and_then(|raw| v.check(field, optional_text(&raw, max))).unwrap_or_default()
        };
        let address = text("address", input.address, ADDRESS_MAX_CHARS);
        let wilaya = text("wilaya", input.wilaya, AREA_MAX_CHARS);
        let commune = text("commune", input.commune, AREA_MAX_CHARS);
        let description = text("description", input.description, DESCRIPTION_MAX_CHARS);
        let features = match input.features {
            Some(raw) => v.check_nested("features", FeatureTags::parse(&raw)),
            None => Some(FeatureTags::default()),
        };
        let (Some(name), Some(location), Some(features)) = (name, location, features) else {
            return Err(v.into());
        };
        v.into_result()?;

        let id = StopId::generate();
        let now = self.clock.now();
        let details = json!({
            "name": name.as_str(),
            "location": { "lat": location.lat(), "lng": location.lng() },
        });
        let audit = audit::entry(actor, meta, now, "stop.create", "stop", id.to_string(), details);
        let new = NewStop {
            id,
            name,
            location,
            address,
            wilaya,
            commune,
            description,
            features,
            is_active: input.is_active.unwrap_or(true),
            created_at: now,
        };
        let stop = self.stops.insert(new, WriteEffects::audited(audit)).await?;
        tracing::info!(stop_id = %stop.id, "stop created");
        Ok(self.view(stop))
    }

    /// Applies a partial update; an empty update returns the stop unchanged (not audited).
    pub async fn update(
        &self,
        actor: &Actor,
        id: StopId,
        input: UpdateStopInput,
        meta: &RequestMeta,
    ) -> AppResult<StopView> {
        Self::authorize_write(actor)?;
        let mut v = Violations::new();
        let mut changes = Map::new();
        let name = input.name.as_deref().and_then(|raw| v.check("name", StopName::parse(raw)));
        let location = input
            .location
            .and_then(|(lat, lng)| v.check_nested("location", GeoPoint::parse(lat, lng)));
        let mut text = |field, raw: Option<String>, max| {
            raw.and_then(|raw| v.check(field, optional_text(&raw, max)))
        };
        let address = text("address", input.address, ADDRESS_MAX_CHARS);
        let wilaya = text("wilaya", input.wilaya, AREA_MAX_CHARS);
        let commune = text("commune", input.commune, AREA_MAX_CHARS);
        let description = text("description", input.description, DESCRIPTION_MAX_CHARS);
        let features =
            input.features.and_then(|raw| v.check_nested("features", FeatureTags::parse(&raw)));
        v.into_result()?;

        if let Some(name) = &name {
            changes.insert("name".into(), json!(name.as_str()));
        }
        if let Some(location) = location {
            let point = json!({ "lat": location.lat(), "lng": location.lng() });
            changes.insert("location".into(), point);
        }
        for (field, value) in [
            ("address", &address),
            ("wilaya", &wilaya),
            ("commune", &commune),
            ("description", &description),
        ] {
            if let Some(value) = value {
                changes.insert(field.into(), json!(value));
            }
        }
        if let Some(features) = &features {
            changes.insert("features".into(), json!(features.as_slice()));
        }
        if let Some(is_active) = input.is_active {
            changes.insert("is_active".into(), json!(is_active));
        }
        let patch = StopPatch {
            name,
            location,
            address,
            wilaya,
            commune,
            description,
            features,
            is_active: input.is_active,
        };
        if patch.is_empty() {
            return Ok(self.view(self.existing(id).await?));
        }
        let now = self.clock.now();
        let details = Value::Object(changes);
        let audit = audit::entry(actor, meta, now, "stop.update", "stop", id.to_string(), details);
        let stop = self.stops.update(id, patch, now, WriteEffects::audited(audit)).await?;
        Ok(self.view(stop))
    }

    /// Deletes a stop no line serves; its photo is deleted by a deferred job.
    pub async fn delete(&self, actor: &Actor, id: StopId, meta: &RequestMeta) -> AppResult<()> {
        Self::authorize_write(actor)?;
        let stop = self.existing(id).await?;
        let now = self.clock.now();
        let details = json!({ "name": stop.name.as_str() });
        let audit = audit::entry(actor, meta, now, "stop.delete", "stop", id.to_string(), details);
        let mut effects = WriteEffects::audited(audit);
        if let Some(key) = stop.photo_key.as_deref() {
            effects = self.uploads.with_deletion(effects, key).await?;
        }
        self.stops.delete(id, stop.photo_key.as_deref(), effects).await?;
        tracing::info!(stop_id = %id, "stop deleted");
        Ok(())
    }

    /// Sets the photo of a stop to a claimed `stop_photo` upload of the actor. The previous
    /// photo is deleted by a deferred job enqueued with the change.
    pub async fn set_photo(
        &self,
        actor: &Actor,
        id: StopId,
        upload_id: UploadId,
        meta: &RequestMeta,
    ) -> AppResult<StopView> {
        Policy::authorize(actor, &Action::AttachStopPhoto)?;
        let owner = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        self.uploads.require_storage()?;
        let stop = self.existing(id).await?;
        let claimed =
            self.uploads.claim(owner, upload_id, UploadPurpose::StopPhoto, "upload_id").await?;
        let now = self.clock.now();
        let details = json!({ "upload_id": upload_id });
        let audit =
            audit::entry(actor, meta, now, "stop.photo.set", "stop", id.to_string(), details);
        let mut effects = WriteEffects::audited(audit);
        if let Some(key) = stop.photo_key.as_deref() {
            effects = self.uploads.with_deletion(effects, key).await?;
        }
        let stop = self
            .stops
            .set_photo(id, Some(&claimed), stop.photo_key.as_deref(), now, effects)
            .await?;
        Ok(self.view(stop))
    }

    /// Removes the photo of a stop (idempotent); the object is deleted by a deferred job.
    pub async fn remove_photo(
        &self,
        actor: &Actor,
        id: StopId,
        meta: &RequestMeta,
    ) -> AppResult<()> {
        Self::authorize_write(actor)?;
        self.uploads.require_storage()?;
        let stop = self.existing(id).await?;
        let Some(previous) = stop.photo_key else {
            return Ok(());
        };
        let now = self.clock.now();
        let audit =
            audit::entry(actor, meta, now, "stop.photo.remove", "stop", id.to_string(), json!({}));
        let effects = self.uploads.with_deletion(WriteEffects::audited(audit), &previous).await?;
        self.stops.set_photo(id, None, Some(&previous), now, effects).await?;
        Ok(())
    }
}

/// A wilaya or commune filter: trimmed, 1–100 characters.
fn area_filter(field: &'static str, raw: Option<&str>, v: &mut Violations) -> Option<String> {
    let value = raw?.trim();
    if value.is_empty() {
        v.push(field, Violation::Required);
        return None;
    }
    v.check(field, optional_text(value, AREA_MAX_CHARS))
}

/// An optional bounded integer parameter.
fn bounded(raw: Option<i64>, min: u32, default: u32, max: u32) -> Result<u32, Violation> {
    let Some(raw) = raw else {
        return Ok(default);
    };
    match u32::try_from(raw) {
        Ok(value) if (min..=max).contains(&value) => Ok(value),
        _ => Err(Violation::OutOfRange { min: i64::from(min), max: i64::from(max) }),
    }
}
