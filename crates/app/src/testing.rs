//! In-memory implementations of every port, for unit tests (enable feature `test-support` to
//! use them from other crates). They follow the same contracts as the Postgres/Valkey
//! adapters, including atomicity of combined operations.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::collections::HashMap;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Duration;

use async_trait::async_trait;
use chrono::{DateTime, DurationRound, Utc};
use dz_domain::ids::{ApiKeyId, SessionId, UploadId, UserId};
use dz_domain::upload::UploadStatus;
use dz_domain::user::{Bio, Email, Profile, User};
use dz_domain::{ConflictKind, Lang};
use secrecy::{ExposeSecret, SecretString};
use uuid::Uuid;

use crate::error::{AppError, AppResult, AuthFailure};
use crate::jobs::{Job, chrono_duration};
use crate::pagination::{Cursor, Page, PageRequest};
use crate::ports::{
    AccessClaims, AccessTokenCodec, AdminUserPatch, AdminUserUpdate, ApiKeyCredentials,
    ApiKeyRecord, ApiKeyRepository, AuditActor, AuditEntry, AuditFilter, AuditRepository,
    ClaimedUpload, Clock, Credentials, EmailMessage, EnqueueOutcome, JobOptions, JobQueue,
    LockoutPolicy, Mailer, NewApiKey, NewAuditEntry, NewRefreshToken, NewSession, NewUpload,
    NewUser, ObjectInfo, ObjectStorage, OutboxJob, PasswordCheck, PasswordHasher,
    PasswordResetRepository, PresignedUpload, ProfilePatch, Quota, RateDecision, RateLimiter,
    RevocationReason, RevocationStore, RotateOutcome, SessionInfo, SessionRepository, TokenHash,
    Upload, UploadRepository, UserFilter, UserPatch, UserRepository, WriteEffects,
};
use crate::uploads::UploadService;

mod drivers;
mod network;

/// A clock that only moves when told to.
#[derive(Debug)]
pub struct ManualClock(Mutex<DateTime<Utc>>);

impl ManualClock {
    #[must_use]
    pub fn new(start: DateTime<Utc>) -> Self {
        Self(Mutex::new(start))
    }

    pub fn advance(&self, by: Duration) {
        let mut now = self.0.lock().unwrap();
        *now += chrono_duration(by);
    }
}

impl Clock for ManualClock {
    fn now(&self) -> DateTime<Utc> {
        *self.0.lock().unwrap()
    }
}

#[derive(Debug, Clone)]
struct UserRow {
    user: User,
    profile: Profile,
    password_hash: Option<String>,
    failed: u32,
    locked_until: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone)]
struct SessionRow {
    info: SessionInfo,
    revoked: Option<RevocationReason>,
}

#[derive(Debug, Clone)]
struct RefreshRow {
    session_id: SessionId,
    expires_at: DateTime<Utc>,
    used: bool,
}

#[derive(Debug, Clone)]
struct ResetRow {
    user_id: UserId,
    expires_at: DateTime<Utc>,
    used: bool,
}

#[derive(Debug, Default)]
struct State {
    users: HashMap<UserId, UserRow>,
    sessions: HashMap<SessionId, SessionRow>,
    refresh: HashMap<TokenHash, RefreshRow>,
    resets: HashMap<TokenHash, ResetRow>,
    keys: HashMap<ApiKeyId, ApiKeyCredentials>,
    audit: Vec<AuditEntry>,
    uploads: HashMap<UploadId, Upload>,
    /// Jobs persisted by writes (transactional outbox), in order.
    outbox: Vec<OutboxJob>,
    network: network::NetworkState,
    drivers: drivers::DriversState,
}

impl State {
    /// What the Postgres adapter does in the write's transaction.
    fn persist(&mut self, effects: WriteEffects) {
        self.audit.extend(effects.audit.into_iter().map(to_entry));
        self.outbox.extend(effects.jobs);
    }
}

/// One in-memory "database" implementing all repository ports.
#[derive(Debug, Default)]
pub struct InMemoryStore {
    state: Mutex<State>,
}

impl InMemoryStore {
    fn state(&self) -> MutexGuard<'_, State> {
        self.state.lock().unwrap()
    }

    /// Number of audit entries written so far.
    #[must_use]
    pub fn audit_len(&self) -> usize {
        self.state().audit.len()
    }

    /// Stored password hash of a user.
    #[must_use]
    pub fn password_hash(&self, id: UserId) -> Option<String> {
        self.state().users.get(&id).and_then(|r| r.password_hash.clone())
    }

    /// Removes and returns the jobs persisted by writes so far, with their options.
    pub fn drain_outbox(&self) -> Vec<OutboxJob> {
        std::mem::take(&mut self.state().outbox)
    }

    /// An upload as stored.
    #[must_use]
    pub fn upload(&self, id: UploadId) -> Option<Upload> {
        self.state().uploads.get(&id).cloned()
    }

    /// Overrides the stored hash (e.g. to simulate an imported Django hash).
    pub fn set_password_hash(&self, id: UserId, hash: &str) {
        self.state().users.get_mut(&id).unwrap().password_hash = Some(hash.to_owned());
    }

    fn revoke_all_locked(
        state: &mut State,
        user_id: UserId,
        reason: RevocationReason,
        keep: Option<SessionId>,
    ) -> Vec<SessionId> {
        let mut revoked = Vec::new();
        for row in state.sessions.values_mut() {
            if row.info.user_id == user_id && row.revoked.is_none() && Some(row.info.id) != keep {
                row.revoked = Some(reason);
                revoked.push(row.info.id);
            }
        }
        revoked
    }
}

fn credentials(row: &UserRow) -> Credentials {
    Credentials {
        user: row.user.clone(),
        password_hash: row.password_hash.clone(),
        failed_login_attempts: row.failed,
        locked_until: row.locked_until,
        language: row.profile.language,
    }
}

#[async_trait]
impl UserRepository for InMemoryStore {
    async fn insert(&self, new: NewUser) -> AppResult<(User, Profile)> {
        let mut state = self.state();
        if state.users.values().any(|r| r.user.email == new.email) {
            return Err(AppError::Conflict(ConflictKind::EmailTaken));
        }
        let user = User {
            id: new.id,
            email: new.email,
            role: new.role,
            first_name: new.first_name,
            last_name: new.last_name,
            phone_number: new.phone_number,
            is_active: true,
            email_verified_at: None,
            last_login_at: None,
            created_at: new.created_at,
            updated_at: new.created_at,
        };
        let profile = Profile {
            user_id: new.id,
            avatar_key: None,
            bio: Bio::default(),
            language: new.language,
            push_notifications_enabled: true,
            email_notifications_enabled: true,
            sms_notifications_enabled: false,
            created_at: new.created_at,
            updated_at: new.created_at,
        };
        state.users.insert(
            new.id,
            UserRow {
                user: user.clone(),
                profile: profile.clone(),
                password_hash: Some(new.password_hash),
                failed: 0,
                locked_until: None,
            },
        );
        Ok((user, profile))
    }

    async fn find(&self, id: UserId) -> AppResult<Option<User>> {
        Ok(self.state().users.get(&id).map(|r| r.user.clone()))
    }

    async fn credentials_by_email(&self, email: &Email) -> AppResult<Option<Credentials>> {
        Ok(self.state().users.values().find(|r| &r.user.email == email).map(credentials))
    }

    async fn credentials_by_id(&self, id: UserId) -> AppResult<Option<Credentials>> {
        Ok(self.state().users.get(&id).map(credentials))
    }

    async fn record_login_success(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        upgraded_hash: Option<String>,
    ) -> AppResult<()> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("user"))?;
        row.failed = 0;
        row.locked_until = None;
        row.user.last_login_at = Some(at);
        if let Some(hash) = upgraded_hash {
            row.password_hash = Some(hash);
        }
        Ok(())
    }

    async fn record_login_failure(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        policy: LockoutPolicy,
    ) -> AppResult<()> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("user"))?;
        row.failed += 1;
        if let Some(lock) = policy.lock_for(row.failed) {
            row.locked_until = Some(at + chrono_duration(lock));
        }
        Ok(())
    }

    async fn change_password(
        &self,
        id: UserId,
        password_hash: String,
        at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("user"))?;
        row.password_hash = Some(password_hash);
        row.user.updated_at = at;
        Ok(Self::revoke_all_locked(&mut state, id, RevocationReason::PasswordChanged, keep))
    }

    async fn update(&self, id: UserId, patch: UserPatch, at: DateTime<Utc>) -> AppResult<User> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("user"))?;
        if let Some(v) = patch.first_name {
            row.user.first_name = v;
        }
        if let Some(v) = patch.last_name {
            row.user.last_name = v;
        }
        if let Some(v) = patch.phone_number {
            row.user.phone_number = v;
        }
        row.user.updated_at = at;
        Ok(row.user.clone())
    }

    async fn profile(&self, id: UserId) -> AppResult<Option<Profile>> {
        Ok(self.state().users.get(&id).map(|r| r.profile.clone()))
    }

    async fn update_profile(
        &self,
        id: UserId,
        patch: ProfilePatch,
        at: DateTime<Utc>,
    ) -> AppResult<Profile> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("profile"))?;
        let p = &mut row.profile;
        if let Some(v) = patch.bio {
            p.bio = v;
        }
        if let Some(v) = patch.language {
            p.language = v;
        }
        if let Some(v) = patch.push_notifications_enabled {
            p.push_notifications_enabled = v;
        }
        if let Some(v) = patch.email_notifications_enabled {
            p.email_notifications_enabled = v;
        }
        if let Some(v) = patch.sms_notifications_enabled {
            p.sms_notifications_enabled = v;
        }
        p.updated_at = at;
        Ok(p.clone())
    }

    async fn list(&self, filter: &UserFilter, page: PageRequest) -> AppResult<Page<User>> {
        let state = self.state();
        let mut users: Vec<User> = state
            .users
            .values()
            .map(|r| r.user.clone())
            .filter(|u| filter.role.is_none_or(|r| u.role == r))
            .filter(|u| filter.is_active.is_none_or(|a| u.is_active == a))
            .filter(|u| {
                filter.email_prefix.as_deref().is_none_or(|p| u.email.as_str().starts_with(p))
            })
            .filter(|u| {
                page.after.is_none_or(|c| (u.created_at, u.id.as_uuid()) < (c.created_at, c.id))
            })
            .collect();
        users.sort_by_key(|u| std::cmp::Reverse((u.created_at, u.id.as_uuid())));
        users.truncate(page.fetch_limit() as usize);
        Ok(Page::from_rows(users, page, |u| Cursor { created_at: u.created_at, id: u.id.as_uuid() }))
    }

    async fn admin_update(
        &self,
        id: UserId,
        patch: AdminUserPatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<AdminUserUpdate> {
        let mut state = self.state();
        let row = state.users.get_mut(&id).ok_or(AppError::NotFound("user"))?;
        let deactivated = patch.is_active == Some(false) && row.user.is_active;
        let role_changed = patch.role.is_some_and(|r| r != row.user.role);
        if let Some(active) = patch.is_active {
            row.user.is_active = active;
        }
        if let Some(role) = patch.role {
            row.user.role = role;
        }
        row.user.updated_at = at;
        let user = row.user.clone();
        let revoked_sessions = if deactivated || role_changed {
            Self::revoke_all_locked(&mut state, id, RevocationReason::AdminAction, None)
        } else {
            Vec::new()
        };
        state.persist(effects);
        Ok(AdminUserUpdate { user, revoked_sessions })
    }

    async fn set_avatar(
        &self,
        id: UserId,
        avatar: Option<&ClaimedUpload>,
        expected: Option<&str>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Profile> {
        let mut state = self.state();
        let row = state.users.get(&id).ok_or(AppError::NotFound("profile"))?;
        if row.profile.avatar_key.as_deref() != expected {
            return Err(AppError::Conflict(ConflictKind::StaleState));
        }
        if let Some(claimed) = avatar {
            mark_attached(&mut state, claimed, at)?;
        }
        let profile = &mut state.users.get_mut(&id).unwrap().profile;
        profile.avatar_key = avatar.map(|c| c.object_key.clone());
        profile.updated_at = at;
        let profile = profile.clone();
        state.persist(effects);
        Ok(profile)
    }
}

/// What `pg::uploads::mark_attached` does: pending → attached, or a conflict.
fn mark_attached(state: &mut State, claimed: &ClaimedUpload, at: DateTime<Utc>) -> AppResult<()> {
    match state.uploads.get_mut(&claimed.id) {
        Some(upload) if upload.status == UploadStatus::Pending => {
            upload.status = UploadStatus::Attached;
            upload.attached_at = Some(at);
            Ok(())
        }
        _ => Err(AppError::Conflict(ConflictKind::UploadAlreadyUsed)),
    }
}

fn to_entry(new: NewAuditEntry) -> AuditEntry {
    AuditEntry {
        id: new.id,
        occurred_at: new.occurred_at,
        actor: new.actor,
        action: new.action.to_owned(),
        resource_type: new.resource_type.to_owned(),
        resource_id: new.resource_id,
        details: new.details,
        ip: new.ip,
        request_id: new.request_id,
    }
}

#[async_trait]
impl SessionRepository for InMemoryStore {
    async fn create(&self, session: NewSession, token: NewRefreshToken) -> AppResult<()> {
        let mut state = self.state();
        state.sessions.insert(
            session.id,
            SessionRow {
                info: SessionInfo {
                    id: session.id,
                    user_id: session.user_id,
                    created_at: session.created_at,
                    last_used_at: session.created_at,
                    expires_at: session.expires_at,
                    user_agent: session.user_agent,
                    ip: session.ip,
                },
                revoked: None,
            },
        );
        state.refresh.insert(
            token.hash,
            RefreshRow { session_id: token.session_id, expires_at: token.expires_at, used: false },
        );
        Ok(())
    }

    async fn rotate(
        &self,
        presented: TokenHash,
        next: TokenHash,
        now: DateTime<Utc>,
        refresh_ttl: Duration,
    ) -> AppResult<RotateOutcome> {
        let mut state = self.state();
        let Some(token) = state.refresh.get(&presented).cloned() else {
            return Ok(RotateOutcome::Invalid);
        };
        let Some(session) = state.sessions.get(&token.session_id).cloned() else {
            return Ok(RotateOutcome::Invalid);
        };
        if token.used {
            if session.revoked.is_none() {
                state.sessions.get_mut(&token.session_id).unwrap().revoked =
                    Some(RevocationReason::RefreshTokenReuse);
            }
            return Ok(RotateOutcome::Reused {
                user_id: session.info.user_id,
                session_id: session.info.id,
            });
        }
        if session.revoked.is_some() || token.expires_at <= now || session.info.expires_at <= now {
            return Ok(RotateOutcome::Invalid);
        }
        state.refresh.get_mut(&presented).unwrap().used = true;
        let refresh_expires_at = (now + chrono_duration(refresh_ttl)).min(session.info.expires_at);
        state.refresh.insert(
            next,
            RefreshRow { session_id: session.info.id, expires_at: refresh_expires_at, used: false },
        );
        state.sessions.get_mut(&session.info.id).unwrap().info.last_used_at = now;
        Ok(RotateOutcome::Rotated {
            user_id: session.info.user_id,
            session_id: session.info.id,
            refresh_expires_at,
        })
    }

    async fn revoke(
        &self,
        user_id: UserId,
        session_id: SessionId,
        reason: RevocationReason,
        _at: DateTime<Utc>,
    ) -> AppResult<bool> {
        let mut state = self.state();
        match state.sessions.get_mut(&session_id) {
            Some(row) if row.info.user_id == user_id && row.revoked.is_none() => {
                row.revoked = Some(reason);
                Ok(true)
            }
            _ => Ok(false),
        }
    }

    async fn revoke_all(
        &self,
        user_id: UserId,
        reason: RevocationReason,
        _at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>> {
        Ok(Self::revoke_all_locked(&mut self.state(), user_id, reason, keep))
    }

    async fn list_active(
        &self,
        user_id: UserId,
        now: DateTime<Utc>,
    ) -> AppResult<Vec<SessionInfo>> {
        Ok(self
            .state()
            .sessions
            .values()
            .filter(|r| r.info.user_id == user_id && r.revoked.is_none() && r.info.expires_at > now)
            .map(|r| r.info.clone())
            .collect())
    }

    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64> {
        let mut state = self.state();
        let n = state.sessions.len();
        state.sessions.retain(|_, r| r.info.expires_at >= before);
        state.refresh.retain(|_, r| r.expires_at >= before);
        Ok((n - state.sessions.len()) as u64)
    }
}

#[async_trait]
impl PasswordResetRepository for InMemoryStore {
    async fn issue(
        &self,
        user_id: UserId,
        hash: TokenHash,
        _created_at: DateTime<Utc>,
        expires_at: DateTime<Utc>,
    ) -> AppResult<()> {
        let mut state = self.state();
        for row in state.resets.values_mut().filter(|r| r.user_id == user_id) {
            row.used = true;
        }
        state.resets.insert(hash, ResetRow { user_id, expires_at, used: false });
        Ok(())
    }

    async fn find_valid(&self, hash: TokenHash, now: DateTime<Utc>) -> AppResult<Option<UserId>> {
        Ok(self
            .state()
            .resets
            .get(&hash)
            .filter(|r| !r.used && r.expires_at > now)
            .map(|r| r.user_id))
    }

    async fn consume(
        &self,
        hash: TokenHash,
        password_hash: String,
        now: DateTime<Utc>,
    ) -> AppResult<Option<(UserId, Vec<SessionId>)>> {
        let mut state = self.state();
        let Some(row) = state.resets.get_mut(&hash).filter(|r| !r.used && r.expires_at > now)
        else {
            return Ok(None);
        };
        row.used = true;
        let user_id = row.user_id;
        if let Some(user) = state.users.get_mut(&user_id) {
            user.password_hash = Some(password_hash);
            user.failed = 0;
            user.locked_until = None;
        }
        let revoked =
            Self::revoke_all_locked(&mut state, user_id, RevocationReason::PasswordReset, None);
        Ok(Some((user_id, revoked)))
    }

    async fn purge_expired(&self, before: DateTime<Utc>) -> AppResult<u64> {
        let mut state = self.state();
        let n = state.resets.len();
        state.resets.retain(|_, r| r.expires_at >= before);
        Ok((n - state.resets.len()) as u64)
    }
}

#[async_trait]
impl ApiKeyRepository for InMemoryStore {
    async fn insert(&self, key: NewApiKey, effects: WriteEffects) -> AppResult<ApiKeyRecord> {
        let mut state = self.state();
        let record = ApiKeyRecord {
            id: key.id,
            name: key.name,
            prefix: key.prefix,
            scopes: key.scopes,
            created_by: Some(key.created_by),
            created_at: key.created_at,
            expires_at: key.expires_at,
            last_used_at: None,
            revoked_at: None,
        };
        state.keys.insert(
            key.id,
            ApiKeyCredentials { record: record.clone(), secret_hash: key.secret_hash },
        );
        state.persist(effects);
        Ok(record)
    }

    async fn find_by_prefix(&self, prefix: &str) -> AppResult<Option<ApiKeyCredentials>> {
        Ok(self.state().keys.values().find(|k| k.record.prefix == prefix).cloned())
    }

    async fn touch(&self, id: ApiKeyId, at: DateTime<Utc>) -> AppResult<()> {
        if let Some(key) = self.state().keys.get_mut(&id) {
            key.record.last_used_at = Some(at);
        }
        Ok(())
    }

    async fn list(&self, page: PageRequest) -> AppResult<Page<ApiKeyRecord>> {
        let mut keys: Vec<ApiKeyRecord> =
            self.state().keys.values().map(|k| k.record.clone()).collect();
        keys.sort_by_key(|k| std::cmp::Reverse((k.created_at, k.id.as_uuid())));
        keys.truncate(page.fetch_limit() as usize);
        Ok(Page::from_rows(keys, page, |k| Cursor { created_at: k.created_at, id: k.id.as_uuid() }))
    }

    async fn revoke(
        &self,
        id: ApiKeyId,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Option<ApiKeyRecord>> {
        let mut state = self.state();
        let Some(key) = state.keys.get_mut(&id) else {
            return Ok(None);
        };
        key.record.revoked_at.get_or_insert(at);
        let record = key.record.clone();
        state.persist(effects);
        Ok(Some(record))
    }
}

#[async_trait]
impl AuditRepository for InMemoryStore {
    async fn list(&self, filter: &AuditFilter, page: PageRequest) -> AppResult<Page<AuditEntry>> {
        let mut entries: Vec<AuditEntry> = self
            .state()
            .audit
            .iter()
            .filter(|e| filter.action.as_deref().is_none_or(|a| e.action == a))
            .filter(|e| filter.resource_type.as_deref().is_none_or(|t| e.resource_type == t))
            .filter(|e| {
                filter.actor_id.is_none_or(|id| match e.actor {
                    AuditActor::User(u) => u.as_uuid() == id,
                    AuditActor::Service(k) => k.as_uuid() == id,
                    AuditActor::System => false,
                })
            })
            .cloned()
            .collect();
        entries.sort_by_key(|e| std::cmp::Reverse((e.occurred_at, e.id.as_uuid())));
        entries.truncate(page.fetch_limit() as usize);
        Ok(Page::from_rows(entries, page, |e| Cursor { created_at: e.occurred_at, id: e.id.as_uuid() }))
    }
}

#[async_trait]
impl UploadRepository for InMemoryStore {
    async fn insert(&self, new: NewUpload) -> AppResult<Upload> {
        let mut state = self.state();
        if state.uploads.values().any(|u| u.object_key == new.object_key) {
            return Err(AppError::Conflict(ConflictKind::AlreadyExists));
        }
        let upload = Upload {
            id: new.id,
            owner_id: new.owner_id,
            purpose: new.purpose,
            object_key: new.object_key,
            content_type: new.content_type,
            size_bytes: new.size_bytes,
            status: UploadStatus::Pending,
            created_at: new.created_at,
            expires_at: new.expires_at,
            attached_at: None,
        };
        state.uploads.insert(upload.id, upload.clone());
        Ok(upload)
    }

    async fn find(&self, id: UploadId) -> AppResult<Option<Upload>> {
        Ok(self.state().uploads.get(&id).cloned())
    }

    async fn find_by_key(&self, object_key: &str) -> AppResult<Option<Upload>> {
        Ok(self.state().uploads.values().find(|u| u.object_key == object_key).cloned())
    }

    async fn list_expired(&self, before: DateTime<Utc>, limit: u32) -> AppResult<Vec<Upload>> {
        let mut expired: Vec<Upload> = self
            .state()
            .uploads
            .values()
            .filter(|u| u.status == UploadStatus::Pending && u.expires_at < before)
            .cloned()
            .collect();
        expired.sort_by_key(|u| u.expires_at);
        expired.truncate(limit as usize);
        Ok(expired)
    }

    async fn delete_pending(&self, ids: &[UploadId]) -> AppResult<u64> {
        let mut state = self.state();
        let before = state.uploads.len();
        state.uploads.retain(|id, u| !(ids.contains(id) && u.status == UploadStatus::Pending));
        Ok((before - state.uploads.len()) as u64)
    }
}

/// A transparent "hasher" for tests: `plain$<password>`; `legacy$<password>` verifies but asks
/// for a rehash (stands in for imported Django hashes).
#[derive(Debug, Default)]
pub struct FakeHasher;

#[async_trait]
impl PasswordHasher for FakeHasher {
    async fn hash(&self, password: &SecretString) -> AppResult<String> {
        Ok(format!("plain${}", password.expose_secret()))
    }

    async fn verify(&self, password: &SecretString, stored: &str) -> AppResult<PasswordCheck> {
        let pw = password.expose_secret();
        Ok(match stored.split_once('$') {
            Some(("plain", p)) if p == pw => PasswordCheck::Match { needs_rehash: false },
            Some(("legacy", p)) if p == pw => PasswordCheck::Match { needs_rehash: true },
            _ => PasswordCheck::Mismatch,
        })
    }

    async fn burn(&self, _password: &SecretString) {}
}

/// Access tokens as plain JSON (no signature) for tests.
#[derive(Debug, Default)]
pub struct FakeTokens;

impl AccessTokenCodec for FakeTokens {
    fn issue(&self, claims: &AccessClaims) -> AppResult<String> {
        Ok(serde_json::to_string(claims).unwrap())
    }

    fn verify(&self, token: &str, now: DateTime<Utc>) -> Result<AccessClaims, AuthFailure> {
        let claims: AccessClaims =
            serde_json::from_str(token).map_err(|_| AuthFailure::TokenInvalid)?;
        if claims.exp <= now.timestamp() {
            return Err(AuthFailure::TokenExpired);
        }
        Ok(claims)
    }
}

/// Revocation set; can be switched to failing mode.
#[derive(Debug, Default)]
pub struct FakeRevocations {
    revoked: Mutex<Vec<SessionId>>,
    pub failing: std::sync::atomic::AtomicBool,
}

#[async_trait]
impl RevocationStore for FakeRevocations {
    async fn revoke_sessions(&self, sessions: &[SessionId], _ttl: Duration) -> AppResult<()> {
        self.revoked.lock().unwrap().extend_from_slice(sessions);
        Ok(())
    }

    async fn is_session_revoked(&self, session: SessionId) -> AppResult<bool> {
        if self.failing.load(std::sync::atomic::Ordering::SeqCst) {
            return Err(AppError::Unavailable("valkey"));
        }
        Ok(self.revoked.lock().unwrap().contains(&session))
    }
}

/// Counts requests per key; denies beyond `quota.burst`.
#[derive(Debug, Default)]
pub struct FakeLimiter {
    hits: Mutex<HashMap<String, u32>>,
}

#[async_trait]
impl RateLimiter for FakeLimiter {
    async fn check(&self, key: &str, quota: Quota) -> AppResult<RateDecision> {
        let mut hits = self.hits.lock().unwrap();
        let n = hits.entry(key.to_owned()).or_default();
        *n += 1;
        let allowed = *n <= quota.burst;
        Ok(RateDecision {
            allowed,
            limit: quota.burst,
            remaining: quota.burst.saturating_sub(*n),
            retry_after: if allowed { Duration::ZERO } else { quota.emission_interval() },
            reset_after: quota.emission_interval(),
        })
    }
}

/// Records enqueued jobs; honours dedup keys while a job is pending.
#[derive(Debug, Default)]
pub struct FakeQueue {
    pub jobs: Mutex<Vec<(Job, JobOptions)>>,
}

impl FakeQueue {
    /// Removes and returns every pending job.
    pub fn drain(&self) -> Vec<Job> {
        self.jobs.lock().unwrap().drain(..).map(|(j, _)| j).collect()
    }
}

#[async_trait]
impl JobQueue for FakeQueue {
    async fn enqueue(&self, job: &Job, options: JobOptions) -> AppResult<EnqueueOutcome> {
        let mut jobs = self.jobs.lock().unwrap();
        if options.dedup_key.is_some()
            && jobs.iter().any(|(_, o)| o.dedup_key == options.dedup_key)
        {
            return Ok(EnqueueOutcome::Duplicate);
        }
        jobs.push((job.clone(), options));
        Ok(EnqueueOutcome::Enqueued(Uuid::now_v7()))
    }

    async fn purge_finished(&self, _before: DateTime<Utc>) -> AppResult<u64> {
        Ok(0)
    }
}

/// Records sent e-mails.
#[derive(Debug, Default)]
pub struct FakeMailer {
    pub sent: Mutex<Vec<EmailMessage>>,
}

#[async_trait]
impl Mailer for FakeMailer {
    async fn send(&self, message: &EmailMessage) -> AppResult<()> {
        self.sent.lock().unwrap().push(message.clone());
        Ok(())
    }
}

/// An object stored by [`FakeObjectStorage`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FakeObject {
    pub size_bytes: u64,
    pub content_type: String,
}

/// In-memory object storage. Presigned URLs are `fake://` URLs that encode what was signed;
/// tests "upload" with [`FakeObjectStorage::put`]. Can be switched to failing mode.
pub struct FakeObjectStorage {
    clock: Arc<dyn Clock>,
    download_ttl: Duration,
    objects: Mutex<HashMap<String, FakeObject>>,
    /// Keys deleted so far, in order.
    pub deleted: Mutex<Vec<String>>,
    pub failing: std::sync::atomic::AtomicBool,
}

impl std::fmt::Debug for FakeObjectStorage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("FakeObjectStorage").field("objects", &self.objects).finish_non_exhaustive()
    }
}

impl FakeObjectStorage {
    #[must_use]
    pub fn new(clock: Arc<dyn Clock>) -> Self {
        Self {
            clock,
            download_ttl: Duration::from_secs(3600),
            objects: Mutex::default(),
            deleted: Mutex::default(),
            failing: std::sync::atomic::AtomicBool::new(false),
        }
    }

    /// Stores an object as a client would through a presigned `PUT`.
    pub fn put(&self, key: &str, size_bytes: u64, content_type: &str) {
        let object = FakeObject { size_bytes, content_type: content_type.to_owned() };
        self.objects.lock().unwrap().insert(key.to_owned(), object);
    }

    #[must_use]
    pub fn object(&self, key: &str) -> Option<FakeObject> {
        self.objects.lock().unwrap().get(key).cloned()
    }

    fn check(&self) -> AppResult<()> {
        if self.failing.load(std::sync::atomic::Ordering::SeqCst) {
            return Err(AppError::Unavailable("storage"));
        }
        Ok(())
    }
}

#[async_trait]
impl ObjectStorage for FakeObjectStorage {
    fn presign_put(
        &self,
        key: &str,
        content_type: &str,
        size_bytes: u64,
        expires_in: Duration,
    ) -> PresignedUpload {
        let expires_at = self.clock.now() + chrono_duration(expires_in);
        PresignedUpload {
            url: format!("fake://put/{key}"),
            method: "PUT",
            headers: vec![
                ("content-type", content_type.to_owned()),
                ("content-length", size_bytes.to_string()),
            ],
            expires_at,
        }
    }

    fn presign_get(&self, key: &str) -> String {
        let hour = self.clock.now().duration_trunc(chrono::TimeDelta::hours(1)).unwrap();
        let expires = hour + chrono_duration(self.download_ttl + Duration::from_secs(3600));
        format!("fake://get/{key}?expires={}", expires.timestamp())
    }

    async fn head(&self, key: &str) -> AppResult<Option<ObjectInfo>> {
        self.check()?;
        Ok(self.object(key).map(|o| ObjectInfo {
            size_bytes: o.size_bytes,
            content_type: Some(o.content_type),
        }))
    }

    async fn delete(&self, key: &str) -> AppResult<()> {
        self.check()?;
        self.objects.lock().unwrap().remove(key);
        self.deleted.lock().unwrap().push(key.to_owned());
        Ok(())
    }
}

/// A ready-to-use set of fakes sharing one store and clock.
pub struct Fakes {
    pub store: Arc<InMemoryStore>,
    pub clock: Arc<ManualClock>,
    pub hasher: Arc<FakeHasher>,
    pub tokens: Arc<FakeTokens>,
    pub revocations: Arc<FakeRevocations>,
    pub limiter: Arc<FakeLimiter>,
    pub queue: Arc<FakeQueue>,
    pub mailer: Arc<FakeMailer>,
    pub storage: Arc<FakeObjectStorage>,
}

impl Default for Fakes {
    fn default() -> Self {
        let start = DateTime::parse_from_rfc3339("2026-10-01T08:00:00Z").unwrap().to_utc();
        let clock = Arc::new(ManualClock::new(start));
        Self {
            store: Arc::default(),
            storage: Arc::new(FakeObjectStorage::new(clock.clone())),
            clock,
            hasher: Arc::default(),
            tokens: Arc::default(),
            revocations: Arc::default(),
            limiter: Arc::default(),
            queue: Arc::default(),
            mailer: Arc::default(),
        }
    }
}

impl Fakes {
    /// The default language used by fixtures.
    #[must_use]
    pub const fn lang() -> Lang {
        Lang::Fr
    }

    /// Upload use-cases over the fake store and storage (15-minute upload URLs).
    #[must_use]
    pub fn uploads(&self) -> Arc<UploadService> {
        let storage: Arc<dyn ObjectStorage> = self.storage.clone();
        Arc::new(self.upload_service(Some(storage)))
    }

    /// Upload use-cases of a deployment without object storage.
    #[must_use]
    pub fn uploads_without_storage(&self) -> Arc<UploadService> {
        Arc::new(self.upload_service(None))
    }

    fn upload_service(&self, storage: Option<Arc<dyn ObjectStorage>>) -> UploadService {
        let ttl = Duration::from_secs(900);
        UploadService::new(self.store.clone(), storage, self.clock.clone(), ttl)
    }
}
