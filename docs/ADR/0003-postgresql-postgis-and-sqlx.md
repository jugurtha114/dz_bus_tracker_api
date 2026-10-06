# 0003 — PostgreSQL 18 + PostGIS with sqlx compile-time checked queries

* Status: accepted
* Date: 2026-10-05

## Context

The domain is geospatial (stops, routes, live positions) and relational (lines, schedules,
trips, users). The legacy code computed distances in Python and enforced invariants in
services that some endpoints bypassed.

## Decision

* PostgreSQL 18 (native `uuidv7()`) with PostGIS 3.6; `geography(Point, 4326)` and
  `geography(LineString, 4326)` with GiST indexes, distances in metres in SQL.
* **Invariants live in the schema**: check constraints, a GiST exclusion constraint against
  overlapping active schedules, a deferrable unique constraint so stops can be re-ordered in
  one transaction, an append-only audit log enforced by triggers.
* **sqlx** with `query!`/`query_as!` macros: every query is type-checked against the real
  schema at compile time. The metadata is committed in `.sqlx/` so builds (CI, image) need no
  database (`SQLX_OFFLINE=true`); CI checks it is current (`cargo sqlx prepare --check`).
* Migrations are plain SQL in `migrations/`, applied by `dz-cli migrate` (a one-shot job in
  compose), never implicitly by several replicas at once in production. `/health/ready`
  fails while the schema is behind the binary.
* Pool connections set `statement_timeout` and `idle_in_transaction_session_timeout`.

## Consequences

* SQL is explicit and reviewable; no ORM-generated N+1 queries.
* Schema changes require regenerating `.sqlx/` (one command).
* Migrations are forward-only; destructive changes are done in expand/contract steps.

## Alternatives considered

* **SeaORM / Diesel** — more abstraction, weaker PostGIS support, less control over SQL.
* **Runtime-only queries** — loses compile-time checking.
