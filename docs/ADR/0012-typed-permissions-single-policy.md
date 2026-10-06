# 0012 — Typed permissions and a single authorization policy

* Status: accepted
* Date: 2026-10-05

## Context

Legacy permissions were scattered across view classes and serializers, with several
endpoints missing checks (BOLA/BFLA findings in `docs/PARITY_MATRIX.md` §9).

## Decision

* Roles: `admin`, `driver`, `passenger` for users; `service` for API keys.
* A closed `Permission` enum (`user:read`, `user:manage`, `api_key:manage`, `audit_log:read`,
  `catalog:read`, `tracking:publish`, …) and **one** mapping `role_permissions(role)` in
  `crates/domain/src/authz.rs`. API keys hold explicit scopes, limited to the subset marked
  `grantable_to_service`.
* Coarse checks at the edge: `RequirePermission<perm::X>` extractors in handler signatures.
* Fine checks in use cases: `Policy::authorize(actor, &Action)` with resource context
  (ownership, self-management rules). Deny by default.
* Administrative mutations append to an immutable `audit_log` in the same transaction.
* Table-driven tests: policy unit tests and an HTTP role × endpoint matrix.

## Consequences

* Adding an endpoint means choosing a permission explicitly; forgetting is a compile error
  for the extractor or a failing matrix test.
* The permission list is part of the API-key contract (scopes).

## Alternatives considered

* **Policy engine (Cedar, OPA)** — powerful, but an extra moving part for a small, static
  role model; can be adopted later behind `Policy::authorize`.
