# 0013 — Distroless image, compose for Docker and Podman, nginx at the edge

* Status: accepted
* Date: 2026-10-05

## Context

The service runs on Linux hosts with Docker or rootless Podman. TLS and HTTP/3 terminate at
nginx; the application speaks plain HTTP/1.1 (and h2c) on a private network.

## Decision

* One image with three binaries (`dz-api` default, `dz-worker`, `dz-cli`), built with
  cargo-chef and offline sqlx metadata, on `gcr.io/distroless/cc-debian13:nonroot`; no shell,
  so the health check is a subcommand (`dz-api healthcheck`).
* `compose.yaml` is the reference deployment: migrate (one-shot) → api + worker; PostGIS and
  Valkey on an internal network; only nginx publishes ports; read-only root file systems,
  dropped capabilities, resource limits; secrets as files.
* nginx (unprivileged image) re-resolves the API through the container DNS, so restarts and
  `--scale api=N` need no reload; it overwrites `X-Forwarded-For` and the API trusts it only
  from nginx's subnet.
* Compression (br, zstd, gzip) is negotiated by the API; nginx passes encoded bodies through.
* Images are pinned by digest; versions are listed in `docs/VERSIONS.md`.

## Consequences

* The same artefacts run locally, in CI and in production.
* Kubernetes can reuse the image and health endpoints as is (`/health/live`,
  `/health/ready`, metrics on a separate port).

## Alternatives considered

* **Alpine/musl static binaries** — smaller, but musl's allocator hurts multi-threaded
  throughput; glibc distroless is ~26 MB anyway.
* **TLS in the application (rustls)** — possible, but nginx already handles certificates,
  HTTP/3 and edge rate limits in one place.
