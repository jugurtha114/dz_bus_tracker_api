//! RFC 9457 problem details.
//!
//! Handlers and middleware return [`ApiError`]. Its response carries the [`Problem`] in the
//! response extensions; the outermost [`render_problems`] middleware then writes the body in the
//! caller's language with the request's `instance` path and request id. Every error response of
//! the API, including 404/405 from the router and panics, has the same shape.

use axum::extract::Request;
use axum::http::header::{CONTENT_LANGUAGE, CONTENT_TYPE, RETRY_AFTER, WWW_AUTHENTICATE};
use axum::http::{HeaderValue, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use dz_app::{AppError, AuthFailure};
use dz_domain::{DenyReason, FieldViolation, Lang, Violation};
use serde::Serialize;
use utoipa::ToSchema;

use crate::i18n;

/// Media type of problem documents.
pub const PROBLEM_JSON: &str = "application/problem+json";

/// The language chosen for this response (set by the authentication middleware from the
/// access token, which reflects the user's saved preference).
#[derive(Debug, Clone, Copy)]
pub struct ResolvedLang(pub Lang);

/// Everything needed to render a problem document.
#[derive(Debug, Clone)]
pub struct Problem {
    pub status: StatusCode,
    pub code: &'static str,
    pub violations: Vec<FieldViolation>,
    pub retry_after_secs: Option<u64>,
    /// `error` parameter of the `WWW-Authenticate: Bearer` challenge, for 401 responses.
    pub bearer_error: Option<&'static str>,
}

impl Problem {
    #[must_use]
    pub fn new(status: StatusCode, code: &'static str) -> Self {
        Self { status, code, violations: Vec::new(), retry_after_secs: None, bearer_error: None }
    }
}

/// An error returned by a handler or middleware.
#[derive(Debug)]
pub struct ApiError(pub Problem);

impl ApiError {
    #[must_use]
    pub fn new(status: StatusCode, code: &'static str) -> Self {
        Self(Problem::new(status, code))
    }

    #[must_use]
    pub fn validation(violations: Vec<FieldViolation>) -> Self {
        let mut problem = Problem::new(StatusCode::UNPROCESSABLE_ENTITY, "validation_error");
        problem.violations = violations;
        Self(problem)
    }

    #[must_use]
    pub fn field(field: impl Into<std::borrow::Cow<'static, str>>, violation: Violation) -> Self {
        Self::validation(vec![FieldViolation { field: field.into(), violation }])
    }

    #[must_use]
    pub fn not_found() -> Self {
        Self::new(StatusCode::NOT_FOUND, "not_found")
    }

    #[must_use]
    pub fn rate_limited(retry_after_secs: u64) -> Self {
        let mut problem = Problem::new(StatusCode::TOO_MANY_REQUESTS, "rate_limited");
        problem.retry_after_secs = Some(retry_after_secs.max(1));
        Self(problem)
    }

    #[must_use]
    pub fn unauthenticated(failure: AuthFailure) -> Self {
        let status = match failure {
            AuthFailure::ResetTokenInvalid => StatusCode::BAD_REQUEST,
            _ => StatusCode::UNAUTHORIZED,
        };
        let mut problem = Problem::new(status, failure.code());
        problem.bearer_error = match failure {
            AuthFailure::TokenInvalid | AuthFailure::TokenExpired | AuthFailure::SessionRevoked => {
                Some("invalid_token")
            }
            AuthFailure::Missing => Some(""),
            _ => None,
        };
        Self(problem)
    }
}

impl From<AppError> for ApiError {
    fn from(error: AppError) -> Self {
        match error {
            AppError::Validation(v) => Self::validation(v.into_iter().collect()),
            AppError::Unauthenticated(failure) => Self::unauthenticated(failure),
            AppError::Forbidden(DenyReason::AuthenticationRequired) => {
                Self::unauthenticated(AuthFailure::Missing)
            }
            AppError::Forbidden(_) => Self::new(StatusCode::FORBIDDEN, "forbidden"),
            AppError::NotFound(_) => Self::not_found(),
            AppError::Conflict(kind) => Self::new(StatusCode::CONFLICT, kind.code()),
            AppError::InvalidState(_) => Self::new(StatusCode::CONFLICT, "invalid_state"),
            AppError::RateLimited { retry_after_secs } => Self::rate_limited(retry_after_secs),
            AppError::Unavailable(what) => {
                tracing::warn!(dependency = what, "dependency unavailable");
                // Object storage is optional and may be unconfigured: clients can tell that
                // apart from the API itself being unavailable.
                let code =
                    if what == "storage" { "storage_unavailable" } else { "service_unavailable" };
                let mut problem = Problem::new(StatusCode::SERVICE_UNAVAILABLE, code);
                problem.retry_after_secs = Some(5);
                Self(problem)
            }
            AppError::Internal(error) => {
                tracing::error!(error = ?error, "internal error");
                Self::new(StatusCode::INTERNAL_SERVER_ERROR, "internal_error")
            }
        }
    }
}

impl From<DenyReason> for ApiError {
    fn from(reason: DenyReason) -> Self {
        AppError::from(reason).into()
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let problem = self.0;
        let body = render_body(&problem, Lang::default(), None, None);
        let mut response = (problem.status, body).into_response();
        decorate(&mut response, &problem, Lang::default());
        response.extensions_mut().insert(problem);
        response
    }
}

/// A field error in a problem document.
#[derive(Debug, Serialize, ToSchema)]
pub struct ProblemFieldError {
    /// Path of the offending field (`email`, `scopes[2]`).
    pub field: String,
    /// Stable machine code (`required`, `invalid_email`, `too_long`, ...).
    pub code: String,
    /// Localized human-readable message.
    pub message: String,
    /// Parameters of the rule (e.g. `{"max": 150}`).
    #[serde(skip_serializing_if = "Option::is_none")]
    #[schema(value_type = Option<Object>)]
    pub params: Option<serde_json::Value>,
}

/// RFC 9457 problem document returned by every error response.
#[derive(Debug, Serialize, ToSchema)]
pub struct ProblemDocument {
    /// URI identifying the problem type (`urn:dzbus:problem:<code>`).
    #[serde(rename = "type")]
    pub problem_type: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
    /// The request path that produced the problem.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub instance: Option<String>,
    /// Stable machine-readable code.
    pub code: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub errors: Vec<ProblemFieldError>,
}

fn render_body(
    problem: &Problem,
    lang: Lang,
    instance: Option<String>,
    request_id: Option<String>,
) -> String {
    let text = i18n::problem(problem.code, lang);
    let errors = problem
        .violations
        .iter()
        .map(|fv| {
            let params = serde_json::to_value(&fv.violation).ok().and_then(|mut v| {
                let object = v.as_object_mut()?;
                object.remove("code");
                (!object.is_empty()).then_some(v)
            });
            ProblemFieldError {
                field: fv.field.to_string(),
                code: fv.violation.code().to_owned(),
                message: i18n::violation(&fv.violation, lang),
                params,
            }
        })
        .collect();
    let document = ProblemDocument {
        problem_type: format!("urn:dzbus:problem:{}", problem.code.replace('_', "-")),
        title: text.title.to_owned(),
        status: problem.status.as_u16(),
        detail: text.detail.to_owned(),
        instance,
        code: problem.code.to_owned(),
        request_id,
        errors,
    };
    serde_json::to_string(&document).unwrap_or_else(|_| "{}".to_owned())
}

fn decorate(response: &mut Response, problem: &Problem, lang: Lang) {
    let headers = response.headers_mut();
    headers.insert(CONTENT_TYPE, HeaderValue::from_static(PROBLEM_JSON));
    headers.insert(CONTENT_LANGUAGE, HeaderValue::from_static(lang.as_str()));
    if let Some(secs) = problem.retry_after_secs {
        headers.insert(RETRY_AFTER, HeaderValue::from(secs));
    }
    if let Some(error) = problem.bearer_error {
        let challenge = if error.is_empty() {
            "Bearer realm=\"dz-bus-tracker\"".to_owned()
        } else {
            format!("Bearer realm=\"dz-bus-tracker\", error=\"{error}\"")
        };
        if let Ok(value) = HeaderValue::from_str(&challenge) {
            headers.insert(WWW_AUTHENTICATE, value);
        }
    }
}

/// Outermost error middleware: localizes problem documents and turns bare router errors
/// (404/405 with an empty body) into problems.
pub async fn render_problems(request: Request, next: Next) -> Response {
    let negotiated = request
        .headers()
        .get(axum::http::header::ACCEPT_LANGUAGE)
        .and_then(|v| v.to_str().ok())
        .and_then(Lang::negotiate);
    let instance = request.uri().path().to_owned();
    let request_id = request
        .headers()
        .get(crate::middleware::REQUEST_ID)
        .and_then(|v| v.to_str().ok())
        .map(str::to_owned);
    let mut response = next.run(request).await;

    let problem = match response.extensions_mut().remove::<Problem>() {
        Some(problem) => problem,
        None if response.status() == StatusCode::METHOD_NOT_ALLOWED => {
            Problem::new(StatusCode::METHOD_NOT_ALLOWED, "method_not_allowed")
        }
        None => return response,
    };
    let lang = response
        .extensions()
        .get::<ResolvedLang>()
        .map(|l| l.0)
        .or(negotiated)
        .unwrap_or_default();
    let body = render_body(&problem, lang, Some(instance), request_id);
    let (mut parts, _) = response.into_parts();
    parts.headers.remove(axum::http::header::CONTENT_LENGTH);
    let mut response = Response::from_parts(parts, axum::body::Body::from(body));
    *response.status_mut() = problem.status;
    decorate(&mut response, &problem, lang);
    response
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_errors_map_to_statuses_and_codes() {
        let cases = [
            (AppError::NotFound("user"), StatusCode::NOT_FOUND, "not_found"),
            (
                AppError::Unauthenticated(AuthFailure::InvalidCredentials),
                StatusCode::UNAUTHORIZED,
                "invalid_credentials",
            ),
            (
                AppError::Unauthenticated(AuthFailure::ResetTokenInvalid),
                StatusCode::BAD_REQUEST,
                "reset_token_invalid",
            ),
            (AppError::Forbidden(DenyReason::NotOwner), StatusCode::FORBIDDEN, "forbidden"),
            (
                AppError::Forbidden(DenyReason::AuthenticationRequired),
                StatusCode::UNAUTHORIZED,
                "authentication_required",
            ),
            (
                AppError::Conflict(dz_domain::ConflictKind::EmailTaken),
                StatusCode::CONFLICT,
                "email_taken",
            ),
            (AppError::RateLimited { retry_after_secs: 3 }, StatusCode::TOO_MANY_REQUESTS, "rate_limited"),
            (AppError::Unavailable("db"), StatusCode::SERVICE_UNAVAILABLE, "service_unavailable"),
            (
                AppError::Unavailable("storage"),
                StatusCode::SERVICE_UNAVAILABLE,
                "storage_unavailable",
            ),
            (
                AppError::Conflict(dz_domain::ConflictKind::UploadAlreadyUsed),
                StatusCode::CONFLICT,
                "upload_already_used",
            ),
            (
                AppError::Internal(anyhow::anyhow!("boom")),
                StatusCode::INTERNAL_SERVER_ERROR,
                "internal_error",
            ),
        ];
        for (error, status, code) in cases {
            let ApiError(problem) = error.into();
            assert_eq!((problem.status, problem.code), (status, code));
        }
    }

    #[test]
    fn bodies_are_localized_with_field_params() {
        let mut problem = Problem::new(StatusCode::UNPROCESSABLE_ENTITY, "validation_error");
        problem.violations.push(FieldViolation {
            field: "first_name".into(),
            violation: Violation::TooLong { max: 150 },
        });
        let body: serde_json::Value = serde_json::from_str(&render_body(
            &problem,
            Lang::Ar,
            Some("/x".into()),
            Some("rid".into()),
        ))
        .unwrap();
        assert_eq!(body["type"], "urn:dzbus:problem:validation-error");
        assert_eq!(body["status"], 422);
        assert_eq!(body["instance"], "/x");
        assert_eq!(body["request_id"], "rid");
        assert_eq!(body["errors"][0]["code"], "too_long");
        assert_eq!(body["errors"][0]["params"]["max"], 150);
        assert_eq!(body["title"], "بيانات غير صالحة");
    }
}
