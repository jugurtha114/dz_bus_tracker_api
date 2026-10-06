//! Request extractors: validated JSON and query strings, the caller, typed permission guards,
//! and request metadata. All rejections are problem documents.

use std::borrow::Cow;
use std::marker::PhantomData;

use axum::extract::{FromRequest, FromRequestParts, Request};
use axum::http::StatusCode;
use axum::http::header::{CONTENT_TYPE, USER_AGENT};
use axum::http::request::Parts;
use bytes::Bytes;
use dz_app::AuthFailure;
use dz_app::ports::{AccessClaims, RequestMeta};
use dz_domain::authz::{Actor, Permission};
use dz_domain::{FieldViolation, Violation};
use serde::de::DeserializeOwned;
use validator::{Validate, ValidationErrors, ValidationErrorsKind};

use crate::error::ApiError;
use crate::middleware::auth::AuthContext;
use crate::middleware::client_ip::ClientIp;
use crate::middleware::request_id::RequestId;

// --- Validation ---------------------------------------------------------------------------------------

/// Maps a `validator` error to a domain violation.
fn violation_from(error: &validator::ValidationError, value_len: Option<u64>) -> Violation {
    let param = |name: &str| error.params.get(name).and_then(serde_json::Value::as_u64);
    let param_i = |name: &str| error.params.get(name).and_then(serde_json::Value::as_i64);
    match error.code.as_ref() {
        "required" => Violation::Required,
        "email" => Violation::InvalidEmail,
        "length" => match (param("min"), param("max"), value_len) {
            (Some(min), _, Some(len)) if len < min => Violation::TooShort { min },
            (_, Some(max), _) => Violation::TooLong { max },
            (Some(min), None, _) => Violation::TooShort { min },
            _ => Violation::InvalidFormat,
        },
        "range" => Violation::OutOfRange {
            min: param_i("min").unwrap_or(i64::MIN),
            max: param_i("max").unwrap_or(i64::MAX),
        },
        _ => Violation::InvalidFormat,
    }
}

fn value_length(error: &validator::ValidationError) -> Option<u64> {
    match error.params.get("value") {
        Some(serde_json::Value::String(s)) => Some(s.chars().count() as u64),
        Some(serde_json::Value::Array(a)) => Some(a.len() as u64),
        _ => None,
    }
}

fn collect(errors: &ValidationErrors, prefix: &str, out: &mut Vec<FieldViolation>) {
    let mut fields: Vec<_> = errors.errors().iter().collect();
    fields.sort_by(|a, b| a.0.cmp(b.0));
    for (field, kind) in fields {
        let path = if prefix.is_empty() { field.to_string() } else { format!("{prefix}.{field}") };
        match kind {
            ValidationErrorsKind::Field(list) => {
                for error in list {
                    out.push(FieldViolation {
                        field: Cow::Owned(path.clone()),
                        violation: violation_from(error, value_length(error)),
                    });
                }
            }
            ValidationErrorsKind::Struct(inner) => collect(inner, &path, out),
            ValidationErrorsKind::List(items) => {
                for (index, inner) in items {
                    collect(inner, &format!("{path}[{index}]"), out);
                }
            }
        }
    }
}

/// Converts `validator` errors into a 422 problem.
#[must_use]
pub fn validation_problem(errors: &ValidationErrors) -> ApiError {
    let mut violations = Vec::new();
    collect(errors, "", &mut violations);
    ApiError::validation(violations)
}

/// Maps a serde error (with its path) to a 422 problem.
fn deserialize_problem<E: std::fmt::Display>(error: serde_path_to_error::Error<E>) -> ApiError {
    let path = error.path().to_string();
    let message = error.inner().to_string();
    let field_from = |marker: &str| {
        message
            .split_once(marker)
            .and_then(|(_, rest)| rest.split('`').next())
            .map(str::to_owned)
    };
    let join = |name: String| if path == "." || path.is_empty() { name } else { format!("{path}.{name}") };
    let (field, violation) = if let Some(name) = field_from("unknown field `") {
        // The path already ends with the unknown field.
        (if path == "." || path.is_empty() { name } else { path }, Violation::UnknownField)
    } else if let Some(name) = field_from("missing field `") {
        (join(name), Violation::Required)
    } else {
        (if path == "." { "body".to_owned() } else { path }, Violation::InvalidFormat)
    };
    ApiError::field(field, violation)
}

/// JSON body that is deserialized strictly (unknown fields rejected by the DTOs) and validated.
pub struct ValidatedJson<T>(pub T);

impl<S, T> FromRequest<S> for ValidatedJson<T>
where
    S: Send + Sync,
    T: DeserializeOwned + Validate,
{
    type Rejection = ApiError;

    async fn from_request(request: Request, state: &S) -> Result<Self, Self::Rejection> {
        let is_json = request
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.split(';').next())
            .map(str::trim)
            .is_some_and(|mime| mime == "application/json" || mime.ends_with("+json"));
        if !is_json {
            return Err(ApiError::new(StatusCode::UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type"));
        }
        let bytes = Bytes::from_request(request, state).await.map_err(|rejection| {
            if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
                ApiError::new(StatusCode::PAYLOAD_TOO_LARGE, "payload_too_large")
            } else {
                ApiError::new(StatusCode::BAD_REQUEST, "malformed_request")
            }
        })?;
        let mut deserializer = serde_json::Deserializer::from_slice(&bytes);
        let value: T = match serde_path_to_error::deserialize(&mut deserializer) {
            Ok(value) => value,
            Err(error) if error.inner().is_syntax() || error.inner().is_eof() => {
                return Err(ApiError::new(StatusCode::BAD_REQUEST, "malformed_request"));
            }
            Err(error) => return Err(deserialize_problem(error)),
        };
        deserializer
            .end()
            .map_err(|_| ApiError::new(StatusCode::BAD_REQUEST, "malformed_request"))?;
        value.validate().map_err(|e| validation_problem(&e))?;
        Ok(Self(value))
    }
}

/// Query string deserialized strictly and validated.
pub struct ValidatedQuery<T>(pub T);

impl<S, T> FromRequestParts<S> for ValidatedQuery<T>
where
    S: Send + Sync,
    T: DeserializeOwned + Validate,
{
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let query = parts.uri.query().unwrap_or_default();
        let deserializer = serde_urlencoded::Deserializer::new(form_urlencoded::parse(query.as_bytes()));
        let value: T = serde_path_to_error::deserialize(deserializer).map_err(deserialize_problem)?;
        value.validate().map_err(|e| validation_problem(&e))?;
        Ok(Self(value))
    }
}

// --- Caller ------------------------------------------------------------------------------------------

/// The caller (possibly anonymous).
pub struct Caller(pub AuthContext);

impl<S: Send + Sync> FromRequestParts<S> for Caller {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        Ok(Self(parts.extensions.get::<AuthContext>().cloned().unwrap_or_else(AuthContext::anonymous)))
    }
}

/// A user authenticated with an access token.
pub struct CurrentUser {
    pub actor: Actor,
    pub claims: AccessClaims,
}

impl<S: Send + Sync> FromRequestParts<S> for CurrentUser {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let context = parts.extensions.get::<AuthContext>();
        match context {
            Some(AuthContext { actor, claims: Some(claims) }) => {
                Ok(Self { actor: actor.clone(), claims: claims.clone() })
            }
            Some(AuthContext { actor: Actor::Service { .. }, .. }) => {
                Err(ApiError::new(StatusCode::FORBIDDEN, "forbidden"))
            }
            _ => Err(ApiError::unauthenticated(AuthFailure::Missing)),
        }
    }
}

/// Compile-time name of a [`Permission`].
pub trait PermissionMarker: Send + Sync + 'static {
    const PERMISSION: Permission;
}

/// Typed permission guard: `RequirePermission<perm::ApiKeyManage>` in a handler signature
/// rejects callers lacking the permission before the handler runs.
pub struct RequirePermission<P: PermissionMarker> {
    pub actor: Actor,
    _permission: PhantomData<P>,
}

impl<S: Send + Sync, P: PermissionMarker> FromRequestParts<S> for RequirePermission<P> {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let Caller(context) = Caller::from_request_parts(parts, state).await?;
        context.actor.require(P::PERMISSION)?;
        Ok(Self { actor: context.actor, _permission: PhantomData })
    }
}

/// Marker types for [`RequirePermission`].
pub mod perm {
    use super::PermissionMarker;
    use dz_domain::authz::Permission;

    macro_rules! markers {
        ($($name:ident),+ $(,)?) => {$(
            #[doc = concat!("Marker for [`Permission::", stringify!($name), "`].")]
            pub struct $name;
            impl PermissionMarker for $name {
                const PERMISSION: Permission = Permission::$name;
            }
        )+};
    }

    markers!(
        AccountSelfManage,
        UserRead,
        UserManage,
        ApiKeyManage,
        AuditLogRead,
        CatalogRead,
        LineWrite,
        StopWrite,
        ScheduleWrite,
        DisruptionWrite,
        DriverApply,
        DriverRead,
        DriverReview,
        BusRegister,
        BusRead,
        BusManage,
        TrackingRead,
        TrackingPublish,
        TripManage,
        TripReadAll,
        AnomalyReport,
        AnomalyResolve,
        WaitingListJoin,
        WaitingReportSubmit,
        WaitingReportVerify,
        DriverRate,
        PassengerCountRecord,
        NotificationSend,
        RewardsRead,
        PremiumPurchase,
        CurrencyAdjust,
        AnalyticsRead,
        OfflineSync,
    );
}

// --- Request metadata ---------------------------------------------------------------------------------

/// Client IP, user agent and request id, for sessions and the audit log.
pub struct Meta(pub RequestMeta);

impl<S: Send + Sync> FromRequestParts<S> for Meta {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        Ok(Self(RequestMeta {
            ip: parts.extensions.get::<ClientIp>().map(|c| c.0),
            user_agent: parts.headers.get(USER_AGENT).and_then(|v| v.to_str().ok()).map(str::to_owned),
            request_id: parts.extensions.get::<RequestId>().map(|r| r.0.clone()),
        }))
    }
}

// --- Path ids & language --------------------------------------------------------------------------------

/// A UUID path segment. A malformed id cannot name an existing resource, so it is a 404.
pub struct PathId(pub uuid::Uuid);

impl<S: Send + Sync> FromRequestParts<S> for PathId {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        axum::extract::Path::<uuid::Uuid>::from_request_parts(parts, state)
            .await
            .map(|axum::extract::Path(id)| Self(id))
            .map_err(|_| ApiError::not_found())
    }
}

/// The caller's language: the saved preference of a signed-in user, else `Accept-Language`,
/// else French.
pub struct ClientLang(pub dz_domain::Lang);

impl<S: Send + Sync> FromRequestParts<S> for ClientLang {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let from_token = parts
            .extensions
            .get::<AuthContext>()
            .and_then(|c| c.claims.as_ref())
            .map(|c| c.lang);
        let negotiated = || {
            parts
                .headers
                .get(axum::http::header::ACCEPT_LANGUAGE)
                .and_then(|v| v.to_str().ok())
                .and_then(dz_domain::Lang::negotiate)
        };
        Ok(Self(from_token.or_else(negotiated).unwrap_or_default()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Deserialize;

    #[derive(Debug, Deserialize, Validate)]
    #[serde(deny_unknown_fields)]
    struct Dto {
        #[validate(length(min = 2, max = 4))]
        name: String,
        #[validate(range(min = 1, max = 9))]
        n: i64,
    }

    #[test]
    fn validator_errors_become_typed_violations() {
        let dto = Dto { name: "a".into(), n: 10 };
        let ApiError(problem) = validation_problem(&dto.validate().unwrap_err());
        let got: Vec<_> = problem.violations.iter().map(|v| (v.field.to_string(), v.violation.clone())).collect();
        assert_eq!(
            got,
            vec![
                ("n".to_owned(), Violation::OutOfRange { min: 1, max: 9 }),
                ("name".to_owned(), Violation::TooShort { min: 2 }),
            ]
        );
        let long = Dto { name: "abcdef".into(), n: 1 };
        let ApiError(problem) = validation_problem(&long.validate().unwrap_err());
        assert_eq!(problem.violations[0].violation, Violation::TooLong { max: 4 });
    }

    #[test]
    fn serde_errors_name_the_field() {
        let parse = |json: &str| {
            let mut de = serde_json::Deserializer::from_str(json);
            serde_path_to_error::deserialize::<_, Dto>(&mut de).map_err(deserialize_problem)
        };
        let ApiError(p) = parse(r#"{"name":"ab","n":1,"role":"admin"}"#).unwrap_err();
        assert_eq!((p.violations[0].field.as_ref(), &p.violations[0].violation), ("role", &Violation::UnknownField));
        let ApiError(p) = parse(r#"{"name":"ab"}"#).unwrap_err();
        assert_eq!((p.violations[0].field.as_ref(), &p.violations[0].violation), ("n", &Violation::Required));
        let ApiError(p) = parse(r#"{"name":"ab","n":"x"}"#).unwrap_err();
        assert_eq!((p.violations[0].field.as_ref(), &p.violations[0].violation), ("n", &Violation::InvalidFormat));
    }
}
