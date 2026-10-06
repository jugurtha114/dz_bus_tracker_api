# 0010 — Opaque keyset cursors for pagination

* Status: accepted
* Date: 2026-10-05

## Context

Legacy lists used page numbers with `COUNT(*)` and `OFFSET`: slow on large tables and
unstable when rows are inserted between pages.

## Decision

* Lists are ordered by `(created_at DESC, id DESC)` (ids are UUIDv7, so ties are ordered too)
  and paginated with **keyset** conditions on that pair, backed by matching indexes.
* The client sees `?limit=` (1–100, default 20) and an opaque `?cursor=`; responses are
  `{ "items": [...], "next_cursor": "…" | null }`. The cursor is base64url JSON of the last
  position; tampered cursors are a `422`.
* No total counts by default; endpoints that need one get a dedicated, cached count.
* Filters are allow-listed per endpoint; unknown query parameters are rejected.

## Consequences

* Constant cost per page regardless of depth; no skipped or repeated items under inserts.
* No "jump to page N" — acceptable for feeds and admin lists, which filter instead.

## Alternatives considered

* **Offset pagination** — simple, but slow and unstable.
