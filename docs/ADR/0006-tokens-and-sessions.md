# 0006 — EdDSA access tokens, rotating refresh tokens, revocable sessions

* Status: accepted
* Date: 2026-10-05

## Context

The legacy API used long-lived HS256 JWTs (shared secret), accepted refresh tokens where
access tokens were expected, put tokens in WebSocket URLs, and could not revoke a stolen
token before it expired.

## Decision

* **Session** = a refresh-token family (`auth_sessions`), created at login/registration, with
  a sliding refresh lifetime (14 d) and an absolute lifetime (60 d).
* **Access token**: JWT signed with **Ed25519 (EdDSA)**, 15 minutes, claims `sub`, `sid`
  (session), `role`, `lang`, `iss`, `aud`, `iat`, `exp`, `jti`. The header carries a `kid`; all
  keys in the key directory verify, only the active one signs; public keys are published at
  `/.well-known/jwks.json`. Rotation: add a key, switch `DZ_AUTH__ACTIVE_KEY_ID`, remove the
  old key after one access-token lifetime.
* **Refresh token**: opaque 256-bit random (`dzr_…`), stored as SHA-256, **rotated on every
  use** inside a transaction that locks the token and its session. Presenting an already
  rotated token is treated as theft: the whole session is revoked (`refresh_token_reused`).
* **Immediate revocation**: logout, logout-all, password change/reset, deactivation and role
  changes revoke sessions in PostgreSQL and write a Valkey marker `revoked:sid:<id>` that lives
  as long as an access token can. Every authenticated request checks the marker; if Valkey is
  unreachable the request is rejected (fail-closed, configurable).
* **API keys** for machines (`dzk_<id>_<secret>`, `X-Api-Key`) are separate from user tokens:
  hashed, scoped, expirable, revocable.

## Consequences

* Verification needs only public keys; other services can verify tokens with the JWKS.
* One Valkey `EXISTS` per authenticated request — sub-millisecond, and the price of real
  revocation.
* Role changes take effect immediately because affected sessions are revoked (tokens carry the
  role).

## Alternatives considered

* **Opaque access tokens only** — a database/Valkey lookup per request anyway, no offline
  verification for future services.
* **HS256** — every verifier holds the signing secret.
* **ES256** — equally valid; Ed25519 is deterministic, faster and has no nonce pitfalls.
* **PASETO** — fewer footguns, but weaker client tooling for the planned JS/React Native apps.
