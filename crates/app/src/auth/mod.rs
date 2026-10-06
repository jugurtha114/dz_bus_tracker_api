//! Authentication use-cases: registration, login, token refresh, logout, password change and
//! reset, session management, and access-token authentication.

pub mod secrets;

#[cfg(test)]
mod tests;

use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use dz_domain::Lang;
use dz_domain::authz::{Action, Actor, Policy};
use dz_domain::ids::{SessionId, UserId};
use dz_domain::password::{PasswordContext, PasswordPolicy};
use dz_domain::user::{Email, PersonName, PhoneNumber, Profile, Role, User};
use dz_domain::{Violation, Violations};
use secrecy::{ExposeSecret, SecretString};
use uuid::Uuid;

use crate::error::{AppError, AppResult, AuthFailure};
use crate::jobs::{Job, after};
use crate::ports::{
    AccessClaims, AccessTokenCodec, Clock, Credentials, JobOptions, JobQueue, LockoutPolicy,
    NewRefreshToken, NewSession, NewUser, PasswordCheck, PasswordHasher, PasswordResetRepository,
    Quota, RateLimiter, RequestMeta, RevocationReason, RevocationStore, RotateOutcome,
    SessionInfo, SessionRepository, UserRepository,
};

/// Longest stored user-agent string.
const MAX_USER_AGENT: usize = 255;

/// Tunables of the authentication use-cases.
#[derive(Debug, Clone)]
pub struct AuthSettings {
    pub access_ttl: Duration,
    pub refresh_ttl: Duration,
    pub session_max_lifetime: Duration,
    pub password_policy: PasswordPolicy,
    pub lockout: LockoutPolicy,
    /// Reset requests accepted per e-mail address.
    pub reset_quota: Quota,
    /// Accept requests when the revocation store is unreachable.
    pub revocation_fail_open: bool,
}

/// Adapters the authentication use-cases depend on.
#[derive(Clone)]
pub struct AuthDeps {
    pub users: Arc<dyn UserRepository>,
    pub sessions: Arc<dyn SessionRepository>,
    pub resets: Arc<dyn PasswordResetRepository>,
    pub hasher: Arc<dyn PasswordHasher>,
    pub tokens: Arc<dyn AccessTokenCodec>,
    pub revocations: Arc<dyn RevocationStore>,
    pub jobs: Arc<dyn JobQueue>,
    pub limiter: Arc<dyn RateLimiter>,
    pub clock: Arc<dyn Clock>,
}

/// An access token plus its refresh token.
#[derive(Debug, Clone)]
pub struct TokenPair {
    pub access_token: String,
    pub access_expires_at: DateTime<Utc>,
    pub refresh_token: String,
    pub refresh_expires_at: DateTime<Utc>,
    pub session_id: SessionId,
}

/// Input of [`AuthService::register`].
#[derive(Debug)]
pub struct RegisterInput {
    pub email: String,
    pub password: SecretString,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub phone_number: Option<String>,
    pub language: Option<Lang>,
}

/// A session opened by registration or login.
#[derive(Debug, Clone)]
pub struct SignedIn {
    pub user: User,
    pub profile: Option<Profile>,
    pub tokens: TokenPair,
}

/// A session listed to its owner.
#[derive(Debug, Clone)]
pub struct OwnSession {
    pub info: SessionInfo,
    pub current: bool,
}

pub struct AuthService {
    deps: AuthDeps,
    settings: AuthSettings,
}

impl AuthService {
    #[must_use]
    pub fn new(deps: AuthDeps, settings: AuthSettings) -> Self {
        Self { deps, settings }
    }

    #[must_use]
    pub fn settings(&self) -> &AuthSettings {
        &self.settings
    }

    /// Creates a passenger account and signs it in. The role is never client-controlled.
    pub async fn register(&self, input: RegisterInput, meta: &RequestMeta) -> AppResult<SignedIn> {
        let mut v = Violations::new();
        let email = v.check("email", Email::parse(&input.email));
        let first_name =
            v.check("first_name", PersonName::parse(input.first_name.as_deref().unwrap_or("")));
        let last_name =
            v.check("last_name", PersonName::parse(input.last_name.as_deref().unwrap_or("")));
        let phone_number = match input.phone_number.as_deref().map(str::trim) {
            None | Some("") => Some(None),
            Some(raw) => v.check("phone_number", PhoneNumber::parse(raw)).map(Some),
        };
        // The password is checked even when other fields are invalid, so that a client gets
        // every problem in one response.
        let ctx = PasswordContext {
            email_local_part: email.as_ref().map(Email::local_part),
            first_name: first_name.as_ref().map(PersonName::as_str),
            last_name: last_name.as_ref().map(PersonName::as_str),
        };
        v.check("password", self.settings.password_policy.validate(input.password.expose_secret(), ctx));
        let (Some(email), Some(first_name), Some(last_name), Some(phone_number)) =
            (email, first_name, last_name, phone_number)
        else {
            return Err(v.into());
        };
        if !v.is_empty() {
            return Err(v.into());
        }

        let password_hash = self.deps.hasher.hash(&input.password).await?;
        let now = self.deps.clock.now();
        let language = input.language.unwrap_or_default();
        let (user, profile) = self
            .deps
            .users
            .insert(NewUser {
                id: UserId::generate(),
                email,
                password_hash,
                role: Role::Passenger,
                first_name,
                last_name,
                phone_number,
                language,
                created_at: now,
            })
            .await?;
        tracing::info!(user_id = %user.id, "account registered");
        let tokens = self.open_session(&user, language, meta).await?;
        Ok(SignedIn { user, profile: Some(profile), tokens })
    }

    /// Verifies e-mail and password and opens a session.
    ///
    /// Every failure (unknown account, wrong password, locked or disabled account) returns the
    /// same error after the same amount of work, so the response reveals nothing.
    pub async fn login(
        &self,
        email: &str,
        password: &SecretString,
        meta: &RequestMeta,
    ) -> AppResult<SignedIn> {
        let invalid = || AppError::Unauthenticated(AuthFailure::InvalidCredentials);
        let now = self.deps.clock.now();
        let credentials = match Email::parse(email) {
            Ok(email) => self.deps.users.credentials_by_email(&email).await?,
            Err(_) => None,
        };
        let Some(credentials) = credentials else {
            self.deps.hasher.burn(password).await;
            return Err(invalid());
        };
        let user_id = credentials.user.id;
        if credentials.locked_until.is_some_and(|until| until > now) {
            // Do not even check the password while locked: no guessing during the lock.
            self.deps.hasher.burn(password).await;
            tracing::info!(%user_id, "login attempt on a locked account");
            return Err(invalid());
        }
        let Some(stored) = credentials.password_hash.as_deref() else {
            self.deps.hasher.burn(password).await;
            return Err(invalid());
        };
        match self.deps.hasher.verify(password, stored).await? {
            PasswordCheck::Mismatch => {
                self.deps.users.record_login_failure(user_id, now, self.settings.lockout).await?;
                tracing::info!(%user_id, "failed login");
                Err(invalid())
            }
            PasswordCheck::Match { .. } if !credentials.user.is_active => {
                tracing::info!(%user_id, "login attempt on a deactivated account");
                Err(invalid())
            }
            PasswordCheck::Match { needs_rehash } => {
                let upgraded = if needs_rehash {
                    Some(self.deps.hasher.hash(password).await?)
                } else {
                    None
                };
                if upgraded.is_some() {
                    tracing::info!(%user_id, "password hash upgraded to the current algorithm");
                }
                self.deps.users.record_login_success(user_id, now, upgraded).await?;
                let tokens = self.open_session(&credentials.user, credentials.language, meta).await?;
                let mut user = credentials.user;
                user.last_login_at = Some(now);
                Ok(SignedIn { user, profile: None, tokens })
            }
        }
    }

    /// Exchanges a refresh token for a new token pair (rotation with reuse detection).
    pub async fn refresh(&self, refresh_token: &str) -> AppResult<TokenPair> {
        let presented = secrets::hash(refresh_token);
        let next = secrets::generate("dzr");
        let now = self.deps.clock.now();
        let outcome =
            self.deps.sessions.rotate(presented, next.hash, now, self.settings.refresh_ttl).await?;
        match outcome {
            RotateOutcome::Invalid => {
                Err(AppError::Unauthenticated(AuthFailure::RefreshTokenInvalid))
            }
            RotateOutcome::Reused { user_id, session_id } => {
                tracing::warn!(%user_id, %session_id, "refresh token reuse detected; session revoked");
                self.cut_off(&[session_id]).await?;
                Err(AppError::Unauthenticated(AuthFailure::RefreshTokenReused))
            }
            RotateOutcome::Rotated { user_id, session_id, refresh_expires_at } => {
                let credentials = self.deps.users.credentials_by_id(user_id).await?;
                let Some(credentials) = credentials.filter(|c| c.user.is_active) else {
                    self.deps
                        .sessions
                        .revoke(user_id, session_id, RevocationReason::AdminAction, now)
                        .await?;
                    self.cut_off(&[session_id]).await?;
                    return Err(AppError::Unauthenticated(AuthFailure::RefreshTokenInvalid));
                };
                let (access_token, access_expires_at) =
                    self.mint_access(&credentials, session_id, now)?;
                Ok(TokenPair {
                    access_token,
                    access_expires_at,
                    refresh_token: next.plaintext,
                    refresh_expires_at,
                    session_id,
                })
            }
        }
    }

    /// Ends the caller's session, or all of their sessions.
    pub async fn logout(&self, claims: &AccessClaims, everywhere: bool) -> AppResult<()> {
        let now = self.deps.clock.now();
        let revoked = if everywhere {
            self.deps.sessions.revoke_all(claims.sub, RevocationReason::Logout, now, None).await?
        } else {
            self.deps.sessions.revoke(claims.sub, claims.sid, RevocationReason::Logout, now).await?;
            vec![claims.sid]
        };
        self.cut_off(&revoked).await
    }

    /// Validates a bearer access token and checks that its session is still alive.
    pub async fn authenticate(&self, bearer: &str) -> AppResult<AccessClaims> {
        let claims =
            self.deps.tokens.verify(bearer, self.deps.clock.now()).map_err(AppError::Unauthenticated)?;
        match self.deps.revocations.is_session_revoked(claims.sid).await {
            Ok(false) => Ok(claims),
            Ok(true) => Err(AppError::Unauthenticated(AuthFailure::SessionRevoked)),
            Err(error) if self.settings.revocation_fail_open => {
                tracing::warn!(%error, "revocation store unreachable; accepting token (fail-open)");
                Ok(claims)
            }
            Err(error) => {
                tracing::error!(%error, "revocation store unreachable; rejecting token");
                Err(AppError::Unavailable("session store"))
            }
        }
    }

    /// Changes the caller's password and signs out every other session.
    pub async fn change_password(
        &self,
        claims: &AccessClaims,
        current: &SecretString,
        new: &SecretString,
    ) -> AppResult<()> {
        let credentials = self
            .deps
            .users
            .credentials_by_id(claims.sub)
            .await?
            .filter(|c| c.user.is_active)
            .ok_or(AppError::Unauthenticated(AuthFailure::SessionRevoked))?;
        let stored = credentials.password_hash.as_deref().unwrap_or_default();
        let matches = !stored.is_empty()
            && matches!(
                self.deps.hasher.verify(current, stored).await?,
                PasswordCheck::Match { .. }
            );
        if !matches {
            return Err(AppError::invalid("current_password", Violation::Incorrect));
        }
        if current.expose_secret() == new.expose_secret() {
            return Err(AppError::invalid("new_password", Violation::PasswordReused));
        }
        self.check_policy("new_password", &credentials, new)?;
        let hash = self.deps.hasher.hash(new).await?;
        let now = self.deps.clock.now();
        let revoked =
            self.deps.users.change_password(claims.sub, hash, now, Some(claims.sid)).await?;
        tracing::info!(user_id = %claims.sub, revoked = revoked.len(), "password changed");
        self.cut_off(&revoked).await
    }

    /// Starts a password reset. Always succeeds (when the input is well-formed) so that the
    /// response does not reveal whether the account exists; the worker does the rest.
    pub async fn request_password_reset(
        &self,
        email: &str,
        lang: Lang,
        meta: &RequestMeta,
    ) -> AppResult<()> {
        let email = Email::parse(email).map_err(|v| AppError::invalid("email", v))?;
        let key = format!("password_reset:{}", secrets::opaque_key(email.as_str()));
        let decision = self.deps.limiter.check(&key, self.settings.reset_quota).await;
        match decision {
            Ok(d) if !d.allowed => {
                tracing::info!("password reset request dropped (per-address quota)");
                return Ok(());
            }
            Ok(_) => {}
            Err(error) => tracing::warn!(%error, "rate limiter unavailable for reset requests"),
        }
        let job = Job::PasswordResetRequested {
            email: email.as_str().to_owned(),
            lang,
            requested_ip: meta.ip,
        };
        let options = JobOptions { dedup_key: Some(key), ..JobOptions::default() };
        self.deps.jobs.enqueue(&job, options).await?;
        Ok(())
    }

    /// Completes a password reset with the e-mailed token; signs out every session.
    pub async fn confirm_password_reset(
        &self,
        token: &str,
        new_password: &SecretString,
    ) -> AppResult<()> {
        let invalid = || AppError::Unauthenticated(AuthFailure::ResetTokenInvalid);
        let hash = secrets::hash(token.trim());
        let now = self.deps.clock.now();
        let user_id = self.deps.resets.find_valid(hash, now).await?.ok_or_else(invalid)?;
        let credentials = self.deps.users.credentials_by_id(user_id).await?.ok_or_else(invalid)?;
        self.check_policy("new_password", &credentials, new_password)?;
        let password_hash = self.deps.hasher.hash(new_password).await?;
        let (user_id, revoked) =
            self.deps.resets.consume(hash, password_hash, now).await?.ok_or_else(invalid)?;
        tracing::info!(%user_id, revoked = revoked.len(), "password reset completed");
        self.cut_off(&revoked).await
    }

    /// Active sessions of the caller.
    pub async fn list_sessions(&self, claims: &AccessClaims) -> AppResult<Vec<OwnSession>> {
        let sessions = self.deps.sessions.list_active(claims.sub, self.deps.clock.now()).await?;
        Ok(sessions
            .into_iter()
            .map(|info| OwnSession { current: info.id == claims.sid, info })
            .collect())
    }

    /// Revokes one of the caller's sessions (e.g. a lost phone).
    pub async fn revoke_session(&self, actor: &Actor, session_id: SessionId) -> AppResult<()> {
        Policy::authorize(actor, &Action::ManageOwnAccount)?;
        let user_id = actor.user_id().ok_or(AppError::Unauthenticated(AuthFailure::Missing))?;
        let now = self.deps.clock.now();
        let revoked = self
            .deps
            .sessions
            .revoke(user_id, session_id, RevocationReason::UserRequest, now)
            .await?;
        if !revoked {
            return Err(AppError::NotFound("session"));
        }
        self.cut_off(&[session_id]).await
    }

    fn check_policy(
        &self,
        field: &'static str,
        credentials: &Credentials,
        password: &SecretString,
    ) -> AppResult<()> {
        let user = &credentials.user;
        let ctx = PasswordContext {
            email_local_part: Some(user.email.local_part()),
            first_name: Some(user.first_name.as_str()),
            last_name: Some(user.last_name.as_str()),
        };
        self.settings
            .password_policy
            .validate(password.expose_secret(), ctx)
            .map_err(|v| AppError::invalid(field, v))
    }

    async fn open_session(
        &self,
        user: &User,
        language: Lang,
        meta: &RequestMeta,
    ) -> AppResult<TokenPair> {
        let now = self.deps.clock.now();
        let session_id = SessionId::generate();
        let session_end = after(now, self.settings.session_max_lifetime);
        let refresh = secrets::generate("dzr");
        let refresh_expires_at = after(now, self.settings.refresh_ttl).min(session_end);
        let user_agent = meta
            .user_agent
            .as_deref()
            .map(|ua| ua.chars().filter(|c| !c.is_control()).take(MAX_USER_AGENT).collect());
        self.deps
            .sessions
            .create(
                NewSession {
                    id: session_id,
                    user_id: user.id,
                    created_at: now,
                    expires_at: session_end,
                    user_agent,
                    ip: meta.ip,
                },
                NewRefreshToken {
                    hash: refresh.hash,
                    session_id,
                    issued_at: now,
                    expires_at: refresh_expires_at,
                },
            )
            .await?;
        let claims_source = Credentials {
            user: user.clone(),
            password_hash: None,
            failed_login_attempts: 0,
            locked_until: None,
            language,
        };
        let (access_token, access_expires_at) = self.mint_access(&claims_source, session_id, now)?;
        Ok(TokenPair {
            access_token,
            access_expires_at,
            refresh_token: refresh.plaintext,
            refresh_expires_at,
            session_id,
        })
    }

    fn mint_access(
        &self,
        credentials: &Credentials,
        session_id: SessionId,
        now: DateTime<Utc>,
    ) -> AppResult<(String, DateTime<Utc>)> {
        let expires_at = after(now, self.settings.access_ttl);
        let claims = AccessClaims {
            sub: credentials.user.id,
            sid: session_id,
            role: credentials.user.role,
            lang: credentials.language,
            iat: now.timestamp(),
            exp: expires_at.timestamp(),
            jti: Uuid::now_v7(),
        };
        Ok((self.deps.tokens.issue(&claims)?, expires_at))
    }

    /// Makes revoked sessions' access tokens unusable immediately (they would otherwise stay
    /// valid until they expire).
    async fn cut_off(&self, sessions: &[SessionId]) -> AppResult<()> {
        if sessions.is_empty() {
            return Ok(());
        }
        // Entries only need to outlive the longest-lived access token.
        let ttl = self.settings.access_ttl + Duration::from_secs(60);
        self.deps.revocations.revoke_sessions(sessions, ttl).await
    }
}

/// Converts verified access-token claims into the actor used by the authorization policy.
#[must_use]
pub fn actor_from_claims(claims: &AccessClaims) -> Actor {
    Actor::User { id: claims.sub, role: claims.role, session_id: claims.sid }
}
