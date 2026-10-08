# Parity matrix: Django → Rust

This document maps every model, HTTP endpoint, WebSocket message, Celery task, cache key, setting
and management command of the legacy Django service (branch `main`, commit `5ab9afc`) to its
equivalent in the Rust service. Each row is marked:

| Mark | Meaning |
|---|---|
| **Keep** | Same behaviour, new contract conventions only (paths, pagination, error format). |
| **Redesign** | The capability stays, but the rules or the mechanism change. The reason is given. |
| **Drop** | Not ported. The reason is given. Nothing is dropped silently. |

The milestone (M1–M7) says when the Rust equivalent lands. Legacy defects are referenced as
`L-nn` and listed in [section 9](#9-legacy-defects-and-the-rust-fix) with the proposed fix.

**How to read this document.** The legacy code is a *capability inventory*, not a contract. It
says what the product must be able to do. It does not prescribe how: data model, API shape, real-time
protocol, job design and business rules are redesigned freely following current best practices.
No compatibility with the Django API, its WebSocket messages or the existing Flutter client is
kept. Nothing below adds a product feature that does not exist in Django, except where security or
correctness requires it (marked *fix*).

---

## 0. Contract conventions (apply to every row)

The Rust API is a new, versioned contract (`/api/v1`) for the upcoming Next.js and React Native
clients and third-party integrators (see ADR-0002). Compared with Django/DRF:

| Concern | Django | Rust |
|---|---|---|
| Paths | `/api/v1/<app>/<resource>/<action_name>/` with trailing slash and underscores | `/api/v1/<resource>[/{id}[/<action>]]`, no trailing slash, kebab-case segments, nested ownership (`/me/...`) |
| IDs | UUIDv4 | UUIDv7 for new rows; imported UUIDv4 kept unchanged |
| JSON | mixed | snake_case everywhere, RFC 3339 UTC timestamps, coordinates as `{lat, lng}` or GeoJSON |
| Pagination | page/page_size envelope `{count,next,previous,total_pages,current_page,results}` | cursor: `?cursor=&limit=` (default 20, max 100) → `{items, next_cursor}` |
| Filtering / sorting | ad hoc, partly broken (L-41) | explicit allow-list per endpoint, typed and validated (bad input → 422, never 500) |
| Errors | `{"detail"}`, `{"error"}`, `{"message"}`, field dicts; not-found often 400 | RFC 9457 `application/problem+json` with stable `code`, field `errors[]`, localized (fr/ar/en) |
| Updates | PATCH returns a field subset (L-44) | PATCH returns the full resource |
| Writes that create | none | `Idempotency-Key` honoured |
| Caching | none | `ETag` / `If-None-Match` on cacheable GETs |
| Auth | HS256 JWT from `SECRET_KEY`, 30 min / 7 d, no rotation | EdDSA JWT with `kid` rotation (15 min) + rotating opaque refresh tokens with reuse detection (ADR-0004) |
| Throttling | DRF per process cache, spoofable IP (L-12) | Valkey GCRA shared across replicas, trusted-proxy IP extraction (ADR-0007) |
| Side effects | inside the DB transaction, before commit (L-08) | after commit: transactional outbox / job queue, then fan-out |

---

## 1. Data model

| Django model (app) | Rust table(s) | Mark | M | Notes |
|---|---|---|---|---|
| `accounts.User` | `users` | Redesign | M1 | `user_type` + `is_staff` + `is_superuser` → single `role` (`admin`/`driver`/`passenger`); `role` is never client-writable (L-01). Email stored lower-cased and unique (L-35). Phone stored as E.164. Adds `failed_login_attempts`, `locked_until`, `last_login_at`, `password_changed_at`, `email_verified_at`. `password_hash` keeps Django PBKDF2 hashes until next login (ADR-0005). |
| `accounts.Profile` | `profiles` (PK = `user_id`) | Keep | M1 | Created in the same transaction as the user (no signal, no lazy creation race L-63). `avatar` file → `avatar_key` (private object storage; set with `PUT /api/v1/me/avatar` from an upload, M2). |
| `core.Address` | — | Drop | — | Never referenced outside its own module. |
| simplejwt `OutstandingToken` / `BlacklistedToken` | `auth_sessions`, `refresh_tokens` | Redesign | M1 | Session = refresh-token family; tokens stored as SHA-256 hashes; rotation with reuse detection; purge job (L-60). |
| — | `password_reset_tokens` | *fix* | M1 | Django derived stateless HMAC tokens from `SECRET_KEY` and never sent them (L-30). Random single-use tokens, hashed, 1 h TTL. |
| — | `api_keys` | New (spec §4) | M1 | `service` role for machine-to-machine access, hashed, scoped, revocable. |
| — (Django `ImageField`/`FileField` uploads through the API) | `uploads` | *fix* | M2 | Files go straight to the private bucket through presigned `PUT`s whose type and size are signed; the row records the server-generated key (`<purpose>/<owner>/<id>`), owner, purpose, declared type/size and expiry, and is claimed once by the resource that attaches it (L-03). |
| — | `audit_log` | New (spec §4) | M1 | Append-only (trigger-enforced) record of admin actions. |
| — | `jobs` | Redesign | M1 | Replaces Celery broker/results (ADR-0006). |
| `drivers.Driver` | `drivers` | Redesign | M1 schema / M2 logic | Explicit state machine (L-24); ID-card / licence photos become private object-storage keys (L-03); `rating`/`total_ratings` → `rating_sum`/`rating_count` maintained atomically (L-57). `is_active` folded into `status` (suspended). |
| `drivers.DriverRating` | `driver_ratings` | Keep | M4 | One rating per (driver, user, Algiers calendar day); eligibility rules fixed (L-26). |
| `drivers.DriverStatusLog` | `driver_status_log` | Keep | M2 | `changed_by` actually recorded (L-24); every transition logged incl. re-apply. |
| `buses.Bus` | `buses` | Redesign | M1 schema / M2 logic | `is_approved` → `approval_status` (`pending`/`approved`/`rejected`), operational `status` stays; drivers can no longer flip status/activation (L-05); `features` JSON → `text[]`; `photo` → `photo_key`. |
| `lines.Stop` | `stops` | Redesign | M1 | `latitude`/`longitude` decimals → `location geography(Point,4326)` + GiST index. |
| `lines.Line` | `lines` | Redesign | M1 | + `route geography(LineString,4326)` (replaces `RouteSegment`), color validated `#RRGGBB` (L-49). |
| `lines.LineStop` | `line_stops` | Redesign | M1 | `order` → `position`; `(line_id, position)` unique **deferrable** so re-ordering works (L-22). |
| `lines.Schedule` | `schedules` | Redesign | M1 | `end_time > start_time` and non-overlap enforced by the database (exclusion constraint) instead of a bypassable service check (L-23). `day_of_week` follows ISO 8601 (1 = Monday … 7 = Sunday); the importer adds 1 to legacy values. |
| `lines.ServiceDisruption` | `disruptions` | Keep | M2 | Adds `end_time >= start_time` check; fan-out to affected passengers, not only admins (L-32). |
| `tracking.BusLine` | `bus_line_assignments` | Redesign | M2 | Pure assignment (bus may serve line). Tracking state is derived from the active trip, removing the duplicated `tracking_status`/`trip_id` that drifted (L-21). Re-assigning a previously unassigned pair works (L-50). |
| `tracking.Trip` | `trips` | Redesign | M3 | Partial unique indexes guarantee at most one active trip per bus and per driver (race L-17). One finaliser computes stats (L-18). |
| `tracking.LocationUpdate` | `location_history` (partitioned by day) + live state in Valkey | Redesign | M3 | `geography(Point)`; batch insert; partition drop instead of row deletes; latest position served from Valkey. |
| `tracking.PassengerCount` | `passenger_counts` | Keep | M4 | Capacity enforced in the use-case for every entry point (L-48). |
| `tracking.WaitingPassengers` | — | Drop | — | Deprecated in Django (`X-Deprecated-API`), superseded by waiting reports. |
| `tracking.Anomaly` | `anomalies` | Keep | M3 | `location geography(Point)`; trip must belong to the bus (L-47). |
| `tracking.RouteSegment` | — (`lines.route` + `line_stops` segment metrics) | Redesign | M2 | Passenger-writable geometry (L-04); replaced by the admin-managed line route. |
| `tracking.BusWaitingList` | `waiting_list_entries` | Redesign | M4 | Re-join after leaving works (L-27); entries expire when the bus passes or after a timeout (L-62). |
| `tracking.WaitingCountReport` | `waiting_reports` | Redesign | M4 | Reporter GPS never exposed to others (L-07); verification guarded (L-28). |
| `tracking.ReputationScore` | `reputation` | Redesign | M4/M6 | Accuracy over *verified* reports with a minimum count (L-55). |
| `tracking.VirtualCurrency` | `wallets` | Redesign | M6 | Balance only changes through ledger postings applied atomically (L-15). |
| `tracking.CurrencyTransaction` | `ledger_entries` | Redesign | M6 | Double-entry style (user wallet ↔ system accounts), immutable. |
| `tracking.DriverPerformanceScore` | `driver_performance` | Redesign | M6 | Actually updated from trip end / verification / anomalies (L-56). |
| `tracking.PremiumFeature` / `UserPremiumFeature` | `premium_features` / `premium_entitlements` | Redesign | M6 | Eligibility enforced (L-58); renewal extends instead of failing (L-59). |
| `notifications.DeviceToken` | `device_tokens` | Redesign | M5 | Token globally unique, upsert re-assigns to the current user (L-37). |
| `notifications.Notification` | `notifications` | Keep | M5 | Type is a closed enum with a migration for legacy off-enum values (L-38). |
| `notifications.NotificationPreference` | `notification_preferences` (+ favourite stops/lines tables) | Keep | M5 | Quiet hours evaluated in the user's time zone (Africa/Algiers) on every channel (L-39). |
| `notifications.NotificationSchedule` | `jobs` (`run_at`) + `arrival_alerts` | Redesign | M5 | Claim-safe, retried with backoff, deduplicated (L-34). |
| `offline_mode.*` (5 models) | — | Redesign (ask before M6) | M6 | Server-side per-user cache copies and a no-op sync queue (L-40). Proposed: stateless ETag'd catalogue bundle + idempotent replay of queued actions through the normal endpoints. |
| `django_celery_beat` tables | — | Drop | — | Installed but unused. |
| Django admin registrations (30 models) | Admin REST endpoints | Redesign | M1–M6 | The admin UI moves to the upcoming Next.js client; every admin action is an audited API call. |

---

## 2. HTTP endpoints

### 2.1 Health, docs, tokens

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `ANY /health/` | `GET /health/live`, `GET /health/ready` | Redesign | M1 | Readiness checks Postgres, Valkey and migration status; liveness is dependency-free. `dz-api healthcheck` probes it from inside the container. |
| `GET /api/schema/`, `/api/schema/swagger-ui/`, `/api/schema/redoc/` | `GET /api/openapi.json`, `GET /api/docs` (Scalar) | Keep | M1 | OpenAPI 3.1 generated from code. |
| `POST /api/token/` | `POST /api/v1/auth/login` | Redesign | M1 | One login endpoint (L-36). Case-insensitive email, lockout, generic errors. |
| `POST /api/token/refresh/` | `POST /api/v1/auth/refresh` | Redesign | M1 | Rotation + reuse detection (Django did not rotate). |
| `POST /api/token/verify/` | `GET /.well-known/jwks.json` | Redesign | M1 | Third parties verify tokens locally with the published public keys instead of calling the API. |
| `/api/auth/login/`, `/api/docs/login/` (DRF session login) | — | Drop | — | Browsable-API session auth (and its CSRF surface) is not needed by API clients. |
| `ANY /api/v1/trips/history/` (redirect) | — | Drop | — | Alias of `GET /api/v1/trips`. |
| Router API roots (`GET /api/v1/<app>/`) | — | Drop | — | DRF browsable artefacts; the OpenAPI document replaces them. |
| `/admin/...` | Admin endpoints below | Redesign | M1–M6 | See §1. |

### 2.2 Accounts

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `POST /accounts/register/` | `POST /api/v1/auth/register` | Redesign | M1 | Always creates a passenger (L-01). Password policy enforced (L-29). Returns user + token pair. |
| `POST /accounts/users/` (AllowAny) | — | Drop | — | Duplicate of register without tokens (L-36). |
| `POST /accounts/login/` | `POST /api/v1/auth/login` | Redesign | M1 | See 2.1. |
| `POST /accounts/register-driver/`, `POST /drivers/register/` | `POST /api/v1/drivers/applications` | Redesign | M2 | One endpoint, atomic (L-31), validators applied, photos uploaded via presigned URLs (L-03). |
| `POST /drivers/drivers/register/` (410) | — | Drop | — | Already dead. |
| `GET /accounts/users/me/`, `GET /accounts/users/` (self) | `GET /api/v1/me` | Keep | M1 | |
| `PATCH /accounts/users/me/`, `PATCH /accounts/users/{id}/` (self) | `PATCH /api/v1/me` | Keep | M1 | `first_name`, `last_name`, `phone_number`. Unknown fields rejected. |
| `GET /accounts/users/` (staff), `GET /accounts/users/{id}/` | `GET /api/v1/admin/users`, `GET /api/v1/admin/users/{id}` | Keep | M1 | Admin only; filter by role/active/email prefix; cursor pagination. |
| `DELETE /accounts/users/{id}/` (hard delete, cascades) | `PATCH /api/v1/admin/users/{id}` `{is_active:false}` | Redesign | M1 | Deactivation instead of destructive cascade; sessions revoked; audited. Role changes also here (audited). |
| `POST /accounts/users/{id}/change_password/` | `POST /api/v1/auth/password/change` | Redesign | M1 | Revokes all other sessions (L-29). |
| `POST /accounts/users/reset_password_request/` | `POST /api/v1/auth/password/reset` | Redesign | M1 | Actually sends the e-mail (L-30) through the job queue; always 202; rate-limited. |
| `POST /accounts/users/reset_password_confirm/` | `POST /api/v1/auth/password/reset/confirm` | Redesign | M1 | `{token, new_password}`; single use; revokes all sessions. |
| `POST /accounts/users/logout/` | `POST /api/v1/auth/logout` | Redesign | M1 | Revokes the session immediately, including its access tokens (Django left them valid). |
| — | `GET /api/v1/auth/sessions`, `DELETE /api/v1/auth/sessions/{id}` | *fix* | M1 | Lets a user see and revoke sessions on lost devices (needed to make revocation usable). |
| `GET /accounts/profile/`, `GET /accounts/profiles/me/`, `GET /accounts/profiles/` (self) | `GET /api/v1/me/profile` | Keep | M1 | Duplicates collapsed. |
| `PATCH /accounts/profiles/update_me/`, `PATCH /accounts/profiles/{id}/`, `PATCH /accounts/profiles/update_notification_preferences/` | `PATCH /api/v1/me/profile` | Keep | M1 | `bio`, `language`, the three channel flags. The avatar file is no longer a multipart field: `POST /api/v1/uploads` (purpose `avatar`) → presigned `PUT` to storage → `PUT /api/v1/me/avatar {upload_id}`; `DELETE /api/v1/me/avatar` removes it; profiles carry a presigned `avatar_url` (M2). |
| `POST /accounts/profiles/` (broken, 500) | — | Drop | — | Profiles are created with the user (L-46). |
| `DELETE /accounts/profiles/{id}/` | — | Drop | — | A profile cannot exist without its user. |
| — | `GET/POST /api/v1/admin/api-keys`, `DELETE /api/v1/admin/api-keys/{id}` | New (spec §4) | M1 | Service-role keys; audited. |
| — | `GET /api/v1/admin/audit-log` | New (spec §4) | M1 | |

### 2.3 Drivers

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /drivers/drivers/` (any user, full PII) | `GET /api/v1/drivers` | Redesign | M2 | Admin only (L-03). Public views of drivers expose name + rating only. |
| `POST /drivers/drivers/` (any user id) | `POST /api/v1/drivers/applications` | Redesign | M2 | A driver profile is always created for the caller (L-02). |
| `GET /drivers/drivers/{id}/` | `GET /api/v1/drivers/{id}` | Redesign | M2 | Admin or the driver themself. |
| `GET /drivers/drivers/profile/` | `GET /api/v1/drivers/me` | Keep | M2 | |
| `PATCH /drivers/drivers/{id}/` (any driver!) | `PATCH /api/v1/drivers/me` | Redesign | M2 | Own profile only (L-02); documents re-upload sends the application back to review. |
| `DELETE /drivers/drivers/{id}/` (any driver, cascades) | — | Drop | — | Replaced by suspension; history must not be destroyed (L-02). |
| `POST /drivers/drivers/{id}/approve/` | `POST /api/v1/drivers/{id}/approve` | Redesign | M2 | Only from `pending`; the ignored `approve:false` flag is removed (L-24). Audited, notifies driver. |
| `POST /drivers/drivers/{id}/reject/` | `POST /api/v1/drivers/{id}/reject` | Redesign | M2 | `{reason}` required; from `pending`. |
| `POST /drivers/drivers/{id}/suspend/` | `POST /api/v1/drivers/{id}/suspend` | Redesign | M2 | From `approved`; ends active trip, takes buses off duty (L-25). |
| — (approve was the only way back) | `POST /api/v1/drivers/{id}/reinstate` | *fix* | M2 | Explicit `suspended → approved` transition instead of overloading approve. |
| `POST /drivers/drivers/{id}/reapply/` | `POST /api/v1/drivers/me/reapply` | Redesign | M2 | `rejected → pending`; logged; admins notified (L-24). |
| `GET /drivers/drivers/{id}/status_history/` | `GET /api/v1/drivers/{id}/status-history` | Keep | M2 | With `changed_by`. |
| `POST /drivers/drivers/{id}/update_availability/` | `PUT /api/v1/drivers/me/availability` | Keep | M2 | |
| `GET /drivers/drivers/{id}/ratings/` | `GET /api/v1/drivers/{id}/ratings` | Keep | M4 | Rater identity reduced to first name (privacy). |
| `POST /drivers/drivers/{id}/ratings/` | `POST /api/v1/drivers/{id}/ratings` | Redesign | M4 | Eligibility: same trip interaction within 48 h, not self, once per day (L-26). |

### 2.4 Buses

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /buses/buses/` | `GET /api/v1/buses` | Keep | M2 | Drivers see their own; admin all; public sees approved active buses without driver PII. |
| `POST /buses/buses/` (any driver id) | `POST /api/v1/buses` | Redesign | M2 | Driver registers a bus for themself only (L-05); starts `pending` approval. |
| `GET /buses/buses/{id}/` | `GET /api/v1/buses/{id}` | Keep | M2 | |
| `PATCH /buses/buses/{id}/` | `PATCH /api/v1/buses/{id}` | Redesign | M2 | Owner may edit descriptive fields; `status`/activation admin-only (L-05). |
| `DELETE /buses/buses/{id}/` | `DELETE /api/v1/buses/{id}` | Redesign | M2 | Only when the bus has no trips; otherwise deactivate. |
| `POST /buses/buses/{id}/approve/` | `POST /api/v1/buses/{id}/approve`, `.../reject` | Redesign | M2 | Two explicit actions; reason stored (L-45). |
| `POST /buses/buses/{id}/activate/`, `/deactivate/` | `POST /api/v1/buses/{id}/activate`, `.../deactivate` | Keep | M2 | Deactivation ends an active trip. |
| `POST /buses/buses/{id}/start_tracking/` | `POST /api/v1/trips` | Redesign | M3 | One trip-start path (L-36, L-21). |
| `POST /buses/buses/{id}/stop_tracking/` (no-op) | `POST /api/v1/trips/{id}/end` | Redesign | M3 | |
| `POST /buses/buses/{id}/update_location/` | `POST /api/v1/tracking/locations` | Redesign | M3 | One ingest path (L-36). |
| `POST /buses/buses/{id}/update_passenger_count/` | `POST /api/v1/trips/{id}/passenger-counts` | Redesign | M4 | Capacity check always applied (L-48). |
| `GET /buses/locations/`, `GET /buses/locations/{id}/` | `GET /api/v1/buses/{id}/positions` | Redesign | M3 | Duplicate of tracking/locations; history is admin/owner only. |

### 2.5 Lines, stops, schedules, disruptions

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /lines/stops/` | `GET /api/v1/stops` | Keep | M2 | Public catalogue read (consistent public access, L-53), active stops only; `stop:write` holders also see inactive ones. Filters: `q` (trigram `ILIKE`), `wilaya`, `commune`, `line_id`, `is_active` (writers only: `401`/`403` otherwise). Cursor pagination. |
| `POST /lines/stops/` | `POST /api/v1/stops` | Keep | M2 | Admin; lat/lng range validated (L-49). |
| `GET/PATCH/DELETE /lines/stops/{id}/` | `GET/PATCH/DELETE /api/v1/stops/{id}` | Keep | M2 | Delete refused while used by a line (`409 stop_in_use`). Moving a stop recomputes the distances of its lines. |
| `lines.Stop.photo` (multipart field) | `PUT/DELETE /api/v1/stops/{id}/photo` `{upload_id}` | Redesign | M2 | Presigned upload (purpose `stop_photo`), private bucket, `photo_url` presigned GET; replaced/removed photos deleted through the outbox. API keys may remove but not attach (uploads belong to a human account). |
| `GET /lines/stops/{id}/lines/` | `GET /api/v1/stops/{id}/lines` | Keep | M2 | |
| `GET /lines/stops/nearby/` (Python scan) | `GET /api/v1/stops/nearby?lat=&lng=&radius_m=` | Redesign | M2 | PostGIS `ST_DWithin` + KNN `<->`; returns metres. |
| `GET /lines/lines/` | `GET /api/v1/lines` | Keep | M2 | |
| `GET /lines/lines/search/` | `GET /api/v1/lines?q=` | Redesign | M2 | Folded into the list (trigram search). |
| `POST /lines/lines/`, `GET/PATCH/DELETE /lines/lines/{id}/` | same under `/api/v1/lines` | Keep | M2 | `code` immutable as before. |
| `POST /lines/lines/{id}/activate/`, `/deactivate/` | `PATCH /api/v1/lines/{id}` `{is_active}` | Redesign | M2 | No separate verbs needed. |
| `GET /lines/lines/{id}/stops/` | `GET /api/v1/lines/{id}/stops` | Keep | M2 | Ordered by position (L-51). |
| `POST /lines/lines/{id}/add_stop/`, `/remove_stop/`, `/update_stop_order/` | `PUT /api/v1/lines/{id}/stops` (whole ordered list), `POST /api/v1/lines/{id}/stops`, `DELETE /api/v1/lines/{id}/stops/{stop_id}` | Redesign | M2 | Re-ordering is atomic and actually works (L-22): writes to a line are serialised by a lock on the line row, positions are 0-based and contiguous (`line_stops_position_key` deferred to the commit). `distance_from_previous_m` is computed with `ST_Distance`. `POST` answers `201` with the whole new list; the stop after an insertion loses its (now unknown) segment time, a removal merges the two segment times. |
| `GET /lines/lines/{id}/schedules/`, `POST /lines/lines/{id}/add_schedule/` | `GET/POST /api/v1/lines/{id}/schedules` | Keep | M2 | |
| `GET/POST /lines/schedules/`, `GET/PATCH/DELETE /lines/schedules/{id}/` | `GET/PATCH/DELETE /api/v1/schedules/{id}` | Redesign | M2 | Creation only under the line; validation can no longer be bypassed (L-23). |
| `GET /lines/lines/journey/` | `GET /api/v1/journeys?from_stop_id=&to_stop_id=` | Redesign | M2 | Skips inactive lines/stops, considers transfers correctly, ETA covers both legs (L-52). |
| `GET/POST /lines/disruptions/`, `GET/PATCH/DELETE /lines/disruptions/{id}/` | `GET/POST /api/v1/disruptions`, `GET/PATCH/DELETE /api/v1/disruptions/{id}` | Keep | M2 | Fan-out after commit to affected passengers + WS `line:{id}` (L-32). |
| — | `GET/PUT/DELETE /api/v1/lines/{id}/route` | Redesign | M2 | Admin sets the line geometry as a GeoJSON `LineString` (2–10 000 positions; replaces route segments). |

### 2.6 Tracking

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /tracking/active-buses/` (AllowAny, `expand_driver` leaks PII) | `GET /api/v1/tracking/active-buses` (GeoJSON FeatureCollection) | Redesign | M3 | Public, no PII ever (L-03); Valkey first, PostGIS fallback, single-flight. `?line_id=` kept. |
| `GET /tracking/bus-lines/`, `POST /tracking/bus-lines/`, `GET/PATCH/DELETE /tracking/bus-lines/{id}/` | `GET/PUT/DELETE /api/v1/buses/{id}/lines/{line_id}` | Redesign | M2 | Assignment only (admin). |
| `POST /tracking/bus-lines/start_tracking/`, `POST /tracking/trips/` | `POST /api/v1/trips` | Redesign | M3 | Approved driver, own approved active bus assigned to the line; no concurrent trip (DB-enforced) (L-06, L-17). |
| `POST /tracking/bus-lines/stop_tracking/`, `POST /tracking/trips/{id}/end/` | `POST /api/v1/trips/{id}/end` | Redesign | M3 | Idempotent; one stats finaliser (L-18); emits `trip_update`. |
| `GET /tracking/trips/`, `GET /tracking/trips/history/` | `GET /api/v1/trips` | Redesign | M3 | Scoped: admin all, driver own; passengers do not list trips (L-54). |
| `GET /tracking/trips/{id}/` | `GET /api/v1/trips/{id}` | Keep | M3 | |
| `PATCH /tracking/trips/{id}/` (any driver) | `PATCH /api/v1/trips/{id}` | Redesign | M3 | Own trip, `notes` only (L-06). |
| `DELETE /tracking/trips/{id}/` | — | Drop | — | Trips are history; admins correct data through notes/anomalies. |
| `GET /tracking/trips/{id}/statistics/` | `GET /api/v1/trips/{id}/statistics` | Keep | M3 | |
| `GET /tracking/locations/`, `GET /tracking/locations/{id}/` | `GET /api/v1/buses/{id}/positions?from=&to=` | Redesign | M3 | Owner/admin; time-bounded (partitioned table). |
| `POST /tracking/locations/` | `POST /api/v1/tracking/locations` (+ WS ingress) | Redesign | M3 | Accepts a batch of fixes with client timestamps; validates ranges, speed and jumps (L-49); 100/min tier (L-13). |
| `PATCH/DELETE /tracking/locations/{id}/` (any driver) | — | Drop | — | GPS history is immutable (L-06). |
| `POST /tracking/locations/estimate_arrival/` | `GET /api/v1/stops/{id}/arrivals` | Redesign | M3 | One ETA engine replaces five (L-20). |
| `GET /tracking/routes/arrivals/` | `GET /api/v1/stops/{id}/arrivals` | Redesign | M3 | |
| `GET /tracking/routes/bus_route/`, `GET /tracking/routes/track_me/` | `GET /api/v1/buses/{id}/progress` | Redesign | M3 | Progress along the line + per-stop ETAs; works for idle buses (L-20). |
| `GET /tracking/routes/visualization/` | `GET /api/v1/lines/{id}/map` | Redesign | M3 | Static geometry cached with ETag; live buses never cached in it (L-20). |
| `GET/POST/PATCH/DELETE /tracking/route-segments/...` (any user can write) | `PUT /api/v1/lines/{id}/route` | Redesign | M2 | Admin only (L-04). |
| `GET /tracking/passenger-counts/...`, `POST /tracking/passenger-counts/` | `GET/POST /api/v1/trips/{id}/passenger-counts` | Redesign | M4 | Own active trip; capacity enforced. |
| `PATCH/DELETE /tracking/passenger-counts/{id}/` | — | Drop | — | Immutable measurements (L-06). |
| `GET/POST /tracking/waiting-passengers/...` | — | Drop | — | Deprecated in Django. |
| `GET /tracking/anomalies/`, `GET /tracking/anomalies/{id}/` | `GET /api/v1/anomalies`, `GET /api/v1/anomalies/{id}` | Redesign | M3 | Admin all; reporters their own. |
| `POST /tracking/anomalies/` | `POST /api/v1/anomalies` | Redesign | M3 | Trip validated against the bus (L-47). |
| `PATCH/DELETE /tracking/anomalies/{id}/` | — | Drop | — | Resolution is the only state change. |
| `POST /tracking/anomalies/{id}/resolve/` | `POST /api/v1/anomalies/{id}/resolve` | Keep | M3 | Returns the updated anomaly (L-45). |

### 2.7 Waiting lists, reports, reputation

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `POST /tracking/bus-waiting-lists/join/`, `POST /tracking/bus-waiting-lists/` (broken) | `POST /api/v1/waiting-lists` | Redesign | M4 | Bus must serve the stop; re-join works; cooldown race-free (L-27). |
| `POST /tracking/bus-waiting-lists/leave/` | `DELETE /api/v1/waiting-lists/{id}` `{reason}` | Keep | M4 | Reason stored. |
| `GET /tracking/bus-waiting-lists/`, `/{id}/` | `GET /api/v1/waiting-lists`, `/{id}` | Keep | M4 | Own entries. |
| `PATCH/DELETE /tracking/bus-waiting-lists/{id}/` (admin) | — | Drop | — | Not needed; entries expire. |
| `GET /tracking/bus-waiting-lists/summary/` | `GET /api/v1/stops/{id}/waiting` | Keep | M4 | Includes real ETA (Django always returned null). |
| `GET /tracking/waiting-reports/` (all reporters' GPS) | `GET /api/v1/waiting-reports` | Redesign | M4 | Own reports; drivers see reports for their line without reporter location (L-07). |
| `POST /tracking/waiting-reports/` | `POST /api/v1/waiting-reports` | Redesign | M4 | Same confidence model; reward granted on verification instead of on submission (L-55). |
| `PATCH/DELETE /tracking/waiting-reports/{id}/` | — | Drop | — | L-06. |
| `POST /tracking/waiting-reports/{id}/verify/` | `POST /api/v1/waiting-reports/{id}/verify` | Redesign | M4 | Once, not by the reporter, by a driver operating that line within 30 min (L-28). |
| `GET /tracking/reputation/`, `/{id}/`, `/my_stats/` | `GET /api/v1/me/reputation` | Redesign | M4 | GET without side effects (L-43). |
| `GET /tracking/reputation/leaderboard/` | `GET /api/v1/leaderboards/reputation` | Keep | M6 | No e-mail in public payloads (L-42). |

### 2.8 Gamification (ask before building, spec §5 M6)

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /tracking/virtual-currency/my_balance/`, `/my-currency/balance/`, `/driver-currency/balance/`, list/retrieve variants | `GET /api/v1/me/wallet` | Redesign | M6 | Three duplicates collapsed (L-36); GET never credits a bonus (L-43). |
| `GET .../virtual-currency/transactions/`, `/my-currency/transactions/`, `/driver-currency/transactions/` | `GET /api/v1/me/wallet/transactions` | Redesign | M6 | |
| `GET /tracking/driver-currency/earnings_summary/` | `GET /api/v1/me/wallet/summary?days=` | Keep | M6 | |
| `POST /tracking/virtual-currency/adjust/` | `POST /api/v1/admin/users/{id}/wallet/adjustments` | Keep | M6 | Audited; no negative balance unless explicitly allowed (L-15). |
| `GET .../virtual-currency/leaderboard/`, `/driver-currency/leaderboard/`, `/driver-performance/leaderboard/` | `GET /api/v1/leaderboards/{earners,drivers}` | Redesign | M6 | Valkey sorted sets; `Sum` not `Count` (L-42); `period` honoured. |
| `GET /tracking/driver-performance/`, `/{id}/`, `/my_stats/` | `GET /api/v1/drivers/me/performance`, `GET /api/v1/drivers/{id}/performance` (admin) | Redesign | M6 | |
| `GET /tracking/premium-features/`, `/{id}/`, `/available/` | `GET /api/v1/premium-features` | Keep | M6 | Filtered by eligibility. |
| `POST /tracking/premium-features/purchase/` | `POST /api/v1/premium-features/{id}/purchase` | Redesign | M6 | Eligibility, atomic debit, renewal (L-58, L-59). |
| `GET /tracking/user-premium-features/...`, `/active/` | `GET /api/v1/me/premium-features` | Keep | M6 | Expiry computed, not written on GET. |
| `POST /tracking/user-premium-features/{id}/check_access/` | `GET /api/v1/me/premium-features?feature_type=` | Redesign | M6 | |

### 2.9 Notifications

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET/POST /notifications/device-tokens/`, `GET/PUT/PATCH/DELETE .../{id}/`, `POST .../{id}/deactivate/` | `GET/PUT /api/v1/me/device-tokens`, `DELETE /api/v1/me/device-tokens/{id}` | Redesign | M5 | Upsert by token (L-37). |
| `GET /notifications/notifications/`, `/{id}/` | `GET /api/v1/me/notifications`, `/{id}` | Keep | M5 | |
| `PUT/PATCH/DELETE /notifications/notifications/{id}/` | `DELETE /api/v1/me/notifications/{id}` | Redesign | M5 | Users cannot rewrite notification content (L-38). |
| `POST .../{id}/mark_read/`, `POST .../mark_all_read/` | `POST /api/v1/me/notifications/{id}/read`, `POST /api/v1/me/notifications/read` `{ids?}` | Redesign | M5 | Owner-scoped (IDOR L-09). |
| `GET .../unread_count/` | `GET /api/v1/me/notifications/unread-count` | Keep | M5 | |
| `POST /notifications/notifications/` (admin, notifies itself) | `POST /api/v1/admin/notifications` | Redesign | M5 | Targets users/roles/line subscribers (L-38). |
| `POST .../schedule_arrival/` | `POST /api/v1/me/arrival-alerts` | Redesign | M5 | Deduplicated per (user, trip, stop); real ETA. |
| `GET /notifications/schedules/`, `POST .../{id}/cancel/` | `GET /api/v1/me/arrival-alerts`, `DELETE /api/v1/me/arrival-alerts/{id}` | Redesign | M5 | Cancel is a real state (L-34). |
| `GET/POST /notifications/preferences/`, `.../{id}/`, `.../by_type/` | `GET /api/v1/me/notification-preferences`, `PUT /api/v1/me/notification-preferences/{type}` | Redesign | M5 | Quiet hours clearable (L-39). |
| `POST /notifications/system/notify_delay/` | `POST /api/v1/admin/notifications/delays` | Keep | M5 | |
| `apps/notifications/enhanced_views.py` (unrouted) | — | Drop | — | Dead code. |

### 2.10 Offline mode (ask before building, spec §5 M6)

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /offline/config/`, `/config/{id}/`, `/config/current/` | `GET /api/v1/offline/config` | Redesign | M6 | Static configuration from server settings. |
| `GET /offline/cache/status/`, `POST /offline/cache/sync/`, `POST /offline/cache/clear/`, `GET /offline/cache/statistics/`, `POST /offline/data/get_data/`, `GET /offline/data/{lines,stops,schedules,buses,notifications}/` | `GET /api/v1/offline/bundle` (ETag, `?since=`) | Redesign | M6 | Proposal: one versioned bundle the app stores locally; no per-user server copies (L-40). |
| `GET/POST /offline/sync-queue/...`, `queue_action`, `process`, `pending`, `failed`, `retry` | Regular endpoints + `Idempotency-Key` | Redesign | M6 | Django marked queued actions completed without applying them (L-40). |
| `GET /offline/logs/...` | — | Drop | — | Server-side logging of client cache hits has no consumer. |

### 2.11 Admin analytics

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| `GET /admin/stats/ridership/` | `GET /api/v1/admin/stats/ridership` | Redesign | M6 | `avg_occupancy` computed from passenger counts (L-61); Algiers-local dates. |
| `GET /admin/stats/lines/` | `GET /api/v1/admin/stats/lines` | Keep | M6 | |
| `GET /admin/stats/stops/busiest/` | `GET /api/v1/admin/stats/stops/busiest` | Keep | M6 | `top_n` validated. |

---

## 3. WebSocket protocol

The protocol is redesigned as a versioned envelope (`dzbus.v1.json` / `dzbus.v1.proto`). The
names below are the planned event names; the legacy names are listed only to show which
capability each event replaces. Legacy message compatibility is not a goal.

| Django | Rust | Mark | M | Notes |
|---|---|---|---|---|
| Endpoint `ws/` with `?token=<JWT>` (refresh tokens accepted, invalid → anonymous, token logged) | `GET /api/v1/ws?ticket=<one-time>` after `POST /api/v1/ws/ticket` | Redesign | M3 | Short-lived single-use ticket (L-11); anonymous allowed for public channels; Origin allow-list; closes with 4401/4403. Sub-protocols `dzbus.v1.json` / `dzbus.v1.proto`. |
| Auto-join `tracking_updates` (every bus to every client) | — | Redesign | M3 | Firehose removed (L-10); explicit subscriptions with per-connection caps. |
| Auto-join `notifications_{user_id}` | Auto-subscribe `user:{id}` | Keep | M3 | |
| `subscribe_to_bus {bus_id}` → `subscription_confirmed` | `subscribe {channel:"bus:{id}"}` and the legacy shape | Redesign | M3 | Bus channel now actually receives events (L-10). |
| `subscribe_to_line {line_id}` / `unsubscribe_from_line` | `subscribe` / `unsubscribe` `{channel:"line:{id}"}` | Redesign | M3 | UUIDs validated; unsubscribe for every channel kind. |
| — | `subscribe {channel:"stop:{id}"}` | Spec §5 M3 | M3 | Waiting counts and arrivals for a stop. |
| `subscribe {channel:"notifications", user_id}` | implicit `user:{id}` | Redesign | M3 | Own channel only. |
| `subscribe {channel:"general"|"system"}` | — | Drop | — | No producer ever existed (L-10). |
| `heartbeat` / `ping` → `heartbeat_response` | Same messages + protocol ping/pong | Keep | M3 | Server-initiated pings; idle connections closed. |
| `connection_established` | Same | Keep | M3 | |
| `bus_location_update {bus_id, location{...}, timestamp}` | Same event name and field names | Keep | M3 | `0` values no longer become `null` (L-48b); sent to `bus:{id}` and `line:{id}`; after commit. |
| `waiting_count_update` (no producer) | Same name, produced by waiting reports/lists | Keep | M4 | |
| `trip_update` (no producer) | Same name, produced on trip start/end | Keep | M3 | |
| `bus_status_update` (no producer) | Same name, produced on activate/deactivate/approve | Keep | M2/M3 | |
| `user_notification` | Same name | Keep | M5 | Sent after commit. |
| `notification` (`general_notification`, no producer) | `notification` for broadcasts to a line/role | Keep | M5 | |
| `gamification_update {delta, new_balance, reason}` | Same | Keep | M6 | Balance reported from the committed ledger. |
| `error {message}` | `error {code, message}` | Redesign | M3 | Machine-readable code added; message localized. |
| Binary frames (crash the consumer) | Protobuf frames when `dzbus.v1.proto` is negotiated | Redesign | M3 | |

---

## 4. Celery → jobs and cron

| Django task (schedule) | Rust job | Mark | M | Notes |
|---|---|---|---|---|
| `tracking.clean_old_location_data` (daily 00:00) | cron `location_history.retention` | Redesign | M3 | Drops whole daily partitions older than 7 days instead of an unbatched DELETE. |
| `notifications.process_scheduled` (60 s) | `jobs` rows with `run_at` | Redesign | M5 | Claimed with `FOR UPDATE SKIP LOCKED`, retried with backoff, dead-lettered (L-34). |
| `notifications.check_arrival_notifications` (120 s, broken) | arrival-alert evaluation on location ingest | Redesign | M5 | Event-driven from the ETA engine (L-33). |
| `notifications.send_trip_updates` (60 s, duplicates) | job enqueued by trip start/end (outbox) | Redesign | M5 | Exactly one notification per event (L-33). |
| `notifications.cleanup_old_notifications` (daily 03:00) | cron `notifications.retention` | Keep | M5 | |
| `tracking.notify_waiting_passengers_on_arrival` (30 s, racy) | arrival evaluation on ingest + guarded `UPDATE ... RETURNING` | Redesign | M4/M5 | Direction-aware (bus not yet past the stop). |
| `lines.broadcast_disruption` (ad hoc, before commit) | outbox job `disruption.fan_out` | Redesign | M2/M5 | After commit; passengers subscribed to the line, not only admins (L-32). |
| `offline_mode.check_auto_sync`, `auto_sync_user_cache`, `process_sync_queues`, `clean_expired_cache`, `update_cache_statistics`, `cleanup_old_logs` | — | Drop (pending M6 decision) | M6 | No server-side per-user cache in the proposed design. |
| `tracking.process_location_updates` (unscheduled) | inline in the ingest pipeline | Redesign | M3 | Speed anomaly (> 120 km/h) and route deviation (> 1 km from the line route) evaluated per fix (L-19). |
| `tracking.detect_anomalies` (unscheduled, broken) | cron `anomalies.detect_bunching_and_gaps` (5 min) | Redesign | M3 | Bunching < 500 m, gap > 30 min, deduplicated 30 min. |
| `tracking.calculate_eta_for_stops` (unscheduled, write-only cache) | ETA engine on ingest | Redesign | M3 | |
| `notifications.cleanup_invalid_tokens` (unscheduled) | inline deactivation on FCM errors + cron `device_tokens.prune` | Redesign | M5 | |
| `notifications.send_bulk_notification`, `test_push_notification`, `health_check`, `clean_old_data`, `process_scheduled_notifications` (duplicate names, L-35b) | `notification.deliver` job per (notification, channel) | Redesign | M5 | |
| `config.celery.debug_task` | — | Drop | — | Debug only. |
| — | `email.send` | *fix* | M1 | Password-reset e-mails (L-30). |
| — | cron `auth.purge_expired` (hourly) | *fix* | M1 | Expired sessions/refresh/reset tokens (L-60). |
| — | cron `jobs.purge_finished` (daily) | New | M1 | Keeps the queue table small. |
| — (replaced media files were never deleted) | `storage_delete_object` (outbox) | *fix* | M2 | Enqueued in the transaction that drops a reference to an object (replaced/removed avatar, photo or document). |
| — | cron `purge_expired_uploads` (hourly) | New | M2 | Deletes pending uploads expired for more than an hour and their objects (500 per run). |

All cron jobs are de-duplicated across replicas: each firing is enqueued with a unique
`dedup_key = cron:<name>:<slot>` so only one replica's enqueue succeeds (ADR-0006).

---

## 5. Cache keys → Valkey

| Django key (TTL) | Rust key | Mark | M |
|---|---|---|---|
| `bus:location:{bus_id}` (60 s) | `{prefix}bus:{id}:pos` hash + `{prefix}buses:geo` geo set (TTL'd by sweeper) | Redesign | M3 |
| `line:buses:{line_id}` (300 s, never refreshes L-20) | derived from the geo set + `line:{id}:buses` set | Redesign | M3 |
| `bus:passengers:{bus_id}` (300 s) | field `occupancy` in the bus hash | Redesign | M4 |
| `stop:waiting:{stop_id}` (300 s) | `{prefix}stop:{id}:waiting` | Keep | M4 |
| `driver:rating:{driver_id}` (3600 s) | — (rating stored as sum/count columns) | Drop | — |
| `eta:{bus}:{stop}` (300 s, write-only) | `{prefix}bus:{id}:eta` hash | Redesign | M3 |
| `route_visualization_{line_id}` (300 s, live data cached) | ETag'd static payload | Redesign | M3 |
| `device_token:*`, `fcm:invalid_tokens`, `fcm:rate_limit:*` | `{prefix}fcm:*` (atomic INCR/SADD) | Redesign | M5 |
| DRF `throttle_*` | `{prefix}rl:{tier}:{identity}` (GCRA) | Redesign | M1 |
| Django sessions (cache) | — | Drop | — |
| — | `{prefix}revoked:sid:{sid}`, `{prefix}revoked:user:{uid}` | New | M1 |
| — | `{prefix}idem:{actor}:{key}` | New | M1 |
| — | `{prefix}ws:ticket:{hash}` | New | M3 |

---

## 6. Settings → environment

| Django setting / env | Rust (`DZ_*`) | Mark | Notes |
|---|---|---|---|
| `SECRET_KEY` / `DJANGO_SECRET_KEY` / `SIMPLE_JWT.SIGNING_KEY` | `DZ_AUTH__SIGNING_KEYS_DIR`, `DZ_AUTH__ACTIVE_KEY_ID` | Redesign | Ed25519 key files with `kid`; startup fails without them in production (L-14). |
| `SIMPLE_JWT` lifetimes 30 min / 7 d | `DZ_AUTH__ACCESS_TOKEN_TTL_SECS` (900), `DZ_AUTH__REFRESH_TOKEN_TTL_SECS` (14 d sliding), `DZ_AUTH__SESSION_MAX_LIFETIME_SECS` (60 d absolute) | Redesign | |
| `AUTH_PASSWORD_VALIDATORS` (never invoked) | `DZ_AUTH__PASSWORD_MIN_LENGTH` (12) + built-in policy | Redesign | L-29 |
| `DATABASE_URL`, `DB_*`, `CONN_MAX_AGE`, `ATOMIC_REQUESTS` | `DZ_DATABASE__*` | Redesign | Explicit transactions per use-case (L-62b). |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CHANNEL_LAYERS_REDIS` | `DZ_VALKEY__URL` | Redesign | One Valkey for cache/pub-sub/rate limits; the durable queue is in Postgres (no eviction risk, L-12b). |
| `CORS_ALLOWED_ORIGINS`, `CORS_ALLOW_CREDENTIALS` | `DZ_HTTP__CORS_ALLOWED_ORIGINS` | Keep | Bare origins validated; https in production. |
| `DEFAULT_THROTTLE_RATES` | `DZ_RATE_LIMIT__*` | Redesign | `sustained 1000/day` dropped: it locked out drivers after ~4 h (L-13). |
| `LANGUAGE_CODE`, `LANGUAGES`, `TIME_ZONE` | built in (fr default; Africa/Algiers for local-day rules) | Keep | |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | `DZ_EMAIL__TRANSPORT`, `DZ_EMAIL__SMTP_URL`, `DZ_EMAIL__FROM` | Keep | |
| `TWILIO_*` | `DZ_SMS__*` | Keep | M5 |
| `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_SERVER_KEY` | `DZ_PUSH__FCM_SERVICE_ACCOUNT_FILE`, `DZ_PUSH__FCM_PROJECT_ID` | Redesign | FCM HTTP v1 (L-16). |
| `USE_S3`, `AWS_*` (ignored by Django 5.2, L-16b) | `DZ_STORAGE__*` | Redesign | M2; any S3-compatible service (RustFS bundled in the compose `storage` profile), private bucket, presigned URLs (uploads with signed type and size; downloads stable per hour). Optional outside production: without it uploads answer `503 storage_unavailable` and `*_url` fields are `null`. |
| `SENTRY_DSN` (crashes settings, L-16c) | `DZ_TELEMETRY__OTLP_ENDPOINT` | Redesign | OpenTelemetry instead of a vendor SDK. |
| `SECURE_*`, HSTS, `X_FRAME_OPTIONS` | nginx + API security headers | Redesign | TLS terminates at nginx. |
| `BUS_LOCATION_HISTORY_RETENTION` (7), `PASSENGER_COUNT_HISTORY_RETENTION` (30) | `DZ_TRACKING__*` | Keep | M3/M4 |
| `GOOGLE_MAPS_API_KEY`, `DRIVER_APPROVAL_REQUIRED`, `BUS_LOCATION_UPDATE_INTERVAL` | — | Drop | Unused. |

## 7. Management commands → `dz-cli`

| Django | Rust | Mark | M |
|---|---|---|---|
| `manage.py migrate` | `dz-cli migrate` | Keep | M1 |
| `manage.py createsuperuser` | `dz-cli create-admin` | Keep | M1 |
| — | `dz-cli gen-signing-key` | New | M1 |
| — | `dz-cli storage create-bucket` | New | M2 |
| `seed_webtest` | `dz-cli seed --demo` | Keep | M2 |
| `create_premium_features` | `dz-cli seed --premium-features` | Keep | M6 |
| simplejwt `flushexpiredtokens` | cron `auth.purge_expired` | Redesign | M1 |
| — | `dz-cli import-from-django` | Spec M7 | M7 |

## 8. Dead legacy code (not ported)

`tasks/` package; `apps/notifications/enhanced_views.py`, `config.py`, `monitoring.py` (unrouted);
`apps/api/v1/notifications/views.py`; `DriverRatingViewSet`; `apps/core/viewsets.py`;
`apps/api/routers.py`; unused pagination/throttle/filter classes; `ReportValidator` and
`LocationSpoofingDetector` (their useful rules are re-specified in M4); Django admin.

---

## 9. Legacy defects and the Rust fix

Source references are to the Django tree on `main`. "Fixed by design" means the Rust structure
makes the defect impossible rather than patching it.

### Security

| ID | Defect (legacy location) | Rust fix | M |
|---|---|---|---|
| L-01 | Anyone can self-register as admin: `user_type` writable in `UserCreateSerializer` (`apps/api/v1/accounts/serializers.py:56`) and `IsAdmin` trusts it (`apps/core/permissions.py`). | Registration DTO has no role field and rejects unknown fields; role changes only via audited admin endpoint. | M1 |
| L-02 | Any driver can edit/delete any driver, or create a driver profile for any user (`apps/api/v1/drivers/views.py:46`). | `Policy::authorize` ownership rules; driver profile always bound to the caller; no hard delete. | M2 |
| L-03 | Driver ID card / licence numbers and photos exposed to all users and to anonymous callers via `active-buses?expand_driver=true`; S3 objects public-read. | Separate public/admin DTOs; private bucket with short-lived presigned GETs for admins only. | M2/M3 |
| L-04 | Any authenticated user can write route segments (`route_views.py:198`). | `PUT /lines/{id}/route` requires `LineWrite`. | M2 |
| L-05 | Drivers create buses for any driver and toggle status/activation themselves (`buses/serializers.py:48,63`). | Bus owner forced to the caller; status/activation require `BusManage`. | M2 |
| L-06 | Unscoped write IDORs on trips, locations, passenger counts, waiting reports (`tracking/views/__init__.py:256,406,573,1033`); trip create trusts a body `driver` (`:648`). | Immutable measurements (no PATCH/DELETE); trip driver = caller; ownership checked in use-cases. | M3/M4 |
| L-07 | Every reporter's GPS position and name listed to all users (`waiting-reports`). | Reporter location stored for verification only, never returned to others. | M4 |
| L-08 | Side effects (WS, cache, Celery, notifications) fire inside the transaction, before commit. | Transactional outbox: repository writes persist their audit entries and jobs in the same transaction (`WriteEffects`, M2); jobs run after the commit; publishing (WS, push) follows the same rule. | M2+ |
| L-09 | `mark_all_read` with ids marks any user's notifications (`notifications/views.py:116`). | Owner-scoped `UPDATE ... WHERE user_id = $1`. | M5 |
| L-10 | Every WS client (incl. anonymous) receives every bus position; groups leak; arbitrary group names. | Explicit, validated, capped subscriptions; no firehose; cleanup on close. | M3 |
| L-11 | WS accepts refresh and logged-out tokens, logs the token, silently downgrades to anonymous, no Origin check. | One-time tickets, Origin allow-list, explicit close codes, token never logged. | M3 |
| L-12 | Throttle key is the raw `X-Forwarded-For` (spoofable); gunicorn trusts all proxies. | Client IP from `X-Forwarded-For`/`X-Real-IP` only when the peer is in `DZ_HTTP__TRUSTED_PROXIES`. | M1 |
| L-12b | One Redis with `allkeys-lru` holds broker + channel layer (queued tasks can be evicted). | Durable jobs in Postgres; Valkey holds only reconstructible data. | M1 |
| L-13 | `sustained 1000/day` blocks drivers after ~4 h; location throttle never applied. | Per-endpoint GCRA tiers; location tier 100/min. | M1/M3 |
| L-14 | JWT signed with a public default key unless `SECRET_KEY` also set (`settings/base.py:23,200`). | Asymmetric keys from files; startup fails without them in production. | M1 |
| L-15 | Coin balances: read-modify-write races, welcome bonus lost, double spend, negative balances. | Ledger postings in one transaction with row locks / conditional updates. | M6 |
| L-16 | Push uses the shut-down FCM legacy batch API; `google-services.json` used as credentials. | FCM HTTP v1 with service-account OAuth2. | M5 |
| L-16b | S3 settings ignored by Django 5.2 (`STATICFILES_STORAGE`/`DEFAULT_FILE_STORAGE`). | Object storage adapter with explicit config. | M2 |
| L-16c | `SENTRY_DSN` makes settings import crash (`production.py:72`). | Not applicable (OTLP). | M1 |
| L-29 | No password strength validation anywhere; change/reset do not revoke tokens. | Policy (length, blocklist, similarity); all sessions revoked on change/reset. | M1 |
| L-30 | Password reset e-mail never sent; tokens valid 3 days. | Single-use 1 h tokens, e-mailed through the job queue; link carries the token in the URL fragment. | M1 |
| L-31 | Driver registration not atomic, validators bypassed, duplicates → 500. | One transaction; validated; conflicts → 409. | M2 |
| L-35 | E-mail case handled inconsistently (login exact match vs register lower-case). | Always lower-cased; unique index. | M1 |
| L-42 | Leaderboards fall back to showing e-mail addresses. | Public names only (first name + initial). | M6 |
| L-53 | Some catalogue endpoints public, others not (`IsAdminOrReadOnly`). | Catalogue and live tracking reads are consistently public; PII never public. | M2 |
| L-58 | Premium purchase ignores `target_users` / `required_level`. | Eligibility enforced. | M6 |

### Correctness

| ID | Defect (legacy location) | Rust fix | M |
|---|---|---|---|
| L-17 | Concurrent trip starts create two active trips (`tracking/services/__init__.py:148`). | Partial unique indexes on active trips per bus and per driver. | M3 |
| L-18 | `end_trip` fails `full_clean` for any trip that moved (unquantized average speed, `:696`), and reject/suspend silently leave trips open; `stop_tracking` stores unclamped speeds. | One finaliser with rounding and clamping; errors propagate. | M3 |
| L-19 | Speed/route anomaly detection and bunching/gap detection never run (unscheduled, NameError). | Inline detection + scheduled sweep. | M3 |
| L-20 | Five ETA algorithms; ETA ignores passed stops; reliability uses `.seconds`; visualization caches live positions. | Single ETA engine (live speed → historical segment times → bus average). | M3 |
| L-21 | Active trip defined two ways (`is_completed` vs `end_time IS NULL`); BusLine state drifts. | Trip is the single source of truth. | M3 |
| L-22 | Stop re-ordering always fails on the unique constraint (`lines/services.py:356`). | Deferrable unique constraint; whole-list replace. | M2 |
| L-23 | Schedule validation bypassed by `POST /lines/schedules/`; overlap includes inactive rows. | Database exclusion constraint on active schedules; one creation path. | M1/M2 |
| L-24 | No driver state machine; approve ignores its flag; reapply not logged, admins never notified (off-enum type); `changed_by` never set. | Explicit transition table in the domain; every transition logged with actor. | M2 |
| L-25 | Suspension/rejection do not take the driver's buses off duty. | Cascade in the same transaction. | M2 |
| L-26 | Rating eligibility query crashes (`user=` instead of `reporter=`); not tied to a trip; self-rating possible. | Eligibility = rode a trip of this driver within 48 h; no self-rating. | M4 |
| L-27 | Waiting list: re-join after leaving impossible (unique constraint), reactivation branch inverted, generic create always 400. | Upsert with cooldown check under lock. | M4 |
| L-28 | Report verification repeatable, any driver, own reports, pays every time (coin farm). | Single verification, verifier ≠ reporter, operating the line, within a window. | M4 |
| L-32 | Disruptions notify admins only; task may run before commit. | Outbox fan-out to affected passengers after commit. | M2/M5 |
| L-33 | Arrival notifications broken (FieldError, missing method); trip updates sent twice. | Event-driven, deduplicated. | M5 |
| L-34 | Scheduled notifications not claim-safe, failed rows retried forever, cancel = "sent". | Job queue with states, attempts, backoff, dead letter. | M5 |
| L-35b | Four Celery task names registered twice; winner depends on import order. | Unique job kinds checked at compile time (enum). | M1 |
| L-36 | Duplicate endpoints with diverging rules (3 trip starts, 3 balances, 2 logins, ...). | One endpoint per capability. | M1–M6 |
| L-37 | Device token re-registration fails after deactivation; one token shared by several users. | Globally unique token, upsert re-assigns. | M5 |
| L-38 | Off-enum notification types persisted; admin create notifies the admin; users can edit content. | Closed enum + migration; target selection; read-only content. | M5 |
| L-39 | Quiet hours compared in UTC, only on one path, cannot be cleared; push flag ignored. | Evaluated in Africa/Algiers on every channel; nullable fields. | M5 |
| L-40 | Offline sync queue marks actions completed without applying them; sync error state rolled back. | Redesign (see §2.10). | M6 |
| L-41 | `?search=` and geo filters silently ignored; `limit`+filter → 500; booleans filtered twice; raw params → 500. | Typed query DTOs; invalid input → 422. | M1+ |
| L-43 | GET endpoints with write side effects (balance creation +100, cache status, premium expiry). | Safe methods are read-only. | M4/M6 |
| L-44 | PATCH returns a field subset; create returns echoes without `id`. | Full resource representation. | M1+ |
| L-45 | Anomaly resolve returns stale object; bus approve reason / leave reason / verify notes accepted but dropped. | Return updated rows; store accepted fields or reject them. | M2–M4 |
| L-46 | `POST /accounts/profiles/` and `POST /offline/sync-queue/` always 500. | Endpoints removed. | M1 |
| L-47 | Anomaly `trip_id` not validated against the bus. | Validated. | M3 |
| L-48 | Passenger-count capacity check only on one path; `0` speed/heading become `null` in WS. | Use-case enforces capacity; explicit `Option` handling. | M3/M4 |
| L-49 | No lat/lng range, heading or speed validation; `latitude == 0` rejected; line colour unvalidated. | Typed value objects with ranges. | M2/M3 |
| L-50 | Unassigned bus-line pair cannot be re-assigned. | Upsert. | M2 |
| L-51 | Line stop selectors lose the line order. | Ordered by position. | M2 |
| L-52 | Journey planner ignores inactive lines/stops, mishandles transfers, first-leg ETA only. | Fixed algorithm with tests. | M2 |
| L-54 | Passengers list every trip in the system but get nothing from history. | Consistent scoping. | M3 |
| L-55 | Reputation accuracy divides by unverified reports; one verification → platinum ×2; coins paid before verification; early-adopter bonus always 0; consistency bonus repeats. | Verified-only accuracy with minimum counts; rewards on verification; bonuses computed before insert, once per streak. | M4/M6 |
| L-56 | Driver performance never updated (hooks never called); rating not synced. | Updated from trip end, verification, anomalies, ratings. | M6 |
| L-57 | Concurrent ratings store stale averages. | `rating_sum`/`rating_count` atomic increments. | M4 |
| L-59 | Re-purchasing an expired-but-active premium feature fails with a 500. | Renewal extends the entitlement. | M6 |
| L-60 | Blacklisted tokens never purged. | Hourly purge job. | M1 |
| L-61 | Admin stats: `avg_occupancy` is the average of `max_passengers`; UTC vs local dates. | Correct aggregate; Algiers-local days. | M6 |
| L-62 | Waiting lists, disruptions, entitlements never expire automatically. | Expiry rules + sweeps. | M4–M6 |
| L-62b | `ATOMIC_REQUESTS` silently disabled by settings overrides. | Explicit transaction per use-case. | M1 |
| L-63 | Profile creation via signal + lazy getters races on the 1:1 relation. | Created in the user's insert transaction. | M1 |

---

## 10. Decisions that need the product owner

1. **Offline mode (M6).** Proposed: drop server-side per-user cache tables and the sync queue in
   favour of a versioned bundle plus idempotent replay. To confirm before M6.
2. **Gamification scope (M6).** The spec says to ask before building M6; the coin economy has
   several abuse paths in Django (L-15, L-28, L-55). To confirm the simplified rules.
3. **Public live tracking.** Kept public (as `active-buses` was), without any driver PII. Live
   positions of specific buses are therefore visible to anonymous users; confirm this is intended.
4. **Existing Flutter client.** Decided: no compatibility. The REST and WebSocket contracts are
   new; the upcoming Next.js and React Native clients are built against them.
