# syntax=docker/dockerfile:1
#
# DZ Bus Tracker backend image: dz-api (default entrypoint), dz-worker and dz-cli.
#
#   docker build -f Containerfile -t dz-bus-tracker:dev .
#   podman build -f Containerfile -t dz-bus-tracker:dev .
#
# * Dependencies are compiled in their own layer (cargo-chef), so source edits rebuild only
#   the workspace crates.
# * Queries are checked against the committed `.sqlx/` metadata: no database at build time.
# * Runtime: distroless (glibc + libgcc, CA certificates, no shell, no package manager),
#   running as the unprivileged `nonroot` user (65532). Works with a read-only root fs.
# * Base images are pinned by digest; see docs/VERSIONS.md for the update procedure.

ARG RUST_VERSION=1.99.0
ARG CARGO_CHEF_VERSION=0.1.78

FROM docker.io/library/rust:1.99.0-slim-trixie@sha256:24e632c09342c20abf8312cf4f61430a911c01ed3a5e4c02b87292b1c39c5273 AS chef
ARG RUST_VERSION
ARG CARGO_CHEF_VERSION
# Use the image's toolchain (the same release rust-toolchain.toml pins) instead of letting
# rustup download the extra components listed there.
ENV RUSTUP_TOOLCHAIN=${RUST_VERSION} \
    CARGO_TERM_COLOR=never \
    CARGO_INCREMENTAL=0
RUN cargo install cargo-chef --version "${CARGO_CHEF_VERSION}" --locked
WORKDIR /src

FROM chef AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS builder
COPY --from=planner /src/recipe.json recipe.json
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    cargo chef cook --release --locked --recipe-path recipe.json \
        --package dz-api --package dz-worker --package dz-cli
COPY . .
ENV SQLX_OFFLINE=true
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    cargo build --release --locked --package dz-api --package dz-worker --package dz-cli \
    && mkdir -p /out \
    && cp target/release/dz-api target/release/dz-worker target/release/dz-cli /out/

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:e792ab3d241a468a4fd7519ddbbebe66b49b5f365771716ea688ad40b6c6f1c2 AS runtime
LABEL org.opencontainers.image.title="dz-bus-tracker" \
      org.opencontainers.image.description="DZ Bus Tracker API, worker and operator CLI" \
      org.opencontainers.image.source="https://github.com/jugurtha114/dz_bus_tracker_api" \
      org.opencontainers.image.licenses="Proprietary"
COPY --from=builder /out/ /usr/local/bin/
USER 65532:65532
ENV DZ_HTTP__ADDR=0.0.0.0:8080 \
    DZ_HTTP__METRICS_ADDR=0.0.0.0:9090
EXPOSE 8080 9090
# Docker honours this; Podman keeps it with `--format docker`, and compose.yaml repeats it.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["/usr/local/bin/dz-api", "healthcheck"]
ENTRYPOINT ["/usr/local/bin/dz-api"]
CMD ["serve"]
