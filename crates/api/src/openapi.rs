//! OpenAPI 3.1 description assembled from the annotated handlers.

use utoipa::openapi::security::{ApiKey, ApiKeyValue, HttpAuthScheme, HttpBuilder, SecurityScheme};
use utoipa::{Modify, OpenApi};

use crate::error::{ProblemDocument, ProblemFieldError};

#[derive(OpenApi)]
#[openapi(
    info(
        title = "DZ Bus Tracker API",
        version = "1.0.0",
        description = "Real-time bus tracking for Algeria.\n\n\
            * JSON uses snake_case; timestamps are RFC 3339 UTC.\n\
            * Errors are RFC 9457 problem documents (`application/problem+json`) with a stable \
              `code`, localized in French (default), Arabic or English via `Accept-Language`.\n\
            * Lists use cursor pagination: `?limit=` (1–100) and `?cursor=` from `next_cursor`.\n\
            * Cacheable GETs return a weak `ETag`; send `If-None-Match` to get `304`.\n\
            * Rate limits are reported in `RateLimit-*` headers; `429` carries `Retry-After`.",
        license(name = "Proprietary"),
    ),
    tags(
        (name = "auth", description = "Registration, sign-in, tokens, passwords and sessions"),
        (name = "me", description = "The signed-in user's account and preferences"),
        (name = "uploads", description = "Presigned uploads of photos and documents"),
        (name = "stops", description = "Bus stops: catalogue, nearby search, administration"),
        (name = "lines", description = "Bus lines with their ordered stops and route"),
        (name = "schedules", description = "Weekly service windows of the lines"),
        (name = "drivers", description = "Driver applications, profiles, reviews and history"),
        (name = "admin", description = "Administration (users, API keys, audit log)"),
        (name = "ops", description = "Health probes and signing keys"),
    ),
    components(schemas(ProblemDocument, ProblemFieldError)),
    modifiers(&SecuritySchemes),
)]
pub struct ApiDoc;

struct SecuritySchemes;

impl Modify for SecuritySchemes {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let components = openapi.components.get_or_insert_with(Default::default);
        components.add_security_scheme(
            "bearer",
            SecurityScheme::Http(
                HttpBuilder::new()
                    .scheme(HttpAuthScheme::Bearer)
                    .bearer_format("JWT")
                    .description(Some("Access token from /auth/login or /auth/refresh (EdDSA)."))
                    .build(),
            ),
        );
        components.add_security_scheme(
            "api_key",
            SecurityScheme::ApiKey(ApiKey::Header(ApiKeyValue::with_description(
                "X-Api-Key",
                "Machine-to-machine key (`dzk_…`) with explicit scopes.",
            ))),
        );
    }
}
