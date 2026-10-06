# 0005 — Durable jobs and cron on PostgreSQL

* Status: accepted
* Date: 2026-10-05

## Context

Celery handled e-mails, notifications, clean-ups and periodic tasks, with at-most-once
semantics in practice and duplicate periodic runs when several beat processes ran.
Requirements: durable, idempotent, multi-replica safe, observable, no extra broker.

## Decision

* A `jobs` table is the queue. Workers claim batches with
  `UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED)` and hold a **lease**
  (`locked_until`); a crashed worker's jobs are re-queued when the lease expires.
* `NOTIFY dz_jobs` from an insert trigger wakes idle workers; polling is the fallback.
* Failures retry with exponential backoff and jitter, then are **dead-lettered**
  (`status = 'failed'`, `last_error` kept) — inspectable with SQL.
* De-duplication: a partial unique index on `dedup_key` for queued/running jobs.
* Enqueueing happens in the same database as the business change, so a job can be made
  transactional with it.
* **Cron**: every worker computes the schedule (`croner`, seconds field required); each
  `(name, slot)` is claimed with an `INSERT … ON CONFLICT DO NOTHING` into `cron_runs`, so with
  N replicas each slot is enqueued exactly once — no leader election needed.
* The `dz-worker` binary runs both; any number of replicas is safe.

## Consequences

* No broker to operate; jobs are backed up with the database.
* Throughput is bounded by PostgreSQL (thousands of jobs/s with SKIP LOCKED), far above the
  workload (e-mails, notifications, purges). High-rate streams (GPS positions) do not go
  through this queue.
* Handlers must be idempotent (at-least-once delivery).

## Alternatives considered

* **Valkey streams** — fast, but durability depends on AOF settings and the data is separate
  from the transactional database.
* **apalis** — capable, but its PostgreSQL backend was still a release candidate when this
  was decided; the queue here is ~400 lines and fully under our control.
