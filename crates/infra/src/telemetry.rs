//! Logging, tracing and metrics setup.
//!
//! * Structured logs (JSON in production) via `tracing-subscriber`, filtered by
//!   `DZ_TELEMETRY__LOG_FILTER`.
//! * Optional OpenTelemetry trace export over OTLP/HTTP when `DZ_TELEMETRY__OTLP_ENDPOINT` is set.
//! * Prometheus metrics through the `metrics` facade.
//!
//! Call [`init`] from a synchronous `main` before starting the Tokio runtime: the OTLP exporter
//! uses a blocking HTTP client that must not be created or dropped inside the runtime.

use dz_config::{LogFormat, TelemetrySettings};
use metrics_exporter_prometheus::{Matcher, PrometheusBuilder, PrometheusHandle};
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::{Protocol, WithExportConfig};
use opentelemetry_sdk::Resource;
use opentelemetry_sdk::trace::{Sampler, SdkTracerProvider};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::{EnvFilter, Layer};

/// Flushes and shuts down exporters when dropped.
pub struct TelemetryGuard {
    tracer_provider: Option<SdkTracerProvider>,
}

impl Drop for TelemetryGuard {
    fn drop(&mut self) {
        if let Some(provider) = self.tracer_provider.take()
            && let Err(error) = provider.shutdown()
        {
            eprintln!("failed to flush traces: {error}");
        }
    }
}

/// Installs the global tracing subscriber. `component` names the binary (api, worker, cli).
pub fn init(settings: &TelemetrySettings, component: &str) -> anyhow::Result<TelemetryGuard> {
    let filter = EnvFilter::try_new(&settings.log_filter)
        .map_err(|e| anyhow::anyhow!("invalid log filter `{}`: {e}", settings.log_filter))?;
    let fmt_layer = match settings.log_format {
        LogFormat::Json => tracing_subscriber::fmt::layer()
            .json()
            .flatten_event(true)
            .with_current_span(true)
            .with_span_list(false)
            .with_target(true)
            .boxed(),
        LogFormat::Pretty => tracing_subscriber::fmt::layer().with_target(true).boxed(),
    };

    let mut tracer_provider = None;
    let otel_layer = match &settings.otlp_endpoint {
        Some(endpoint) => {
            let exporter = opentelemetry_otlp::SpanExporter::builder()
                .with_http()
                .with_protocol(Protocol::HttpBinary)
                .with_endpoint(endpoint.as_str())
                .build()?;
            let provider = SdkTracerProvider::builder()
                .with_batch_exporter(exporter)
                .with_sampler(Sampler::ParentBased(Box::new(Sampler::TraceIdRatioBased(
                    settings.otlp_sample_ratio,
                ))))
                .with_resource(
                    Resource::builder()
                        .with_service_name(format!("{}-{component}", settings.service_name))
                        .build(),
                )
                .build();
            let tracer = provider.tracer("dz-bus-tracker");
            tracer_provider = Some(provider);
            Some(tracing_opentelemetry::layer().with_tracer(tracer))
        }
        None => None,
    };

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt_layer)
        .with(otel_layer)
        .try_init()
        .map_err(|e| anyhow::anyhow!("tracing already initialised: {e}"))?;
    Ok(TelemetryGuard { tracer_provider })
}

/// Installs the Prometheus recorder and returns the handle that renders `/metrics`.
pub fn install_metrics() -> anyhow::Result<PrometheusHandle> {
    let latency_buckets = [
        0.000_5, 0.001, 0.002_5, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    ];
    let handle = PrometheusBuilder::new()
        .set_buckets_for_metric(Matcher::Suffix("_seconds".to_owned()), &latency_buckets)?
        .install_recorder()?;
    Ok(handle)
}
