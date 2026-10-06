# 0001 — Record architecture decisions; a new Rust service with a hexagonal workspace

* Status: accepted
* Date: 2026-10-05

## Context

The DZ Bus Tracker backend is a Django 5.2 + DRF + Channels + Celery application. Its audit
(`docs/PARITY_MATRIX.md` §9) lists 63 defects, several of them security-relevant, and the
product owner asked for a complete redesign in Rust instead of a line-by-line port.
Decisions that are expensive to reverse need a durable, reviewable record.

## Decision

* Architecture decisions are recorded here as numbered ADRs (context, decision,
  consequences, alternatives). Superseded ADRs stay, marked as such.
* The new backend is a **modular monolith** in one Cargo workspace at the repository root,
  next to the legacy code (which is removed once the Rust service replaces it):

  | Crate | Role |
  |---|---|
  | `crates/domain` (`dz-domain`) | Entities, value objects, validation, the authorization policy. No I/O, no async. |
  | `crates/config` (`dz-config`) | Typed settings from the environment and secret files, fail-fast validation. |
  | `crates/app` (`dz-app`) | Use cases and the **ports** (traits) they need: repositories, hasher, tokens, queue, mailer, limiter. |
  | `crates/infra` (`dz-infra`) | **Adapters**: PostgreSQL (sqlx), Valkey (fred), Argon2, JWT, SMTP, job queue, telemetry; the composition root. |
  | `crates/api` (`dz-http`) | HTTP edge: axum routes, extractors, middleware, DTOs, OpenAPI, problem documents. |
  | `crates/testkit` | Test support over real PostgreSQL/Valkey. |
  | `bin/dz-api`, `bin/dz-worker`, `bin/dz-cli` | Thin binaries. |

* Dependencies point inwards only: `api → app → domain`, `infra → app → domain`; `app` never
  depends on `infra`, and `api` never on `infra` (the binaries wire them together).
* Shared state is one `Arc` (`AppState`); there is no global mutable state.

## Consequences

* Use cases are unit-tested with in-memory fakes (`dz_app::testing`) in milliseconds; adapters
  are tested against real services in `crates/testkit`.
* A future split into services (e.g. real-time tracking) can follow crate boundaries.
* Ports cost a little indirection (`Arc<dyn Trait>`); the hot paths are I/O-bound, so dynamic
  dispatch is irrelevant.

## Alternatives considered

* **Port the Django structure 1:1** — would carry the legacy defects and the per-app coupling
  over; rejected by the product owner.
* **Microservices from day one** — operational cost without a scaling need yet.
* **Separate repository** — kept in this repository on a new branch so history, issues and the
  legacy reference stay together.
