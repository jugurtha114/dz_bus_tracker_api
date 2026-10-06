//! Per-request processing deadline, answered with a problem document.

use std::time::Duration;

use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};

use crate::error::{ApiError, Problem};

pub async fn deadline(State(limit): State<Duration>, request: Request, next: Next) -> Response {
    match tokio::time::timeout(limit, next.run(request)).await {
        Ok(response) => response,
        Err(_) => {
            metrics::counter!("dz_http_timeouts_total").increment(1);
            let mut problem = Problem::new(StatusCode::SERVICE_UNAVAILABLE, "request_timeout");
            problem.retry_after_secs = Some(1);
            ApiError(problem).into_response()
        }
    }
}
