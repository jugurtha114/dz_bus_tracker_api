//! RED metrics per route template (never per raw path, to bound cardinality).

use std::time::Instant;

use axum::extract::{MatchedPath, Request};
use axum::middleware::Next;
use axum::response::Response;

pub async fn track(request: Request, next: Next) -> Response {
    let started = Instant::now();
    let method = request.method().as_str().to_owned();
    let route = request
        .extensions()
        .get::<MatchedPath>()
        .map_or_else(|| "unmatched".to_owned(), |p| p.as_str().to_owned());
    metrics::gauge!("dz_http_requests_in_flight").increment(1.0);
    let response = next.run(request).await;
    metrics::gauge!("dz_http_requests_in_flight").decrement(1.0);
    let status = response.status().as_u16().to_string();
    metrics::counter!(
        "dz_http_requests_total",
        "method" => method.clone(),
        "route" => route.clone(),
        "status" => status
    )
    .increment(1);
    metrics::histogram!("dz_http_request_duration_seconds", "method" => method, "route" => route)
        .record(started.elapsed().as_secs_f64());
    response
}
