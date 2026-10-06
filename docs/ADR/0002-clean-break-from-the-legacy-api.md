# 0002 — Clean break from the legacy API contract

* Status: accepted
* Date: 2026-10-05

## Context

The legacy API mixes conventions (trailing slashes, page-number pagination, ad-hoc error
shapes, camelCase and snake_case), exposes dead and duplicated endpoints, and its WebSocket
protocol leaks tokens in URLs. Only a Flutter client consumed it; the new clients (Next.js,
React Native) are not written yet. The product owner decided not to keep compatibility.

## Decision

* The legacy implementation is a **capability inventory, not a contract**
  (`docs/PARITY_MATRIX.md`): every capability is kept, redesigned or dropped with a reason.
* The new contract is `/api/v1`, documented by OpenAPI 3.1 generated from code:
  snake_case JSON, UUIDv7 ids, RFC 3339 UTC timestamps, cursor pagination, RFC 9457 errors,
  `Idempotency-Key` on creating POSTs, ETags on reads.
* Data is migrated, not the API: `dz-cli import-from-django` (milestone M7) imports users
  (keeping their password hashes, see ADR 0007), the network and history.

## Consequences

* No shims for legacy quirks; each defect is fixed at its root.
* Clients must be built against the new OpenAPI document (`docs/openapi.json`).
* Cut-over is a planned migration window with the import tool, not a gradual proxy.

## Alternatives considered

* **Compatibility layer for the Flutter app** — would freeze the worst parts of the old
  design; declined by the product owner.
