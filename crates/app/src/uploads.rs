//! Uploads to private object storage.
//!
//! 1. A client asks for an upload ([`UploadService::request`]): the server records a pending
//!    upload under a key it generates and returns a presigned `PUT` whose content type and
//!    length are signed.
//! 2. The client uploads the object directly to storage.
//! 3. An "attach" use-case (avatar, driver documents, bus or stop photo) calls
//!    [`UploadService::claim`], then hands the [`ClaimedUpload`] to its repository, which stores
//!    the key and marks the upload attached in one transaction.
//!
//! Objects that are replaced or removed are deleted by a [`Job::StorageDeleteObject`] enqueued
//! in the transaction that drops the reference ([`UploadService::with_deletion`]). The job is
//! deferred until the presigned `PUT` of the object has expired: before that, the client could
//! upload the object again after its deletion, and nothing would ever reference or delete it.
//! Pending uploads that are never attached are purged by the hourly
//! [`Job::PurgeExpiredUploads`].
//!
//! Storage is optional: without it, requesting and claiming answer
//! `AppError::Unavailable("storage")` and download URLs are `None`.

use std::sync::Arc;
use std::time::Duration;

use dz_domain::authz::{Action, Actor, Policy};
use dz_domain::ids::{UploadId, UserId};
use dz_domain::upload::{UploadPurpose, UploadStatus, object_key};
use dz_domain::{DenyReason, Violation, Violations};

use crate::error::{AppError, AppResult};
use crate::jobs::{Job, chrono_duration};
use crate::ports::{
    ClaimedUpload, Clock, JobOptions, NewUpload, ObjectStorage, PresignedUpload, Upload,
    UploadRepository, WriteEffects,
};

/// Margin added to the expiry of presigned upload URLs before an object is deleted: storage
/// checks the expiry against its own clock, which may lag behind ours.
pub const PRESIGNED_CLOCK_SKEW: Duration = Duration::from_secs(300);

/// A pending upload with the presigned request that uploads its object.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestedUpload {
    pub upload: Upload,
    pub presigned: PresignedUpload,
}

pub struct UploadService {
    uploads: Arc<dyn UploadRepository>,
    storage: Option<Arc<dyn ObjectStorage>>,
    clock: Arc<dyn Clock>,
    /// Validity of presigned upload URLs (and of the pending upload).
    upload_ttl: Duration,
}

impl UploadService {
    #[must_use]
    pub fn new(
        uploads: Arc<dyn UploadRepository>,
        storage: Option<Arc<dyn ObjectStorage>>,
        clock: Arc<dyn Clock>,
        upload_ttl: Duration,
    ) -> Self {
        Self { uploads, storage, clock, upload_ttl }
    }

    /// Whether object storage is configured.
    #[must_use]
    pub fn enabled(&self) -> bool {
        self.storage.is_some()
    }

    /// Fails with `Unavailable("storage")` when object storage is not configured. Attach and
    /// detach use-cases call it before changing anything.
    pub fn require_storage(&self) -> AppResult<&dyn ObjectStorage> {
        self.storage.as_deref().ok_or(AppError::Unavailable("storage"))
    }

    /// Records a pending upload of `size_bytes` bytes of `content_type` for `purpose`, owned by
    /// the caller, and presigns its `PUT`.
    pub async fn request(
        &self,
        actor: &Actor,
        purpose: UploadPurpose,
        content_type: &str,
        size_bytes: u64,
    ) -> AppResult<RequestedUpload> {
        Policy::authorize(actor, &Action::RequestUpload { purpose })?;
        let owner = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        let storage = self.require_storage()?;
        let mut v = Violations::new();
        let content_type = v.check("content_type", purpose.check_content_type(content_type));
        let size = v.check("size_bytes", purpose.check_size(size_bytes));
        let (Some(content_type), Some(size)) = (content_type, size) else {
            return Err(v.into());
        };

        let id = UploadId::generate();
        let key = object_key(purpose, owner, id);
        let now = self.clock.now();
        let presigned = storage.presign_put(&key, content_type, u64::from(size), self.upload_ttl);
        let upload = self
            .uploads
            .insert(NewUpload {
                id,
                owner_id: owner,
                purpose,
                object_key: key,
                content_type: content_type.to_owned(),
                size_bytes: size,
                created_at: now,
                expires_at: presigned.expires_at,
            })
            .await?;
        tracing::info!(upload_id = %id, purpose = %purpose, size, "upload requested");
        Ok(RequestedUpload { upload, presigned })
    }

    /// One of the caller's uploads (to follow its status). Someone else's upload is
    /// indistinguishable from a missing one.
    pub async fn get(&self, actor: &Actor, id: UploadId) -> AppResult<Upload> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        let owner = actor.user_id().ok_or(AppError::Forbidden(DenyReason::MissingPermission))?;
        self.uploads
            .find(id)
            .await?
            .filter(|u| u.owner_id == owner)
            .ok_or(AppError::NotFound("upload"))
    }

    /// Verifies that `upload_id` can be attached by `owner` as `purpose`: the upload exists, is
    /// owned by `owner`, has that purpose, is pending (not attached yet) and unexpired, and its
    /// object exists with the declared size and type. Problems are reported on `field` as
    /// `invalid_upload`. An object that differs from the declaration is deleted right away: the
    /// upload stays pending, so an object uploaded again with the same URL is purged with it.
    ///
    /// The caller's repository must mark the returned upload attached in the transaction that
    /// stores its key (see [`ClaimedUpload`]); it answers `Conflict(UploadAlreadyUsed)` when a
    /// concurrent request attached the upload in between.
    pub async fn claim(
        &self,
        owner: UserId,
        upload_id: UploadId,
        purpose: UploadPurpose,
        field: &'static str,
    ) -> AppResult<ClaimedUpload> {
        let storage = self.require_storage()?;
        let invalid = || AppError::invalid(field, Violation::InvalidUpload);
        // Someone else's upload is indistinguishable from a missing one.
        let upload = self
            .uploads
            .find(upload_id)
            .await?
            .filter(|u| u.owner_id == owner && u.purpose == purpose)
            .ok_or_else(invalid)?;
        if upload.status != UploadStatus::Pending || upload.expires_at <= self.clock.now() {
            return Err(invalid());
        }
        let Some(object) = storage.head(&upload.object_key).await? else {
            return Err(invalid());
        };
        let type_matches = object
            .content_type
            .as_deref()
            .is_some_and(|t| t.trim().eq_ignore_ascii_case(&upload.content_type));
        if object.size_bytes != u64::from(upload.size_bytes) || !type_matches {
            tracing::warn!(
                upload_id = %upload.id,
                declared = upload.size_bytes,
                stored = object.size_bytes,
                "uploaded object differs from its declaration; deleting it"
            );
            if let Err(error) = storage.delete(&upload.object_key).await {
                tracing::warn!(%error, key = %upload.object_key, "could not delete object");
            }
            return Err(invalid());
        }
        Ok(ClaimedUpload { id: upload.id, object_key: upload.object_key })
    }

    /// A presigned download URL for a stored key; `None` without a key or without storage.
    #[must_use]
    pub fn download_url(&self, key: Option<&str>) -> Option<String> {
        Some(self.storage.as_ref()?.presign_get(key?))
    }

    /// Adds to `effects` the deletion of `key`, an object the write stops referencing (a
    /// replaced or removed avatar, document or photo).
    ///
    /// The [`Job::StorageDeleteObject`] runs once no presigned `PUT` of the key can be valid any
    /// more (the expiry of its upload plus [`PRESIGNED_CLOCK_SKEW`]): presigned URLs cannot be
    /// revoked, and an object uploaded again after its deletion would be referenced by nothing.
    /// A key without upload (or whose upload is gone) is treated as if it was presigned now.
    pub async fn with_deletion(&self, effects: WriteEffects, key: &str) -> AppResult<WriteEffects> {
        let now = self.clock.now();
        let url_expiry = match self.uploads.find_by_key(key).await? {
            Some(upload) => upload.expires_at.max(now),
            None => now + chrono_duration(self.upload_ttl),
        };
        let options = JobOptions {
            run_at: Some(url_expiry + chrono_duration(PRESIGNED_CLOCK_SKEW)),
            ..JobOptions::default()
        };
        Ok(effects.with_job_options(Job::StorageDeleteObject { key: key.to_owned() }, options))
    }
}

#[cfg(test)]
mod tests;
