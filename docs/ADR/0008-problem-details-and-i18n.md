# 0008 — RFC 9457 problem details with stable codes, localized in fr/ar/en

* Status: accepted
* Date: 2026-10-05

## Context

Legacy errors had several shapes (`detail`, `error`, field dictionaries, HTML 500 pages) and
were partially translated.

## Decision

* Every error — including 404/405 from the router, extractor rejections, timeouts, panics and
  nginx-generated 429/5xx — is an `application/problem+json` document:
  `type` (`urn:dzbus:problem:<code>`), `title`, `status`, `detail`, `instance` (path),
  `code` (stable snake_case machine code), `request_id`, and for validation errors an `errors`
  array of `{field, code, message, params}`.
* Handlers return typed errors; one outermost middleware renders them, so `instance`,
  `request_id` and the language are added consistently.
* Language: `Accept-Language` (fr, ar, en; default **fr**), and `Content-Language` is set.
  Clients may also localize from `code` and `params` themselves.
* `500` responses never contain internal details; the cause is logged with the request id.

## Consequences

* Clients branch on `code`, never on text. New codes are additive.
* Adding a language means adding one column of texts in `crates/api/src/i18n.rs`.

## Alternatives considered

* **Custom error envelope** — reinvents a standard that tooling already understands.
