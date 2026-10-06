# 0007 — Argon2id password hashing with transparent migration of Django hashes

* Status: accepted
* Date: 2026-10-05

## Context

Legacy users have Django hashes (`pbkdf2_sha256$…`, possibly `pbkdf2_sha1$` or
`argon2$argon2…`). Users must keep their passwords after the migration (ADR 0002), and new
hashes should follow current guidance.

## Decision

* New hashes: **Argon2id** PHC strings, m = 19 MiB, t = 2, p = 1 (OWASP baseline; production
  refuses lower memory), computed on the blocking pool behind a semaphore so hashing cannot
  starve the async runtime or be used to exhaust memory.
* Verification accepts Argon2 PHC strings, Django's `argon2$argon2…` wrapper and Django
  PBKDF2 (`pbkdf2_sha256`, `pbkdf2_sha1`) with constant-time comparison; known-answer vectors
  from Python's `hashlib` are in the tests.
* After a successful login with a legacy or outdated hash, the password is re-hashed with the
  current parameters in the same update that records the login.
* Unknown accounts still cost one Argon2 verification (dummy hash), so timing does not reveal
  whether an e-mail is registered.

## Consequences

* The import (M7) copies hashes verbatim; nobody needs a password reset.
* Legacy hash formats disappear gradually; a report of remaining legacy hashes can decide
  when to force resets for dormant accounts.

## Alternatives considered

* **bcrypt** — 72-byte input limit, weaker memory hardness.
* **Force a reset for all users** — poor experience and a phishing opportunity.
