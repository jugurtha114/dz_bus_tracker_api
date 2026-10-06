//! Application errors: domain errors plus authentication, rate limiting and infrastructure
//! failures. The HTTP layer maps each variant to exactly one status code and problem type.

use dz_domain::{ConflictKind, DenyReason, DomainError, Violation, Violations};

/// Why a caller could not be authenticated.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthFailure {
    /// Wrong e-mail/password, unknown account, locked or disabled account (deliberately
    /// indistinguishable to the caller).
    InvalidCredentials,
    /// No credentials were sent to an endpoint that needs them.
    Missing,
    /// The access token is malformed, has a bad signature, wrong issuer/audience or unknown key.
    TokenInvalid,
    TokenExpired,
    /// The session behind the token was revoked (logout, password change, deactivation).
    SessionRevoked,
    /// The refresh token is unknown, expired or revoked.
    RefreshTokenInvalid,
    /// A refresh token was presented twice: the whole session has been revoked.
    RefreshTokenReused,
    ApiKeyInvalid,
    /// The password-reset token is unknown, used or expired.
    ResetTokenInvalid,
}

impl AuthFailure {
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidCredentials => "invalid_credentials",
            Self::Missing => "authentication_required",
            Self::TokenInvalid => "token_invalid",
            Self::TokenExpired => "token_expired",
            Self::SessionRevoked => "session_revoked",
            Self::RefreshTokenInvalid => "refresh_token_invalid",
            Self::RefreshTokenReused => "refresh_token_reused",
            Self::ApiKeyInvalid => "api_key_invalid",
            Self::ResetTokenInvalid => "reset_token_invalid",
        }
    }
}

/// Error returned by every use-case and port.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("validation failed")]
    Validation(Violations),
    #[error("unauthenticated: {}", .0.code())]
    Unauthenticated(AuthFailure),
    #[error("forbidden: {0:?}")]
    Forbidden(DenyReason),
    #[error("{0} not found")]
    NotFound(&'static str),
    #[error("conflict: {}", .0.code())]
    Conflict(ConflictKind),
    #[error("invalid state: {0}")]
    InvalidState(&'static str),
    #[error("rate limited, retry after {retry_after_secs}s")]
    RateLimited { retry_after_secs: u64 },
    #[error("dependency unavailable: {0}")]
    Unavailable(&'static str),
    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

impl AppError {
    /// Validation error for a single field.
    #[must_use]
    pub fn invalid(field: &'static str, violation: Violation) -> Self {
        Self::Validation(Violations::single(field, violation))
    }

    /// Wraps any infrastructure error as an internal error, keeping its context for logs.
    pub fn internal<E>(error: E) -> Self
    where
        E: std::error::Error + Send + Sync + 'static,
    {
        Self::Internal(anyhow::Error::new(error))
    }
}

impl From<DomainError> for AppError {
    fn from(e: DomainError) -> Self {
        match e {
            DomainError::Validation(v) => Self::Validation(v),
            DomainError::NotFound(what) => Self::NotFound(what),
            DomainError::Conflict(kind) => Self::Conflict(kind),
            DomainError::Forbidden(reason) => Self::Forbidden(reason),
            DomainError::InvalidState(what) => Self::InvalidState(what),
        }
    }
}

impl From<Violations> for AppError {
    fn from(v: Violations) -> Self {
        Self::Validation(v)
    }
}

impl From<DenyReason> for AppError {
    fn from(reason: DenyReason) -> Self {
        match reason {
            DenyReason::AuthenticationRequired => Self::Unauthenticated(AuthFailure::Missing),
            other => Self::Forbidden(other),
        }
    }
}

/// Result alias used across the application layer.
pub type AppResult<T> = Result<T, AppError>;
