# DZ Bus Tracker — Full-Stack Audit

> Perspective: real Algerian bus operator & daily commuter in a mid-size wilaya.
> Covers: Django backend + Flutter frontend, integration gaps, and end-to-end flows.
> Generated: 2026-03-12

---

## 1. Project Overview

**DZ Bus Tracker** is a real-time public-bus tracking platform for Algeria.

| Role | Core need |
|------|-----------|
| **Passenger** | Know when the next bus arrives, how crowded it is, earn rewards for contributing crowd data |
| **Driver** | Broadcast GPS location, manage passenger counts, track performance and earnings |
| **Admin** | Approve drivers/buses, manage fleet/routes, monitor system health |

**Backend:** Django 5.2 + DRF · PostgreSQL · Redis · Celery · Django Channels (WebSocket) · Uvicorn/ASGI · JWT
**Frontend:** Flutter 3.8+ · Provider state management · Google Maps / OSRM · WebSocket
**Push:** Firebase FCM (configured but disabled in Flutter main.dart)

---

## 2. All Workflows & Use Cases

### 2.1 Passenger

#### Registration & Onboarding
1. `POST /api/v1/accounts/register/` → auto-creates `Profile`, `ReputationScore` (Bronze), `VirtualCurrency` (0 balance).
2. First login → `access` + `refresh` JWT tokens; WebSocket connects immediately on splash screen.
3. Optional: language (fr/ar/en), notification channels.

#### Finding a Bus / Route
1. `GET /api/v1/lines/lines/` — browse routes by name/code.
2. `GET /api/v1/lines/stops/nearby/?lat=&lon=&radius=` — stops within X metres (**returns raw list, not paginated**).
3. `GET /api/v1/tracking/active-buses/` — passenger map pins.
4. WebSocket: `{"type":"subscribe_to_bus","bus_id":"..."}` → live location stream.
5. No endpoint to plan a journey from Stop A to Stop B.

#### Reporting a Waiting Count (Core gamification loop)
1. Passenger physically at a stop submits `POST /api/v1/tracking/waiting-reports/`.
2. `bus` OR `line` is required — stop-alone rejected with 400.
3. Report status = **pending** until a driver verifies it.
4. On driver verification → reputation updated + coins awarded (base ≥50 + proximity/early-adopter bonuses).
5. Rate limit: 1 report / 10 minutes / stop / user.

#### Joining a Waiting List
1. `POST /api/v1/tracking/bus-waiting-lists/` → associates user with bus+stop.
2. Field `notified_on_arrival` exists on model — **notification is never actually triggered**.
3. `DELETE /api/v1/tracking/bus-waiting-lists/{id}/` to leave.

#### Coin Economy & Premium
- Balance: `GET /api/v1/tracking/virtual-currency/`
- Transactions: `GET /api/v1/tracking/virtual-currency/transactions/`
- Browse features: `GET /api/v1/tracking/premium-features/`
- Purchase: `POST /api/v1/tracking/user-premium-features/` (deducts coins, sets expiry)

#### Notifications (In-App)
- `GET /api/v1/notifications/notifications/` · `POST /api/v1/notifications/{id}/mark_read/`
- `GET /api/v1/notifications/notifications/unread_count/`
- Flutter UI: `NotificationProvider.updatePreference()` is a **placeholder — preferences are never persisted to backend**.
- Firebase push: **disabled** — `FirebaseMessaging.requestPermission()` commented out in `main.dart`.

#### Offline Mode
- `POST /api/v1/offline/sync/` — caches lines, stops, schedules, buses.
- `GET /api/v1/offline/cache-status/` — sync status, expiry, cache size.
- Offline actions queued in `SyncQueue`; retried on reconnect.
- Flutter: `LocationSyncService` queues GPS updates when offline; sync on reconnect exists but **not fully tested**.

---

### 2.2 Driver

#### Registration & Approval
1. `POST /api/v1/accounts/register-driver/` — multipart with `id_card_number`, `driver_license_number`, photos.
2. Status = **pending** → cannot start trips or update location.
3. Admin approves/rejects → push notification to driver (push disabled, so in-app only).
4. **Re-apply after rejection:** `POST /api/v1/drivers/drivers/{id}/reapply/` exists in backend but **no Flutter screen or provider method calls it** — rejected drivers are stuck.

#### Bus Assignment
- Buses are **admin-created only** (admin assigns driver FK on Bus record).
- Drivers cannot self-register their vehicle.
- Flutter has a `DriverBusRegistrationScreen` and `POST /api/v1/buses/buses/` is listed in ApiEndpoints for drivers — **chicken-and-egg**: endpoint allows driver to POST but only if they are `IsDriverOrAdmin`, yet there is no Bus approval flow visible in the driver-side UI after submission.

#### Starting a Trip
1. `POST /api/v1/tracking/bus-lines/start_tracking/` with `bus_id` + `line_id`.
   - Or: `POST /api/v1/tracking/trips/` directly.
2. Creates `Trip` (start_time, is_completed=false) + sets `BusLine.tracking_status="active"`.
3. **Requires `IsApprovedDriver`** — but this permission only blocks `status=="pending"`, not `status=="rejected"` or `"suspended"`.

#### Broadcasting Location (every 10–30s)
1. `POST /api/v1/buses/buses/{id}/update_location/` or `POST /api/v1/tracking/locations/`
2. System finds nearest stop, caches `bus:location:{bus_id}`, broadcasts to WebSocket group.
3. Flutter `TrackingScreen` sends GPS every configurable interval while trip is active.

#### Updating Passenger Count
1. `POST /api/v1/buses/buses/{id}/update_passenger_count/`
2. `occupancy_rate = min(count / capacity, 1.0)` — **capacity never enforced; count=999 accepted**.

#### Verifying Waiting Reports
1. `GET /api/v1/tracking/waiting-reports/?verification_status=pending`
2. `POST /api/v1/tracking/waiting-reports/{id}/verify/` → `{actual_count, verification_status}`
3. Correct → reporter earns coins; driver earns 15 coins for verification accuracy.

#### Ending a Trip
1. `POST /api/v1/tracking/trips/{id}/end/` — calculates distance/speed, sets `is_completed=true`.
2. `DriverPerformanceService.update_trip_performance()` — awards coins, updates streak.
3. **Also exists:** `POST /api/v1/tracking/bus-lines/stop_tracking/` — two endpoints can end the same trip; state can diverge.

#### Performance & Stats
- `GET /api/v1/tracking/driver-performance/my_stats/` — **response nested under `performance_score` key**, inconsistent with all other endpoints.

---

### 2.3 Admin

#### Driver Management
- List: `GET /api/v1/drivers/drivers/`
- Approve: `POST /api/v1/drivers/drivers/{id}/approve/`
- Reject with reason: `POST /api/v1/drivers/drivers/{id}/reject/`
- Suspend: `POST /api/v1/drivers/drivers/{id}/suspend/` — **does not end active trips or stop location broadcasting**.
- Status history: `GET /api/v1/drivers/drivers/{id}/status-history/`

#### Fleet Management
- `POST /api/v1/buses/buses/` → create bus, assign driver.
- `POST /api/v1/buses/buses/{id}/activate/` · `/deactivate/` · `/approve/`
- Current GPS: `GET /api/v1/tracking/active-buses/`

#### Network Management
- `POST /api/v1/lines/stops/` → stop (lat/lon/wilaya/commune)
- `POST /api/v1/lines/lines/` → route; assign stops via `POST /api/v1/lines/lines/{id}/add_stop/`
- `POST /api/v1/lines/lines/{id}/add_schedule/` → day/time schedules
- **Service disruptions:** `ServiceDisruption` model exists, no admin screen in Flutter to create/manage them.

#### Monitoring
- `GET /api/v1/tracking/anomalies/` — speed violations, route deviations, bunching.
- `PATCH /api/v1/tracking/anomalies/{id}/` — resolve anomaly.
- `GET /api/v1/tracking/trips/history/`
- Celery Beat: `detect_anomalies()`, `calculate_eta_for_stops()`, `clean_old_location_data()`
- **No aggregated analytics endpoints** — ridership, occupancy, busiest stops do not exist as API views.

#### Notifications & Content
- `POST /api/v1/notifications/notifications/` — broadcast to any user.
- `POST /api/v1/tracking/virtual-currency/add/` — admin coin adjustment.
- `PremiumFeature` catalog — **no API endpoint to create/edit premium features; likely admin panel only**.

---

## 3. Critical Audit

### 3.1 Duplicate / Redundant Features

#### A. Three Overlapping "Waiting" Concepts

| Model | Purpose |
|-------|---------|
| `WaitingPassengers` | Snapshot aggregate — service layer only, never directly user-facing |
| `WaitingCountReport` | Crowdsourced report with verification lifecycle and coin rewards |
| `BusWaitingList` | Personal "I am waiting for bus X at stop Y" with ETA field |

All three encode "passengers waiting at a stop" from slightly different angles. A commuter at a stop must use the non-obvious `WaitingCountReport` (requires bus OR line). `WaitingPassengers` is never surfaced. The distinction confuses both users and developers.

#### B. Dual Currency Endpoints (Same Underlying Model)

- Passengers: `GET /tracking/virtual-currency/`
- Drivers: `GET /tracking/driver-currency/` + `GET /tracking/driver-currency/transactions/`

Both resolve to `VirtualCurrency` + `CurrencyTransaction`. Split API surface, no actual difference. Flutter's `GamificationService` calls both paths depending on user role.

#### C. Duplicate Notification Service Files

- `apps/notifications/services.py`
- `apps/notifications/enhanced_services.py`
- `apps/notifications/tasks.py`
- `apps/notifications/enhanced_tasks.py`

Which is authoritative? "Enhanced" variants suggest incremental patching without cleanup. Risk of logic divergence.

#### D. BusLine.tracking_status vs Trip.is_completed — Dual State

Two fields encode "is this bus currently on a run." When `stop_tracking` and `trips/{id}/end` are called independently, one source can go stale.

#### E. Two Trip-Start Pathways

- `POST /tracking/trips/` — direct Trip creation
- `POST /tracking/bus-lines/start_tracking/` — creates Trip + sets BusLine

Flutter uses `start_tracking`. The direct Trip endpoint is also accessible to drivers and creates an orphaned Trip without updating `BusLine.tracking_status`.

---

### 3.2 Missing Features

#### A. No Route Planning (A → B)
A passenger who knows origin and destination stop has no endpoint to find the correct line(s) or transfer points. `GET /lines/lines/` returns all routes; the passenger must scan each manually. **Fundamental for usability.**

#### B. Bus Arrival Notification Never Fires
`BusWaitingList.notified_on_arrival` field exists, model designed for it, but **no Celery task or signal** compares bus `nearest_stop` against active waiting lists. Feature is modeled but dead.

#### C. No Passenger Trip / Line Rating
Passengers rate *drivers* but cannot rate a *trip experience* or a *line* (punctuality, cleanliness). No feedback loop from passenger experience to line quality improvement.

#### D. No Admin Analytics Endpoints
Data exists (LocationUpdate, PassengerCount, Trip) but no read-only analytics views:
- Ridership per line per day
- Average occupancy rate per hour/route
- Most active stops
- Waiting time distribution
Flutter `AnalyticsDashboardScreen` exists but appears minimal.

#### E. ETA Not Computed on Waiting List Join
`BusWaitingList.estimated_arrival` field exists — never populated at insert time. Always null in practice.

#### F. Driver Cannot Self-Register Bus
Buses are admin-only creations. Flutter has `DriverBusRegistrationScreen` but no driver-side approval flow. In Algeria's context (many owner-operator semi-informal drivers), this is a workflow blocker.

#### G. No Driver Income / Shift Tracking
Coins are gamification tokens, not salary. No model or endpoint tracks real earnings, shift hours, or trip-based pay.

#### H. No Full-Text Stop / Line Search
No `?search=` on stops by name/address or lines by description. A commuter who doesn't know the line code has no discovery mechanism. `GET /lines/stops/nearby/` requires GPS; not useful for planning from home.

#### I. Service Disruptions Invisible to Users
`ServiceDisruption` model + Flutter `service_disruption_model.dart` exist. No admin screen to create them. No passenger screen to view active disruptions. Feature is fully dead end-to-end.

#### J. Anomaly Visibility Locked to Admin
Speed violations, route deviations, and bunching are only visible to admins. Drivers are unaware when they are flagged. Passengers cannot see known service issues.

#### K. Firebase Push Notifications Disabled
`FirebaseMessaging.requestPermission()` is commented out in Flutter `main.dart`. No device token registration flow is triggered. All notifications are in-app WebSocket only — no background delivery when app is closed.

#### L. No Passenger-Facing ETA Screen
No screen shows "Bus 23 arrives at your stop in ~8 minutes." The infrastructure (LocationUpdate, nearest_stop, schedule) exists but no ETA calculation is surfaced per-stop in the passenger UI.

---

### 3.3 Illogical / Confusing Flows

#### A. `IsApprovedDriver` Does Not Block Rejected Drivers
```python
# Current (wrong):
request.user.driver.status != "pending"   # only blocks pending
# Should be:
request.user.driver.status == "approved"
```
Rejected and suspended drivers can start trips, update GPS, and submit passenger counts.

#### B. Bus Capacity Not Enforced
`PassengerCountService.update_passenger_count()` accepts any integer. No comparison to `Bus.capacity`. `occupancy_rate = min(count/capacity, 1.0)` caps display but raw data is corrupted. A driver can post `count=999` on a 40-seat bus.

#### C. Concurrent Active Trips for Same Bus
No DB constraint or service guard prevents two drivers from starting the same bus simultaneously (both receive HTTP 201). Documented gap — concurrent trip guard only partially implemented.

#### D. Premium Feature Re-Purchase Blocked by Stale Record
`unique_together = ['user', 'feature']` prevents re-purchase of an expired feature. `deactivate_if_expired()` marks `is_active=False` but does not delete the record. Re-purchase raises `IntegrityError`.

#### E. Reputation Formula Ignores Partial Matches
`accuracy_rate = (correct_reports / total_reports) * 100`. `verification_status="partially_correct"` contributes zero to accuracy but adds to total_reports — unfairly penalizing reporters who are directionally right.

#### F. Trip Decimal Overflow on End
`TripService.end_trip()` writes cumulative distance/average_speed to `DecimalField(max_digits=10, decimal_places=2)`. Long trips or calculation edge cases cause ORM overflow errors and silent trip-end failure.

#### G. Two Ways to End a Trip, Neither Checks the Other
- `POST /tracking/bus-lines/stop_tracking/` — ends via BusLine
- `POST /tracking/trips/{id}/end/` — ends via Trip

A driver who calls one can call the other and double-end. No idempotency check exists. `BusLine.tracking_status` and `Trip.is_completed` can diverge.

#### H. Driver Performance Stats Under Nested Key
```json
GET /tracking/driver-performance/my_stats/
{ "performance_score": { "total_trips": 42, ... } }
```
Every other list/detail endpoint returns data at root level. Frontend must special-case this.

#### I. Nearby Stops Returns Raw List
`GET /lines/stops/nearby/` → `[{...}, ...]` instead of `{"count": N, "results": [...]}`. Flutter `StopService.getNearby()` branches on `isinstance(response, list)` — fragile pattern.

#### J. Driver Rating: One-Per-Day Is Gameable, Unverified
`unique_together = ['driver', 'user', 'rating_date']` — one rating per calendar day per user. No verification that the passenger actually rode with the driver. `POST /drivers/{id}/ratings/` returns **405** (nested router misconfiguration). GET works; POST is broken.

#### K. Re-Apply Has No Document Re-Submission
`reapply` endpoint resets status to "pending" but does not require new photos. Admin receives a re-apply notification with no new evidence to review.

#### L. Password Reset Requires User ID (Unusable)
Backend: `POST /api/v1/accounts/users/{id}/reset-password-request/` — requires knowing the user's UUID.
Flutter: calls `/api/v1/accounts/users/reset_password_request/` without an ID.
This endpoint 404s in practice. Password reset is broken.

#### M. Notification Preferences Never Saved
Flutter `NotificationProvider.updatePreference()`:
```dart
// In real implementation, find the preference ID by type and update
// For now this is a placeholder that calls the service
return true;
```
User-facing toggle in settings does nothing persistently.

---

### 3.4 Dead-End UX Paths

| Path | Symptom | Root Cause |
|------|---------|-----------|
| `POST /drivers/{id}/ratings/` | HTTP 405 | Nested router wires GET only |
| Join waiting list → get arrival notification | Never fires | `notified_on_arrival` never set; no Celery task checks it |
| Purchase expired premium feature again | IntegrityError | `unique_together` + stale inactive record |
| Offline sync after 24h cache expiry | Stale data | `UserCache.is_expired` property exists; no middleware enforces eviction |
| Passenger at stop, no bus/line knowledge | 400 error | `WaitingCountReport` requires bus OR line |
| Admin views ridership analytics | No endpoint | No analytics ViewSets exist |
| Driver uses `stop_tracking`, then `trips/{id}/end` | Double-end | No idempotency check |
| Admin suspends driver mid-trip | Trip continues | Suspension only sets `Driver.status`; active trip/broadcasting continues |
| Rejected driver tries to re-apply | No UI | Backend endpoint exists; Flutter has no screen or provider method |
| Service disruption announced | No UI | Model + Flutter model exist; admin/passenger screens missing |
| Password reset | 404 | URL requires user ID; Flutter sends no ID |
| Turn off notification type | No effect | `NotificationProvider.updatePreference()` is a placeholder |
| View bus arrival time at my stop | No screen | ETA calculation exists in Celery tasks; not surfaced per-stop in passenger UI |

---

## 4. Recommendations

### Priority 1 — Security & Correctness

**R1 — Fix `IsApprovedDriver`** (XS)
Change `status != "pending"` → `status == "approved"`. Prevents rejected/suspended drivers from operating.

**R2 — Enforce bus capacity** (XS)
In `PassengerCountService`: if `count > bus.capacity` → `ValidationError`. Raw count should never exceed seat count.

**R3 — Prevent concurrent active trips** (S)
Guard in `start_tracking()`: `Trip.objects.filter(bus=bus, is_completed=False).exists()` → 400 if true.

**R4 — Fix Decimal overflow in TripService** (S)
Clamp: `distance = min(round(distance, 2), Decimal('99999999.99'))` or increase field precision.

**R5 — Fix re-purchase of expired features** (S)
In `PremiumFeatureService.purchase_feature()`: `UserPremiumFeature.objects.filter(user=user, feature=feature, is_active=False).delete()` before creating new record.

**R6 — Fix password reset endpoint** (XS)
Add a non-ID route: `POST /api/v1/accounts/reset-password/` that accepts `{"email": "..."}` — no UUID required. Update Flutter to call it.

**R7 — Fix `POST /drivers/{id}/ratings/`** (XS)
Register the action correctly in the nested router or move to a flat endpoint: `POST /api/v1/drivers/ratings/`.

---

### Priority 2 — Logic & UX Consistency

**R8 — Unify trip-end surface** (M)
Route `stop_tracking` through `TripService.end_trip()` internally, or deprecate `stop_tracking`. Add idempotency: if `is_completed=True` → return 200 with no re-processing.

**R9 — Allow stop-only waiting reports** (S)
Make `bus` and `line` optional in `WaitingCountReport`. Auto-detect likely bus/line from active trips near that stop. Blocking informal reporters defeats the crowdsourcing premise.

**R10 — Normalize paginated responses** (XS)
`GET /lines/stops/nearby/` must return `{count, results, next, previous}`. Remove the `isinstance(list)` branch in Flutter.

**R11 — Flatten driver performance stats** (XS)
`my_stats()` should return data at root level, not under `performance_score` key.

**R12 — Credit partial_correct in reputation** (S)
```python
effective_correct = correct_reports + (partially_correct_count * 0.5)
accuracy_rate = (effective_correct / total_reports) * 100
```

**R13 — Wire suspension cascade** (M)
On `suspend_driver()`: find active Trip → call `TripService.end_trip()` → set `BusLine.tracking_status="idle"` → notify driver in-app.

**R14 — Implement notification preferences** (S)
Replace placeholder in Flutter `NotificationProvider.updatePreference()` with a real PATCH to `GET /api/v1/notifications/preferences/{id}/`. Query preference list on load, store IDs.

---

### Priority 3 — Redundancy Cleanup

**R15 — Consolidate notification files** (S)
Merge `services.py` + `enhanced_services.py` → one `services.py`. Same for tasks. Delete "enhanced" variants.

**R16 — Consolidate currency endpoints** (S)
Replace `/tracking/virtual-currency/` and `/tracking/driver-currency/` with `/tracking/my-currency/` serving both roles.

**R17 — Clarify three waiting models** (M)
- `WaitingCountReport` → primary crowdsourced input (fix stop-only)
- `BusWaitingList` → personal queue (wire notifications)
- `WaitingPassengers` → computed aggregate derived from reports (remove direct POST if it exists)

**R18 — Resolve BusLine vs Trip dual state** (M)
Use `Trip.is_completed` as canonical active-trip flag. Derive `BusLine.tracking_status` from it or remove it.

---

### Priority 4 — Missing Critical Features (Backlog)

**R19 — Bus arrival notification** (M)
Celery task every 30–60s: find buses within ~300m of next stop → query `BusWaitingList` → create `Notification` → set `notified_on_arrival=True`. Enable Firebase in Flutter `main.dart`.

**R20 — Route planning endpoint** (L)
`GET /api/v1/lines/route-plan/?from_stop=&to_stop=` → line(s) to board, transfer points, estimated duration. Even naive "which line connects these stops" covers 80% of use cases.

**R21 — Stop / line full-text search** (S)
`GET /api/v1/lines/stops/?search=<name>` — add `icontains` filter on `name` and `address`. Same for lines. Table stakes for discovery.

**R22 — Admin analytics endpoints** (L)
Minimum:
- `GET /api/v1/admin/stats/ridership/?line=&date_from=&date_to=`
- `GET /api/v1/admin/stats/lines/` — trips/day, on-time %, avg occupancy
- `GET /api/v1/admin/stats/stops/busiest/`
Wire into Flutter `AnalyticsDashboardScreen`.

**R23 — Service disruptions end-to-end** (M)
Add Flutter admin screen to create/edit `ServiceDisruption`. Add passenger screen showing active disruptions on a line. Currently entirely dead.

**R24 — Enable Firebase push** (S)
Uncomment `FirebaseMessaging.requestPermission()` in `main.dart`. Add device token registration on login via `POST /api/v1/notifications/device-tokens/`. Test FCM delivery for `driver_approved`, arrival, and achievement notifications.

**R25 — Driver re-apply UI** (XS)
Add a "Re-apply" button on the driver rejected status screen in Flutter. Calls existing `POST /api/v1/drivers/drivers/{id}/reapply/` endpoint.

**R26 — Driver bus self-registration flow** (M)
Add bus submission form to driver onboarding. Admin approves both driver + bus in one step. Resolves chicken-and-egg where driver is approved but has no bus to operate.

**R27 — ETA on waiting list join** (M)
Compute `estimated_arrival` at `POST /bus-waiting-lists/` insert time using `BusLine.average_speed` + remaining stops distance. Return in response.

**R28 — Rating by ride verification** (M)
Before allowing `POST /drivers/ratings/`, verify passenger had a `BusWaitingList` or `WaitingCountReport` for a trip that driver completed. Prevents phantom ratings.

---

## Summary Table

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| R1 | Security — rejected driver can operate | Critical | XS |
| R2 | Data integrity — capacity not enforced | High | XS |
| R3 | Data integrity — concurrent trips | High | S |
| R4 | Bug — decimal overflow on trip end | High | S |
| R5 | Bug — re-purchase blocked by stale record | High | S |
| R6 | Bug — password reset 404 (wrong URL pattern) | High | XS |
| R7 | Bug — driver rating POST returns 405 | High | XS |
| R8 | Logic — dual trip-end endpoints | Medium | M |
| R9 | UX — stop-only report rejected | High | S |
| R10 | UX — inconsistent pagination | Medium | XS |
| R11 | UX — nested performance stats | Low | XS |
| R12 | Logic — partial_correct unfairly penalized | Medium | S |
| R13 | Logic — suspension does not end active trip | High | M |
| R14 | Bug — notification preferences never saved (Flutter placeholder) | High | S |
| R15 | Cleanup — duplicate notification files | Low | S |
| R16 | Cleanup — dual currency endpoints | Low | S |
| R17 | Clarity — three overlapping waiting models | Medium | M |
| R18 | Clarity — dual active-trip state | Medium | M |
| R19 | Missing — bus arrival notification | High | M |
| R20 | Missing — route planning | High | L |
| R21 | Missing — stop/line text search | High | S |
| R22 | Missing — admin analytics | Medium | L |
| R23 | Missing — service disruptions UI | Medium | M |
| R24 | Missing — Firebase push (disabled) | High | S |
| R25 | Missing — driver re-apply UI (endpoint exists, no screen) | Medium | XS |
| R26 | Missing — driver bus self-registration flow | Medium | M |
| R27 | Missing — ETA on waiting list join | Medium | M |
| R28 | Missing — rating by ride verification | Medium | M |

> **XS** = < 1 hour · **S** = 1–4 hours · **M** = half-day · **L** = 1–2 days

---

## Verification (post-implementation)

1. Run full test suite: `venv/bin/python api_test.py` — all 40 phases, expect 636/636 pass.
2. Check R1: `pytest tests/api/test_permissions.py -k "rejected_driver"` — should return 403.
3. Check R3: Start two trips on same bus via API — second should return 400.
4. Check R9: Submit `WaitingCountReport` with only `stop` field — should return 201.
5. Check R10: `GET /lines/stops/nearby/?lat=36&lon=3&radius=1` — response must be `{count, results, ...}` dict.
6. Check R6: `POST /api/v1/accounts/reset-password/` with email only — should return 200.
7. Flutter: enable Firebase, launch app on device, verify device token registered after login.
