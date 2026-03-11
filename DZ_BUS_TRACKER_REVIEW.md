# DZ Bus Tracker API — Comprehensive Expert Review

> **Author**: Generated via deep codebase analysis, 2026-03-11
> **Codebase commit**: 747f984 (post-bug-fix baseline)
> **Scope**: Full API review — workflows, architecture, bugs, duplicates, missing features, Algeria-specific analysis

---

## Table of Contents

1. [Algerian Bus System Context](#1-algerian-bus-system-context)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Complete Workflows — Step by Step](#3-complete-workflows)
   - 3.1 [Passenger Workflows](#31-passenger-workflows)
   - 3.2 [Driver Workflows](#32-driver-workflows)
   - 3.3 [Admin Workflows](#33-admin-workflows)
4. [Critical Issues Found](#4-critical-issues-found)
   - 4.1 [Breaking Bugs](#41-breaking-bugs)
   - 4.2 [Security & Business Logic Gaps](#42-security--business-logic-gaps)
   - 4.3 [Duplicate Features](#43-duplicate-features-major-architectural-issue)
   - 4.4 [Useless / Misfit Features](#44-uselessmisfit-features)
   - 4.5 [Missing Features](#45-missing-features-critical-gaps)
   - 4.6 [Confusing / Illogical Workflows](#46-confusingillogical-workflows)
5. [Algeria-Specific Analysis](#5-algeria-specific-analysis)
6. [Prioritized Improvement Recommendations](#6-prioritized-improvement-recommendations)
7. [Appendix — All Endpoints Reference](#7-appendix--all-endpoints-reference)

---

## 1. Algerian Bus System Context

### How Bus Transport Actually Works in Algeria

Algeria has one of the most complex and informal public bus systems in the Maghreb. Understanding it is essential before critiquing or improving this API.

**Operators:**
- **ETUSA** (Entreprise de Transport Urbain et Suburbain d'Alger) — state-owned, operates large city buses (60–90 seats) in Algiers. Has fixed routes, but schedules are often unreliable.
- **STPE** (Société de Transport de la Périphérie Est) — serves eastern Algiers suburbs.
- **Wilaya-level public operators** — each of Algeria's 58 wilayas has a transport company (e.g., ETUO in Oran, SOTU in Constantine), quality varies widely.
- **Private licensed operators** — individuals or small companies operating minibuses (14-seat Ford Transit or similar) under a granted line license.
- **Informal/unlicensed operators** — widely known as "clandestins". These buses exist everywhere, especially in smaller cities and rural areas. They have no fixed schedules, pick up anywhere, and are technically illegal but tolerated.

**Physical Reality of a Bus Stop:**
- Many stops have no physical infrastructure (no sign, no shelter, no posted schedule).
- In Algiers, numbered line signs may exist on poles but are often removed or vandalized.
- Passengers "know" the stop location culturally — bus drivers recognize regular spots.
- No tap-to-pay or ticketing at stops — all cash, paid to a conductor or driver.

**Service Patterns:**
- **Headway, not schedule**: Buses in Algeria generally run on approximate headways (every 10–20 minutes) rather than specific departure times. Printed schedules are rare and rarely followed.
- **Demand-based**: In low-demand hours, buses may skip trips entirely. Drivers may wait at a stop until the bus is full before departing (common for private operators).
- **No advance booking**: Passengers never book seats. You show up, you board if there's space.
- **Standing passengers**: Legal capacity limits exist on paper but are routinely ignored. Standing in the aisle is normal.

**Problems This App Is Trying to Solve:**
1. "Which bus do I take?" — no central information source in many cities
2. "Where is my bus?" — no real-time tracking exists currently
3. "How crowded is the next bus?" — no occupancy data
4. "Is this bus running today?" — no service disruption alerts
5. Driver accountability — passenger complaints have no formal channel

**Realistic User Base:**
- Primary users: urban commuters aged 18–45 in major cities (Algiers, Oran, Constantine)
- Smartphone penetration: ~70% in urban areas, mostly Android mid-range (Samsung A-series, Tecno, Infinix)
- Network: 4G Djezzy/Mobilis/Ooredoo available in cities, unreliable in suburbs and rural areas
- Languages: Most users speak Algerian Arabic (Darija) and/or French. Classical Arabic is the formal language. French is widely read on screen.
- Digital literacy: Moderate. Users are comfortable with WhatsApp and Facebook, but may not be used to transit apps.

**Why All This Matters:**
Every design decision in this API — from the gamification system to the capacity enforcement to the scheduling model — must be evaluated through this lens. A feature that makes perfect sense for London TfL or RATP Paris may be completely inappropriate or unfeasible for a 14-seat Algerian microbus operator.

---

## 2. System Architecture Overview

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web framework | Django 5.2 + DRF | Modern, well-chosen |
| Real-time | Django Channels + Redis | WebSocket for GPS tracking |
| ASGI server | Uvicorn | Correct choice (fast, modern) |
| Database | PostgreSQL | Appropriate for geospatial + relational data |
| Cache / broker | Redis | Powers Celery + Channels |
| Background tasks | Celery + Celery Beat | Periodic cleanup, notifications |
| Authentication | JWT (SimpleJWT) | Stateless, mobile-friendly |
| Push notifications | Firebase FCM | Standard for Android/iOS |

### Django Application Structure (12 apps)

| App | Purpose | Status |
|-----|---------|--------|
| `apps/accounts/` | User model, auth, profiles | Functional |
| `apps/buses/` | Bus fleet management | Functional, some duplication |
| `apps/drivers/` | Driver registration, approval, ratings | Partially broken |
| `apps/lines/` | Routes and stops | Functional |
| `apps/tracking/` | GPS tracking, trips, gamification, waiting | Core app, complex |
| `apps/notifications/` | Push/email/SMS notifications | Functional |
| `apps/gamification/` | Secondary gamification system | **Likely dead code** |
| `apps/core/` | Base models, middleware | Core utilities |
| `apps/api/` | URL routing, versioning, throttling | Routing layer |

### Three User Types

```
PASSENGER
├── Registers account
├── Searches lines/stops
├── Tracks buses via WebSocket
├── Reports waiting counts (earns coins)
├── Joins waiting lists
├── Views arrival estimates
├── Rates drivers
└── Purchases premium features

DRIVER
├── Registers with ID/license photos
├── Waits for admin approval
├── Sets availability
├── Starts/ends trips
├── Sends GPS location every N seconds
├── Updates passenger counts
├── Verifies waiting reports (earns coins)
└── Views performance statistics

ADMIN
├── Approves/rejects drivers and buses
├── Manages lines, stops, schedules
├── Creates notifications/broadcasts
├── Views system-wide analytics
├── Manages anomalies
└── Adjusts virtual currency
```

---

## 3. Complete Workflows

### 3.1 Passenger Workflows

---

#### Workflow P1: New Passenger Registration → Login → Profile Setup

**Step 1** — Register account
`POST /api/v1/accounts/register/`
```json
{
  "email": "passenger@example.com",
  "password": "SecurePass123",
  "first_name": "Karim",
  "last_name": "Benali",
  "phone_number": "+213555123456"
}
```
Returns `201 Created` with user object. JWT tokens NOT returned at registration — a separate login step is required.

**Step 2** — Login to get JWT tokens
`POST /api/v1/accounts/login/` or `POST /api/v1/token/`
```json
{"email": "passenger@example.com", "password": "SecurePass123"}
```
Returns `{"access": "...", "refresh": "...", "user": {...}}`

**Step 3** — Update profile (optional)
`PATCH /api/v1/accounts/profiles/update_me/`
```json
{"language": "ar", "push_enabled": true, "bio": "Commuter from Bab Ezzouar"}
```

**Step 4** — Register FCM push token (for notifications)
`POST /api/v1/notifications/device-tokens/`
```json
{"token": "FCM_TOKEN_HERE", "device_type": "android"}
```

**Issues:**
- No email verification. No phone verification. Accounts are immediately active.
- Anyone can create unlimited fake accounts to farm coins from waiting reports.

---

#### Workflow P2: Finding a Bus

**Scenario A — Searching by line name/code:**
```
GET /api/v1/lines/lines/?search=36
GET /api/v1/lines/lines/{id}/stops/
GET /api/v1/lines/lines/{id}/schedules/
```

**Scenario B — Finding nearby stops:**
```
GET /api/v1/lines/stops/nearby/?latitude=36.7538&longitude=3.0588&radius=0.5
```
⚠️ Returns a raw JSON array — NOT a paginated dict like every other list endpoint. Client must handle `isinstance(response, list)`.

```
GET /api/v1/lines/stops/{id}/lines/
```
Returns all lines passing through that stop.

**Scenario C — The critical missing scenario (journey planning):**
"I'm at Stop A, I want to reach Stop B" — **THIS ENDPOINT DOES NOT EXIST.**
This is the most fundamental feature of any transit app. See Section 4.5 MISSING-1.

**Issues:** No route/journey planning. No fare information. No bus type (microbus vs city bus) distinction.

---

#### Workflow P3: Real-Time Bus Tracking via WebSocket

**Step 1** — Open WebSocket connection (with JWT in query param)
```
ws://host:8007/ws?token=<ACCESS_TOKEN>
```
Server sends: `{"type": "connection_established", "user_authenticated": true}`

**Step 2** — Subscribe to a specific bus
```json
{"type": "subscribe_to_bus", "bus_id": "uuid-of-bus"}
```
Receive: `{"type": "subscription_confirmed", "channel": "bus_uuid"}`

**Step 3** — Receive live location updates
As the driver sends GPS coordinates, all subscribers on that bus channel receive:
```json
{
  "type": "bus_location_update",
  "bus_id": "...",
  "latitude": 36.7538,
  "longitude": 3.0588,
  "speed": 28.5,
  "nearest_stop": "Bab Ezzouar University",
  "passenger_count": 23
}
```

**Step 4** — Subscribe to a line (all buses on a route)
```json
{"type": "subscribe_to_line", "line_id": "uuid-of-line"}
```

**Step 5** — Subscribe to personal notifications
```json
{"type": "subscribe", "channel": "notifications", "user_id": "user-uuid"}
```

**Heartbeat** — Keep-alive
```json
{"type": "heartbeat"}
```
→ `{"type": "heartbeat_response", "timestamp": "..."}`

**Issues:**
- If Redis goes down, WebSocket connections fail silently. No error is surfaced to the client.
- No "bus went offline" event when a driver stops sending GPS.
- No last-known-location for buses that stopped tracking.

---

#### Workflow P4: Reporting Waiting Count

**Step 1** — Submit a waiting report
`POST /api/v1/tracking/waiting-reports/`
```json
{
  "stop": "stop-uuid",
  "bus": "bus-uuid",
  "line": "line-uuid",
  "reported_count": 15
}
```
Returns `201 Created`. Confidence score is calculated using the reporter's `trust_multiplier`.

**Rate limit:** Only 1 report per 10 minutes at the same stop per user. First reporter takes the coin opportunity.

**Step 2** — Await driver verification
`GET /api/v1/tracking/waiting-reports/?status=pending&line=line-uuid` (from driver session)

**Step 3** — Driver verifies or rejects
`POST /api/v1/tracking/waiting-reports/{id}/verify/`
```json
{"status": "correct", "actual_count": 14}
```

**Step 4** — Coin reward distributed
`GET /api/v1/tracking/virtual-currency/my_balance/`

**Reputation level thresholds:**

| Level | Trust Multiplier | Min accuracy_rate |
|-------|-----------------|------------------|
| Bronze | 0.5x | 0% |
| Silver | 1.0x | 50% |
| Gold | 1.5x | 70% |
| Platinum | 2.0x | 90% |

`accuracy_rate = correct_reports / total_reports`

**Issues:**
- Requires `bus` OR `line` — passengers at a stop don't always know which bus is coming. Should be optional.
- "Race to report" dynamic: only the first reporter earns coins at a stop in each 10-minute window.

---

#### Workflow P5: Joining a Waiting List

**Step 1** — Join waiting list for a specific bus at a stop
`POST /api/v1/tracking/bus-waiting-lists/`
```json
{
  "bus": "bus-uuid",
  "stop": "stop-uuid"
}
```

**Step 2** — Receive arrival push notification when bus approaches.

**Step 3** — Leave the waiting list
`DELETE /api/v1/tracking/bus-waiting-lists/{id}/`

**Issues:** Requires knowing the specific bus UUID. In practice, passengers wait for "the next Line 36 bus" — not a specific bus ID. This workflow is practically unusable without foreknowledge of the bus UUID.

---

#### Workflow P6: Gamification Lifecycle

**Earning coins:**
- Accurate waiting count reports (base ≥ 50 coins × reputation multiplier)
- Consistency bonuses (multiple reports in a session)
- Early adopter bonuses (first report at a stop in a period)

**Check balance:**
`GET /api/v1/tracking/virtual-currency/my_balance/`
```json
{"balance": 250, "lifetime_earned": 430, "lifetime_spent": 180}
```

**View reputation:**
`GET /api/v1/tracking/reputation/my_stats/`
```json
{
  "total_reports": 42,
  "correct_reports": 38,
  "reputation_level": "gold",
  "trust_multiplier": 1.5,
  "accuracy_rate": 0.905
}
```

**Purchase premium features:**
`POST /api/v1/tracking/user-premium-features/`
```json
{"feature": "feature-uuid", "coins_to_spend": 500}
```

**View leaderboard (gamification app):**
`GET /api/v1/gamification/leaderboards/?period=weekly`

⚠️ This leaderboard tracks `total_points` from `apps/gamification/UserProfile`, which are NEVER incremented by real app actions (waiting reports, trips, etc.). The leaderboard is populated with all zeros.

---

#### Workflow P7: Offline Usage

**Pre-cache data:**
`GET /api/v1/offline/sync-config/`
Client caches: line routes, stop coordinates, schedules.

**Queue actions while offline:**
Local device stores waiting count reports, profile updates, etc.

**On reconnect — sync:**
`POST /api/v1/offline/sync/`
```json
{
  "actions": [
    {"type": "waiting_report", "data": {...}}
  ]
}
```

**Issues:**
- Sync endpoint has `throttle_classes = []` — a potential abuse vector (see Section 4.2 GAP-6).
- No conflict resolution when offline actions contradict current server state.
- Sync implementation is incomplete.

---

#### Workflow P8: Notifications

**Configure preferences:**
`PATCH /api/v1/notifications/preferences/{id}/`
```json
{
  "push_enabled": true,
  "email_enabled": false,
  "sms_enabled": false
}
```

**View notifications:**
`GET /api/v1/notifications/notifications/?is_read=false`

**Mark as read:**
`PATCH /api/v1/notifications/notifications/{id}/mark_read/`

**Issues:**
- No line-targeted broadcast for service disruptions.
- Notification creation is admin-only — drivers cannot notify passengers about delays.

---

#### Workflow P9: Rating a Driver

**Submit rating after a trip:**
`POST /api/v1/drivers/ratings/`
```json
{
  "driver": "driver-uuid",
  "rating": 4,
  "comment": "Driver was punctual but the bus was crowded"
}
```
Returns `201 Created`.

**View all ratings for a specific driver:**
`GET /api/v1/drivers/drivers/{id}/ratings/` — **RETURNS 500 ERROR** (breaking bug, see Section 4.1 BUG-1)

**Workaround:**
`GET /api/v1/drivers/ratings/?driver={id}` — flat endpoint, works correctly.

---

### 3.2 Driver Workflows

---

#### Workflow D1: Driver Registration

**Step 1** — Register with documents (multipart form)
`POST /api/v1/accounts/register-driver/` **OR** `POST /api/v1/drivers/drivers/register/`

⚠️ **Two endpoints exist for the same operation.** See Section 4.3 DUPLICATE-2.

```
Content-Type: multipart/form-data

email, password, first_name, last_name, phone_number
id_card_number, id_card_photo (file)
driver_license_number, driver_license_photo (file)
years_of_experience (integer)
```
Returns `201 Created` with `status = "pending"`.

**Step 2** — Login
`POST /api/v1/token/`

**Step 3** — Check registration status
`GET /api/v1/drivers/drivers/profile/`
```json
{"status": "pending", "rejection_reason": null, ...}
```

**Step 4** — Wait for admin approval.
No push notification to inform the driver when approved. Driver must poll their profile.

---

#### Workflow D2: After Admin Approval — Setup

**Step 1** — Register a bus
`POST /api/v1/buses/buses/`
```json
{
  "license_plate": "16-25123-Alger",
  "model": "Mercedes O345",
  "manufacturer": "Mercedes-Benz",
  "year": 2015,
  "capacity": 45,
  "average_speed": 30
}
```
Returns `201 Created`, `status = "inactive"` (awaits admin approval).

**Step 2** — Wait for bus approval (separate admin approval step).

**Step 3** — Mark availability
`POST /api/v1/drivers/drivers/{id}/update_availability/`
Returns: `{"detail": "Availability updated"}` — ⚠️ no driver object returned, requires a follow-up GET.

---

#### Workflow D3: Starting a Trip

`POST /api/v1/tracking/trips/`
```json
{
  "bus": "bus-uuid",
  "line": "line-uuid",
  "start_stop": "stop-uuid"
}
```
Returns `201 Created` with trip object including `"is_completed": false`.

**Issues:**
- Rejected drivers (status=`rejected`) can still create trips — only pending is blocked.
- No concurrent trip check — same bus can have 2+ active trips.
- No ownership check — any driver can start a trip on any bus.

---

#### Workflow D4: During a Trip — GPS Updates

**Send location update:**
`POST /api/v1/tracking/locations/`
```json
{
  "bus": "bus-uuid",
  "latitude": 36.7538,
  "longitude": 3.0588,
  "speed": 28.5,
  "heading": 245,
  "accuracy": 5.0,
  "trip_id": "trip-uuid"
}
```
Server broadcasts to all WebSocket subscribers on this bus/line channel.

**Update passenger count:**
`POST /api/v1/tracking/passenger-counts/`
```json
{
  "bus": "bus-uuid",
  "count": 28,
  "capacity": 45,
  "trip_id": "trip-uuid"
}
```
`occupancy_rate = min(count/capacity, 1.0)` stored.

**Issues:** Two separate location models exist (`LocationUpdate` in tracking, `BusLocation` in buses). Five separate passenger count mechanisms. See Section 4.3.

---

#### Workflow D5: Verifying Waiting Reports

**View pending reports for current line:**
`GET /api/v1/tracking/waiting-reports/?status=pending&line={line-uuid}`

**Verify a report:**
`POST /api/v1/tracking/waiting-reports/{id}/verify/`
```json
{"status": "correct", "actual_count": 14}
```
Options: `correct`, `incorrect`, `partially_correct`.

Driver earns coins via `driver_verification` transaction type for each verification.

---

#### Workflow D6: Ending a Trip

`POST /api/v1/tracking/trips/{id}/end/`

Trip statistics calculated by `TripService.end_trip()`:
- `distance_km`: computed from GPS location history
- `average_speed`: distance / duration
- `max_passengers`: peak from `PassengerCount` records
- `total_stops`: unique stops visited

Returns:
```json
{
  "id": "...",
  "is_completed": true,
  "end_time": "2026-03-11T09:15:00Z",
  "distance": "12.400",
  "average_speed": "27.5"
}
```

**Remaining bug:** `TripService.end_trip()` can overflow `DecimalField` constraints when GPS drift produces unrealistically large distances or speeds.

---

#### Workflow D7: Performance Tracking

`GET /api/v1/tracking/driver-performance/my_stats/`

⚠️ Stats are nested under a `performance_score` key — inconsistent with all other endpoints:
```json
{
  "performance_score": {
    "total_trips": 142,
    "on_time_trips": 128,
    "performance_level": "expert",
    "safety_score": 88.5,
    "passenger_rating": 4.2,
    "current_streak": 7
  }
}
```

**Performance levels:** `rookie → experienced → expert → master`

---

### 3.3 Admin Workflows

---

#### Workflow A1: Driver Approval

```
GET /api/v1/drivers/drivers/?status=pending
POST /api/v1/drivers/drivers/{id}/approve/
POST /api/v1/drivers/drivers/{id}/reject/  {"rejection_reason": "..."}
```

**Issue:** No re-application flow. Once rejected, driver is permanently locked out. See Section 4.5 MISSING-8.

---

#### Workflow A2: Bus Approval

```
GET /api/v1/buses/buses/?is_approved=false
POST /api/v1/buses/buses/{id}/approve/
POST /api/v1/buses/buses/{id}/reject/
```

Two separate approval steps (driver + bus) add friction for legitimate new registrations.

---

#### Workflow A3: Line and Stop Management

**Create stop:**
`POST /api/v1/lines/stops/`
```json
{
  "name": "Bab Ezzouar University",
  "latitude": 36.7538,
  "longitude": 3.0588,
  "address": "Bab Ezzouar, Algiers"
}
```

**Create line:**
`POST /api/v1/lines/lines/`
```json
{"name": "Ligne 36", "code": "36", "color": "#FF5733", "frequency": 15}
```

**Add stop to line (with ordering):**
`POST /api/v1/lines/line-stops/`
```json
{"line": "line-uuid", "stop": "stop-uuid", "order": 1, "distance_from_previous": 850}
```

**Set service schedule:**
`POST /api/v1/lines/schedules/`
```json
{"line": "line-uuid", "day_of_week": 0, "start_time": "06:00:00", "end_time": "22:00:00", "frequency_minutes": 15}
```

**Issue:** Fixed schedule model is inappropriate for Algerian buses. See Section 4.4 USELESS-4.

---

#### Workflow A4: System Monitoring

```
GET /api/v1/tracking/active-buses/       — Buses with active trips
GET /api/v1/tracking/anomalies/          — Service anomalies
POST /api/v1/tracking/anomalies/{id}/resolve/
POST /api/v1/notifications/notifications/ — Broadcast alert
POST /api/v1/tracking/virtual-currency/{id}/add/  — Adjust user coins
```

---

## 4. Critical Issues Found

### 4.1 Breaking Bugs

---

#### BUG-1: `GET /api/v1/drivers/drivers/{id}/ratings/` → 500 Internal Server Error

**Root cause:** The `ratings` action on `DriverViewSet` applies `DriverRatingFilter` with an invalid argument — a `TypeError` occurs during filter initialization.

**Impact:** Every attempt to view a specific driver's ratings crashes. This is the most user-visible social feature (driver star ratings, like Uber/InDriver). It is completely broken.

**Fix:**
```python
# In the ratings action:
queryset = DriverRating.objects.filter(driver=driver_instance)
# Apply filtering manually, or fix the DriverRatingFilter instantiation
```

**Workaround:** Use `GET /api/v1/drivers/ratings/?driver={id}` — flat endpoint works correctly.

---

#### BUG-2: `POST /api/v1/drivers/drivers/{id}/ratings/` → 405 Method Not Allowed

**Root cause:** The nested `ratings` action on `DriverViewSet` is GET-only. No POST route exists on the nested endpoint.

**Impact:** Passengers cannot submit ratings via the natural nested URL. The only working path is `POST /api/v1/drivers/ratings/` with a `driver` field in the body.

**Fix:** Either add `@action(methods=['post'], ...)` to the nested action, or clearly document the flat endpoint as canonical and remove the nested URL from documentation.

---

#### BUG-3: `TripService.end_trip()` — Decimal Field Overflow

**Root cause:** When `average_speed = distance_km / duration_hours`, GPS drift during a long trip (or near-zero duration) can produce a float that exceeds the `DecimalField` constraints on `Trip.distance` or `Trip.average_speed`.

**Impact:** Trip end fails. The driver cannot close their trip; it stays active indefinitely.

**Fix:** Clamp values before saving:
```python
distance_km = min(calculated_distance, 500.0)   # max 500 km trip
average_speed = min(calculated_speed, 120.0)    # max 120 km/h
```

---

#### BUG-4: `IsApprovedDriver` Allows Rejected Drivers

**Root cause:** The permission check tests `driver.status != 'pending'` rather than `driver.status == 'approved'`.

**Impact:** A driver rejected for falsified documents can still create trips and operate in the system.

**Fix (one-line):**
```python
# apps/core/permissions.py or tracking views
return request.user.driver.status == 'approved'
```

---

#### BUG-5: `GET /api/v1/lines/stops/nearby/` Returns Raw Array

**Root cause:** The `nearby` action returns a plain list instead of a paginated response dict.

**Impact:** Any client code that destructures the response as `{"count": ..., "results": [...]}` will crash with a `TypeError`. The Flutter frontend must special-case this endpoint.

**Fix:** Wrap the response in the standard paginated format, or document explicitly that this endpoint returns a raw array.

---

### 4.2 Security & Business Logic Gaps

---

#### GAP-1: Concurrent Trip Prevention — Missing

The same bus can have multiple active (`is_completed=False`) trips simultaneously. Two drivers can both call `POST /tracking/trips/` for the same bus and both receive `201 Created`.

**Impact:** GPS data, passenger counts, and waiting report verifications become ambiguous — the system cannot determine which trip a location update belongs to.

**Fix:**
```python
# In TripViewSet.perform_create():
if Trip.objects.filter(bus=bus, is_completed=False).exists():
    raise ValidationError("This bus already has an active trip.")
```

---

#### GAP-2: No Driver–Bus Ownership Validation

No check that the driver starting a trip is assigned to (or owns) the specified bus.

**Impact:** Driver A can start a trip on Driver B's bus if they know its UUID.

**Fix:**
```python
if serializer.validated_data['bus'].driver != request.user.driver:
    raise PermissionDenied("You are not authorized to use this bus.")
```

---

#### GAP-3: No Email or Phone Verification

Accounts are immediately active after registration. No email or SMS confirmation required.

**Impact:** Anyone can create unlimited fake accounts to farm coins from the waiting count gamification system. Each new account gets a fresh `VirtualCurrency` balance.

**Fix:** Require email verification before a passenger account can submit waiting reports or earn coins.

---

#### GAP-4: Offline Sync Exempt from Throttling

`throttle_classes = []` on `/api/v1/offline/sync/` means sync calls bypass the 60 req/min rate limit.

**Impact:** A user can queue 1000 waiting reports offline and flush them all in a single sync call, bypassing anti-spam protections entirely.

**Fix:** Apply a separate, higher-limit throttle class to the sync endpoint (e.g., `200 req/min` burst allowed, but each synced action counts toward the standard per-action limit).

---

#### GAP-5: No Bus Capacity Validation

`POST /tracking/passenger-counts/` with `count=999` on a 45-seat bus returns `201`.

**Context:** In Algeria, standing passengers are normal (see Section 5.1). Strict enforcement is wrong. However, `999` is clearly erroneous data.

**Fix:** Validate `count ≤ capacity × 2`. Flag (but don't reject) values above capacity — mark as `occupancy_status = "overcrowded"`.

---

#### GAP-6: No Waiting Report Consistency Check

A report can specify a `stop`, `bus`, and `line` where the stop is not on the line, or the bus is not on the line. The system accepts this without validation.

**Impact:** Garbage data enters the verification pipeline. Drivers may be asked to verify reports about unrelated services.

---

### 4.3 Duplicate Features (Major Architectural Issue)

---

#### DUPLICATE-1: Two Complete, Unconnected Gamification Systems

The single biggest architectural problem in this codebase:

**System A — `apps/tracking/` gamification (active and working):**

| Component | Model | Status |
|-----------|-------|--------|
| Coins | `VirtualCurrency` + `CurrencyTransaction` (21 types) | Active — incremented by waiting reports |
| Reputation | `ReputationScore` | Active — updated on verification |
| Driver performance | `DriverPerformanceScore` | Active — updated on trip end |
| Premium features | `PremiumFeature` + `UserPremiumFeature` | Active — purchasable with coins |

**System B — `apps/gamification/` (disconnected, likely dead code):**

| Component | Model | Status |
|-----------|-------|--------|
| Points | `UserProfile.total_points` + `PointTransaction` (7 types) | Dead — never incremented |
| Experience | `UserProfile.experience_points` + levels | Dead — never updated |
| Achievements | `Achievement` + `UserAchievement` | Dead — never awarded |
| Challenges | `Challenge` + `UserChallenge` | Dead — `current_value` never auto-updated |
| Rewards | `Reward` + `UserReward` | Dead — no redemption infrastructure |
| Leaderboard | `Leaderboard` | Dead — all points = 0 |
| Carbon saved | `UserProfile.carbon_saved` | Dead — never calculated |

System B has no connection to `WaitingCountReport`, `Trip`, or any real user action. Its `PointTransaction` types (`trip_complete`, `achievement`, `daily_bonus`) are never triggered. Its `Reward` types (`free_ride`, `merchandise`, `discount`) have no redemption infrastructure.

**Conclusion:** `apps/gamification/` is dead code — almost certainly copied from another project. It adds model complexity, migration overhead, and developer confusion with zero functional value.

---

#### DUPLICATE-2: Two Driver Registration Endpoints

| Endpoint | App |
|----------|-----|
| `POST /api/v1/accounts/register-driver/` | `apps/accounts/` |
| `POST /api/v1/drivers/drivers/register/` | `apps/drivers/` |

Both do the same operation. If validation logic diverges between them (one adds a new required field, the other doesn't), bugs will be hard to trace. Clients must pick one and there is no documentation indicating which is canonical.

**Fix:** Keep `POST /api/v1/accounts/register-driver/` as the canonical registration URL (consistent with passenger registration at `/accounts/register/`). Mark the drivers endpoint as deprecated.

---

#### DUPLICATE-3: Two Bus Tracking Start Endpoints

| Endpoint | App |
|----------|-----|
| `POST /api/v1/buses/buses/{id}/start_tracking` | `apps/buses/` |
| `POST /api/v1/tracking/bus-lines/start_tracking` | `apps/tracking/` |

Both initiate tracking for a bus on a line. The `BusLine` model adds a persistent "assignment" layer on top of `Trip`, but the distinction between "bus-line assignment" and "trip" is never clearly documented.

---

#### DUPLICATE-4: Three Waiting/Passenger Systems

| Model | Purpose | Status |
|-------|---------|--------|
| `WaitingPassengers` | Simple count: N passengers waiting at a stop | Legacy / admin-set |
| `BusWaitingList` | Per-user join/leave for a specific bus | Active |
| `WaitingCountReport` | Crowdsourced reports with verification & coins | Active |

These are related but distinct concepts. A developer reading the code must guess which one to use for a given feature. None of them cross-reference the others. The API has three separate list endpoints for them.

**Fix:** Write clear docstrings for each model explaining when to use it. Cross-link them in the API documentation.

---

#### DUPLICATE-5: Five Passenger Count Tracking Mechanisms

| Mechanism | Location |
|-----------|----------|
| `PassengerCount` model | `apps/tracking/` (timestamped history) |
| `BusLocation.passenger_count` | `apps/buses/` (embedded in location record) |
| `Bus.current_passenger_count` property | `apps/buses/` |
| `POST /buses/buses/{id}/update_passenger_count/` | `apps/buses/` |
| `POST /tracking/passenger-counts/` | `apps/tracking/` |

At any given moment, there are at least 3 different "current passenger count" values for a bus that could disagree with each other.

**Fix:** One canonical write path: `POST /tracking/passenger-counts/`. One canonical read: latest `PassengerCount` record. Everything else is removed.

---

#### DUPLICATE-6: Two GPS Location Models

| Model | App | Fields |
|-------|-----|--------|
| `LocationUpdate` | `apps/tracking/` | lat, lon, speed, heading, accuracy, trip_id, nearest_stop, distance_to_stop, line |
| `BusLocation` | `apps/buses/` | lat, lon, altitude, speed, heading, accuracy, is_tracking_active, passenger_count |

Both record bus GPS positions. `LocationUpdate` is richer (trip context, nearest stop). `BusLocation` has `is_tracking_active` and `passenger_count` (which itself duplicates `PassengerCount`).

**Fix:** `LocationUpdate` is the canonical GPS record. `BusLocation` is removed or merged.

---

### 4.4 Useless/Misfit Features

---

#### USELESS-1: `apps/gamification/` — Entire App Is Dead Code

As established in DUPLICATE-1, no real user action triggers any `apps/gamification/` model update.

Specifically dead:
- `Achievement.check_achievements()` is called from `UserProfile.add_points()` — but `add_points()` is never called from any view, signal, or task connected to the actual app flows.
- `Challenge.current_value` is never auto-updated. There is no Celery task evaluating challenge progress.
- `Reward` redemption codes are generated on `UserReward` creation, but there is no partner, payment gateway, or external system to accept these codes.
- `UserProfile.carbon_saved` is never written. Every user has `carbon_saved = 0`.
- `Leaderboard` records are never created. All point totals are 0.

---

#### USELESS-2: Driver Premium Features

The `PremiumFeature` model includes driver-targeted features: `fuel_optimization`, `earnings_tracker`, `schedule_optimizer`, `maintenance_alerts`, `competition_stats`.

**Why these are inappropriate for Algeria:**
- **Salaried ETUSA/STPE drivers**: Receive fixed salary. "Earnings tracker" is irrelevant. "Competition stats" cannot affect their pay or performance review.
- **Private operators**: Own their bus, operate a fixed licensed line. They manage fuel and maintenance through their own accounting — an in-app feature won't be trusted for business decisions.
- **"Competition stats"**: In public transit, encouraging drivers to "compete" creates dangerous incentives: speeding, skipping stops, refusing passengers at non-profitable stops.
- **Coin cost to unlock**: Drivers earn coins by verifying waiting reports. Expecting them to spend those coins on a maintenance alert feature is an absurd value proposition.

---

#### USELESS-3: `RouteSegment.polyline` — Never Populated

The `RouteSegment` model stores encoded Google Maps API polylines between adjacent stops. `route_service.py` falls back to straight-line connections when no segment exists.

**Reality:** Algeria has tens of thousands of stop-to-stop segments. Each polyline requires a Google Maps API call or manual drawing. No bulk import tool, no Celery task, and no admin interface exists to populate them. They will never be populated in any realistic deployment.

**Fix:** Simplify `RouteSegment` to store only `distance` (km) and `duration` (minutes) — values that can be computed from GPS trip history rather than external API calls. Remove the `polyline` field.

---

#### USELESS-4: `Schedule` Model — Fixed Timetables Don't Exist in Algeria

The `Schedule` model stores `day_of_week`, `start_time`, `end_time`, `frequency_minutes`, implying buses follow a fixed timetable.

**Reality:** As described in Section 1, Algerian buses run on approximate headways at best. Private operators run when they have passengers. ETUSA has approximate schedules but misses them regularly.

**Result:** Schedules will be left empty by operators (because they don't have them), or filled with approximate values that will be wrong half the time, eroding passenger trust in the app.

**Recommendation:** Replace schedule-based ETA with headway + live GPS ETA only. Add a simple `is_operating_now` boolean that drivers toggle at service start/end.

---

#### USELESS-5: `Anomaly` — Admin-Only Creation Kills the Value

The `Anomaly` model records service anomalies (speed violations, route deviations, schedule gaps, bunching). But only admins can create anomaly records.

**Result:** Admins must detect anomalies themselves by watching `active-buses` data. There is no crowdsourcing. The model's potential for "passengers report broken buses" or "drivers report road blockages" is completely unused.

**Fix:** Allow drivers to create anomalies of types `breakdown`, `route_blocked`, `detour`. Allow passengers to report `crowded_beyond_safe`, `driver_behavior`, `bus_breakdown`.

---

### 4.5 Missing Features (Critical Gaps)

---

#### MISSING-1: Journey Planning / Route Search [CRITICAL]

**Gap:** "I want to go from Stop A to Stop B — which bus do I take?"

This is **the most fundamental feature of a transit app**. Without it, the app is a real-time GPS viewer, not a transit planning tool. Every major transit app (Google Maps, Moovit, Citymapper) leads with journey planning.

**Current state:** The API is entirely bus-centric. You look up a bus and see where it goes. You cannot look up a destination and find which bus serves it.

**What's needed:**
```
GET /api/v1/lines/journey/?from_stop=stop-a-uuid&to_stop=stop-b-uuid
→ [
    {
      "line": "Ligne 36",
      "board_at": "Bab Ezzouar University",
      "alight_at": "El Harrach",
      "stops_count": 8,
      "estimated_duration_minutes": 25,
      "next_bus": {
        "bus_id": "...",
        "eta_minutes": 7,
        "occupancy_rate": 0.6
      }
    }
  ]
```

**Implementation path:** `LineStop` already stores stop order on each line. A graph traversal (ordered stop search for single-line journeys, Dijkstra for multi-line) finds valid routes. Single-line cases cover ~80% of real queries.

---

#### MISSING-2: Fare / Price Information

No pricing data exists anywhere in the system.

Algerian bus fares: ETUSA city bus ~25 DZD; private operators 30–80 DZD by distance.

**What's needed:** Add `fare_dza` to `Line`. For distance-based fares, `LineStop` can hold a cumulative fare field.

---

#### MISSING-3: Bus Type

No `bus_type` field on `Bus`.

Algeria has: **Microbus** (14-seat), **City bus** (60–90 seat), **Articulated bus** (180-seat). Type affects capacity, boarding behavior, and what a passenger expects.

**Fix:** `bus_type = CharField(choices=['microbus', 'city_bus', 'articulated', 'minibus'])`

---

#### MISSING-4: Operator / Company Management

No operator/company model. Buses are individually owned by drivers, modeling an Uber-like gig economy rather than a transit system.

**Reality:** ETUSA owns a fleet. Private companies operate licensed lines. Drivers are employed by operators.

**Minimum needed:**
```python
class Operator(BaseModel):
    name = CharField(max_length=200)
    operator_type = CharField(choices=['public', 'private'])
    wilaya = CharField(max_length=50)
    license_number = CharField(max_length=100, unique=True)

# Bus.operator = ForeignKey(Operator)
# Driver.operator = ForeignKey(Operator, null=True)
```

---

#### MISSING-5: Service Disruption Broadcasts

No mechanism to announce "Line 36 suspended until 18:00" to all affected passengers. The `Anomaly` model exists but has no push notification delivery to line subscribers.

**What's needed:**
- `ServiceDisruption` model: `line`, `type` (suspension/delay/diversion), `start_time`, `end_time`, `description`
- Celery task: on creation, push to all passengers who have recently tracked or reported on the affected line

---

#### MISSING-6: Wilaya / Commune Geographic Organization

No geographic hierarchy. All 58 wilayas' lines appear in one undifferentiated list.

A user in Oran should not scroll through Algiers lines by default.

**Fix:** Add `wilaya` field to `Stop`. Filter all line/stop list endpoints by `wilaya`. Add `wilaya` preference to `Profile`.

---

#### MISSING-7: Last Known Location for Inactive Buses

When a bus stops sending GPS (trip ended, app crash, connectivity lost), it disappears from the map. Passengers see nothing.

**Fix:** Store `last_seen_at` + last coordinates on `Bus`. Include recently-inactive buses in `GET /tracking/active-buses/` with a `"status": "inactive_since_Xm"` flag.

---

#### MISSING-8: Driver Re-Application After Rejection

Rejected drivers have no mechanism to correct their documents and re-apply.

**Fix:** A `reapply` action that:
1. Allows uploading new ID/license photos
2. Resets status to `pending`
3. Notifies admin of re-submission

---

#### MISSING-9: Passenger Incident Reporting

Passengers can only report waiting counts. They cannot report: bus breakdown, driver behavior, route deviation, safety incident. Only admins can create `Anomaly` records.

---

#### MISSING-10: Aggregated Stop-Level View

No endpoint for "all buses currently approaching Stop X with their occupancy."

This is what a passenger at a stop actually needs. `GET /tracking/routes/arrivals/?stop_id=X` partially covers this but does not include occupancy data.

---

### 4.6 Confusing / Illogical Workflows

---

#### CONFUSING-1: Waiting Report Requires Bus or Line — Not Stop-Only

A passenger at a stop in Algeria often waits for "whichever bus comes first." Requiring `bus_id` or `line_id` forces them to know details they don't have. The stop alone should be sufficient for a report.

---

#### CONFUSING-2: Driver Owns Their Bus — Wrong Mental Model

The current flow (driver creates and owns a bus) models Uber, not public transit. In Algerian reality, buses belong to operators (ETUSA, private companies) and are assigned to drivers by dispatch — sometimes daily. The `Bus.driver` foreign key is semantically ambiguous: does it mean "this bus belongs to this driver" or "this driver is currently assigned to this bus"?

---

#### CONFUSING-3: `update_availability` Returns No Driver Object

`POST /api/v1/drivers/drivers/{id}/update_availability/`
→ `{"detail": "Availability updated"}`

Client must make a follow-up `GET` to learn the new availability state. This violates the REST principle of returning the updated resource.

**Fix:** Return the full driver object in the response.

---

#### CONFUSING-4: Three Separate Leaderboard Concepts

1. `apps/gamification/Leaderboard` — tracks `total_points` (never incremented)
2. `apps/tracking/VirtualCurrency` — coins (actual earned currency, sortable)
3. `apps/tracking/DriverPerformanceScore` — performance level ranking

Three leaderboards, none synchronized, no documentation of which represents what. The gamification leaderboard shows all zeros.

---

#### CONFUSING-5: `BusLine` vs `Trip` — Undefined Distinction

`BusLine` links a bus to a line with a `tracking_status`. `Trip` links a bus to a line with a driver, start time, end time, and `is_completed`. Both model "a bus operating on a line." The difference is never clearly defined. Querying "is this bus currently on this line?" requires checking both models.

---

#### CONFUSING-6: Premium Feature Expiry Is Pull-Based

`UserPremiumFeature.deactivate_if_expired()` runs only when the feature is accessed — not on a schedule. An expired feature appears "active" in list views until the user tries to use it. No notification is sent on expiry. No renewal flow exists.

**Fix:** Add a daily Celery task that deactivates expired features and sends push notifications.

---

#### CONFUSING-7: Race-to-Report Perverse Incentive

At a busy Algiers stop with 20 waiting passengers, only the first reporter earns coins. The remaining 19 earn nothing. This discourages reporting at busy stops — exactly where accurate data is most valuable.

**Better approach:** Allow multiple reports per stop per window. Award diminishing returns: 1st reporter 100%, 2nd 70%, 3rd 40%, 4th+ 20%. Aggregate reports increase the collective confidence score.

---

## 5. Algeria-Specific Analysis

### 5.1 Standing Passengers — Capacity Is Not a Hard Limit

Algerian buses regularly carry standing passengers. Overcrowding at peak hours in Algiers is the norm, not an exception.

**Design implication:** Strict capacity enforcement is wrong. The current behavior (accepting count > capacity) is actually more realistic. The only reasonable validation is rejecting physically impossible values (`count > capacity × 2`). Occupancy should show "overcrowded" status rather than rejecting the update.

### 5.2 Cash-Only Economy — No Ticketing Required

Algeria's bus system is almost entirely cash-based. Digital payments on transit exist only in limited, recent pilot programs.

**Implication:** The `Reward` types in `apps/gamification/` include `free_ride` — implying integration with a ticketing system that does not exist. Coin-based rewards should be social and cosmetic (badges, leaderboard position), not economic (free rides, discounts).

### 5.3 Formal vs Informal Operators

- **ETUSA / public operators**: Fixed routes, marked stops, modelable in the current `Line`/`Stop` system.
- **Private licensed operators**: Generally follow their route but may deviate on demand. The strict `LineStop` ordering model doesn't fully capture their behavior.
- **Clandestins**: No fixed route. Cannot be modeled. Any data from these services is unattributable.

**Implication:** The system needs an `operator_type` field to apply different validation rules. A clandestin driver cannot be registered because they have no license number.

### 5.4 Language — Darija vs Classical Arabic

The app supports `fr`, `ar`, `en`. However, most urban Algerian commuters speak **Darija** (Algerian Arabic dialect), which is distinct from Classical Arabic. The `ar` locale will feel formal and unfamiliar. French (`fr`) is the better default for urban users.

Many bus line names and stop names are in French or a French-Arabic mix (e.g., "Ligne 36", "Place des Martyrs"). Forcing Classical Arabic transliterations would make them unrecognizable.

### 5.5 Device Constraints — Mid-Range Android

Primary users: Android 8–12, 2–3 GB RAM, variable 3G/4G connectivity.

**Implications:**
- WebSocket reconnection must be robust — frequent disconnects are expected.
- GPS update intervals should be configurable (10-second intervals drain battery on mid-range devices).
- Offline mode is not optional — it is essential for suburban and rural areas.
- API responses should minimize unused fields in list views.

### 5.6 Why Fixed Schedules Won't Work

Algerian buses run on approximate headways, not fixed timetables. Schedules will either be left empty or filled with approximate values that miss reality, destroying trust in ETA features.

**Recommendation:** Base all ETAs exclusively on live GPS data. If no bus is tracked, display "No live data available" instead of a schedule-derived fake arrival time.

### 5.7 Algeria Has 58 Wilayas — Geographic Scoping Is Essential

Without wilaya-level organization, a user in Tlemcen scrolls through hundreds of Algiers bus lines. Any national deployment requires geographic filtering as a first-class feature.

### 5.8 Gamification Cultural Fit

Algerian commuters are smartphone-literate and socially competitive (Instagram, TikTok penetration is very high). The leaderboard and reputation mechanics are culturally appropriate.

However:
- Virtual coins redeemable for "merchandise" or "free rides" feel abstract and untrustworthy in a low-digital-trust environment.
- "Competition stats" for drivers creates perverse transit incentives.
- Social recognition (public leaderboard rank, "Most Helpful Reporter" badge) is more culturally powerful than monetary-feeling rewards.

---

## 6. Prioritized Improvement Recommendations

### Priority 1 — Fix Immediately (Breaking Bugs)

| ID | Fix | File | Effort |
|----|-----|------|--------|
| P1-1 | Fix `DriverRatingFilter` TypeError → 500 on `GET /drivers/{id}/ratings/` | `apps/api/v1/drivers/views.py` | 1h |
| P1-2 | Fix nested POST 405 for driver ratings (add action or document flat endpoint) | `apps/api/v1/drivers/views.py` | 1h |
| P1-3 | Fix `TripService.end_trip()` Decimal overflow (clamp distance/speed) | `apps/tracking/services/trip_service.py` | 2h |
| P1-4 | Fix `IsApprovedDriver` to check `status == 'approved'`, not `!= 'pending'` | permissions file | 30min |
| P1-5 | Fix `GET /lines/stops/nearby/` to return paginated dict, not raw array | `apps/api/v1/lines/views.py` | 1h |

### Priority 2 — Fix Soon (Business Logic & Security)

| ID | Fix | Effort |
|----|-----|--------|
| P2-1 | Add concurrent trip prevention (one active trip per bus) | 2h |
| P2-2 | Add driver–bus ownership validation in trip creation | 1h |
| P2-3 | Return driver object from `update_availability` response | 30min |
| P2-4 | Add `count ≤ capacity × 2` validation in passenger count update | 1h |
| P2-5 | Add driver re-application endpoint after rejection | 3h |
| P2-6 | Add Celery task for auto-deactivating expired premium features + notification | 2h |
| P2-7 | Add throttle to offline sync endpoint | 1h |
| P2-8 | Add email verification requirement before coin earning | 4h |
| P2-9 | Add waiting report consistency check (stop must be on line, bus must be on line) | 2h |

### Priority 3 — Architectural Cleanup

| ID | Fix | Effort |
|----|-----|--------|
| P3-1 | Remove `apps/gamification/` (dead code) OR invest 5+ days to integrate it properly | 1–5 days |
| P3-2 | Consolidate dual driver registration to one canonical endpoint | 2h |
| P3-3 | Resolve `BusLine` vs `Trip` semantic conflict; remove one or document clearly | 4h |
| P3-4 | Consolidate dual GPS location models (`LocationUpdate` vs `BusLocation`) | 1 day |
| P3-5 | Consolidate five passenger count mechanisms into one canonical path | 1 day |
| P3-6 | Document the three waiting systems with cross-references | 2h |

### Priority 4 — New Features (Algeria-Specific, High Value)

| ID | Feature | Effort |
|----|---------|--------|
| P4-1 | Journey planning: `GET /lines/journey/?from=A&to=B` | 3–5 days |
| P4-2 | Fare/price field on `Line` and `LineStop` | 1 day |
| P4-3 | Bus type field (`microbus`, `city_bus`, `articulated`) | 4h |
| P4-4 | Operator/company model (Operator → Bus → Driver) | 2 days |
| P4-5 | Service disruption broadcasts targeted by line | 2 days |
| P4-6 | Wilaya/commune on `Stop` + location-based filtering | 1 day |
| P4-7 | Last known location for inactive buses | 1 day |
| P4-8 | Passenger incident/breakdown reporting | 2 days |
| P4-9 | Multi-reporter waiting reports with diminishing rewards | 1 day |
| P4-10 | Driver re-application flow after rejection | 1 day |

### Priority 5 — Consider Removing

| ID | Feature | Rationale |
|----|---------|-----------|
| P5-1 | `apps/gamification/` (if not integrating) | Dead code — maintainability risk |
| P5-2 | Driver premium features (fuel, earnings, competition) | Culturally inappropriate for Algeria |
| P5-3 | `UserProfile.carbon_saved` | Never populated, no calculation logic |
| P5-4 | `RouteSegment.polyline` | Will never be populated; straight lines are adequate |
| P5-5 | `Schedule` model strict timetabling | Replaced by headway + availability toggle |
| P5-6 | `Reward` (free rides, merchandise) | No infrastructure to redeem in Algeria |

---

## 7. Appendix — All Endpoints Reference

### Authentication

| Method | Endpoint | Auth Required | Notes |
|--------|----------|:---:|-------|
| POST | `/api/v1/token/` | No | Obtain JWT |
| POST | `/api/v1/token/refresh/` | No | Refresh access token |
| POST | `/api/v1/token/verify/` | No | Verify token validity |
| POST | `/api/v1/accounts/register/` | No | Passenger registration |
| POST | `/api/v1/accounts/login/` | No | Login |
| POST | `/api/v1/accounts/register-driver/` | No | ⚠️ Duplicate of drivers/register |
| GET | `/api/v1/accounts/profile/` | Yes | My profile |
| GET | `/api/v1/accounts/users/` | Yes | List users |
| GET | `/api/v1/accounts/users/{id}/` | Yes | Retrieve user |
| PATCH | `/api/v1/accounts/profiles/update_me/` | Yes | Update my profile |
| PATCH | `/api/v1/accounts/profiles/update_notification_preferences/` | Yes | Toggle notifications |

### Buses

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/buses/buses/` | List buses |
| POST | `/api/v1/buses/buses/` | Create bus (driver/admin) |
| GET | `/api/v1/buses/buses/{id}/` | Retrieve bus |
| PATCH | `/api/v1/buses/buses/{id}/` | Update bus |
| DELETE | `/api/v1/buses/buses/{id}/` | Delete bus (admin) |
| POST | `/api/v1/buses/buses/{id}/approve/` | Admin approve |
| POST | `/api/v1/buses/buses/{id}/reject/` | Admin reject |
| POST | `/api/v1/buses/buses/{id}/start_tracking` | ⚠️ Duplicate of tracking endpoint |
| POST | `/api/v1/buses/buses/{id}/update_passenger_count/` | ⚠️ Duplicate of tracking endpoint |
| GET | `/api/v1/buses/locations/` | List BusLocation records |
| POST | `/api/v1/buses/locations/` | ⚠️ Duplicate GPS model |

### Drivers

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/drivers/drivers/` | List drivers |
| GET | `/api/v1/drivers/drivers/{id}/` | Retrieve driver |
| POST | `/api/v1/drivers/drivers/register/` | ⚠️ Duplicate registration |
| POST | `/api/v1/drivers/drivers/{id}/approve/` | Admin approve |
| POST | `/api/v1/drivers/drivers/{id}/reject/` | Admin reject |
| POST | `/api/v1/drivers/drivers/{id}/update_availability/` | ⚠️ Returns no object |
| GET | `/api/v1/drivers/drivers/profile/` | My driver profile |
| GET | `/api/v1/drivers/drivers/{id}/ratings/` | **RETURNS 500** |
| POST | `/api/v1/drivers/drivers/{id}/ratings/` | **RETURNS 405** |
| GET | `/api/v1/drivers/ratings/` | All ratings (working) |
| POST | `/api/v1/drivers/ratings/` | Create rating (working) |
| GET | `/api/v1/drivers/ratings/{id}/` | Retrieve rating |

### Lines

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/lines/lines/` | List lines |
| POST | `/api/v1/lines/lines/` | Create line (admin) |
| GET | `/api/v1/lines/lines/{id}/` | Retrieve line |
| PATCH | `/api/v1/lines/lines/{id}/` | Update line |
| GET | `/api/v1/lines/lines/{id}/stops/` | Stops on line (ordered) |
| GET | `/api/v1/lines/lines/{id}/schedules/` | Line schedules |
| GET | `/api/v1/lines/stops/` | List stops |
| POST | `/api/v1/lines/stops/` | Create stop (admin) |
| GET | `/api/v1/lines/stops/{id}/` | Retrieve stop |
| PATCH | `/api/v1/lines/stops/{id}/` | Update stop |
| DELETE | `/api/v1/lines/stops/{id}/` | Delete stop |
| GET | `/api/v1/lines/stops/nearby/` | ⚠️ Returns raw array (not paginated) |
| GET | `/api/v1/lines/stops/{id}/lines/` | Lines through this stop |
| GET | `/api/v1/lines/schedules/` | List schedules |
| POST | `/api/v1/lines/schedules/` | Create schedule |

### Tracking

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/tracking/active-buses/` | Buses with active trips |
| GET | `/api/v1/tracking/bus-lines/` | Bus-line assignments |
| GET | `/api/v1/tracking/locations/` | GPS location history |
| POST | `/api/v1/tracking/locations/` | Log GPS location (driver) |
| GET | `/api/v1/tracking/passenger-counts/` | Occupancy history |
| POST | `/api/v1/tracking/passenger-counts/` | Log passenger count |
| GET | `/api/v1/tracking/trips/` | List trips |
| POST | `/api/v1/tracking/trips/` | Start trip (driver) |
| GET | `/api/v1/tracking/trips/{id}/` | Retrieve trip |
| POST | `/api/v1/tracking/trips/{id}/end/` | End trip (driver) |
| GET | `/api/v1/tracking/trips/history/` | My trip history (driver) |
| GET | `/api/v1/tracking/trips/{id}/statistics/` | Trip statistics |
| GET | `/api/v1/tracking/waiting-reports/` | List waiting count reports |
| POST | `/api/v1/tracking/waiting-reports/` | Submit report (passenger) |
| GET | `/api/v1/tracking/waiting-reports/{id}/` | Retrieve report |
| POST | `/api/v1/tracking/waiting-reports/{id}/verify/` | Verify report (driver) |
| GET | `/api/v1/tracking/bus-waiting-lists/` | Active waiting lists |
| POST | `/api/v1/tracking/bus-waiting-lists/` | Join waiting list |
| DELETE | `/api/v1/tracking/bus-waiting-lists/{id}/` | Leave waiting list |
| GET | `/api/v1/tracking/waiting-passengers/` | Simple waiting counts (legacy) |
| GET | `/api/v1/tracking/reputation/my_stats/` | My accuracy stats |
| GET | `/api/v1/tracking/virtual-currency/my_balance/` | My coin balance |
| POST | `/api/v1/tracking/virtual-currency/{id}/add/` | Admin coin adjustment |
| GET | `/api/v1/tracking/driver-performance/my_stats/` | ⚠️ Nested under `performance_score` key |
| GET | `/api/v1/tracking/premium-features/` | List purchasable features |
| POST | `/api/v1/tracking/user-premium-features/` | Purchase feature |
| POST | `/api/v1/tracking/user-premium-features/{id}/use/` | Mark feature used |
| GET | `/api/v1/tracking/routes/bus_route/` | Bus ETA + route |
| GET | `/api/v1/tracking/routes/arrivals/` | Arrivals at stop |
| GET | `/api/v1/tracking/routes/visualization/` | Route polyline data |
| GET | `/api/v1/tracking/routes/track_me/` | Driver's current route |
| GET | `/api/v1/tracking/anomalies/` | List anomalies |
| POST | `/api/v1/tracking/anomalies/` | ⚠️ Admin-only creation |
| POST | `/api/v1/tracking/anomalies/{id}/resolve/` | Mark resolved |

### Notifications

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/notifications/notifications/` | List notifications |
| POST | `/api/v1/notifications/notifications/` | Create notification (admin-only) |
| PATCH | `/api/v1/notifications/notifications/{id}/mark_read/` | Mark as read |
| GET | `/api/v1/notifications/device-tokens/` | My FCM tokens |
| POST | `/api/v1/notifications/device-tokens/` | Register FCM token |
| DELETE | `/api/v1/notifications/device-tokens/{id}/` | Remove token |
| GET | `/api/v1/notifications/preferences/` | My notification preferences |
| PATCH | `/api/v1/notifications/preferences/{id}/` | Update preferences |
| GET | `/api/v1/notifications/system/` | System notifications |

### Gamification (apps/gamification/ — LIKELY DEAD CODE)

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/gamification/user-profiles/` | Points always 0 |
| GET | `/api/v1/gamification/user-profiles/me/` | `carbon_saved` always 0 |
| GET | `/api/v1/gamification/achievements/` | Never awarded |
| GET | `/api/v1/gamification/user-achievements/` | Always empty |
| GET | `/api/v1/gamification/leaderboards/` | All rankings 0 |
| GET | `/api/v1/gamification/challenges/` | `current_value` never updated |
| POST | `/api/v1/gamification/user-challenges/` | Progress never auto-updated |
| GET | `/api/v1/gamification/rewards/` | No redemption infrastructure |
| POST | `/api/v1/gamification/user-rewards/` | Code generated but unverifiable |

### Offline

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/api/v1/offline/sync-config/` | Get cacheable data config |
| POST | `/api/v1/offline/sync/` | ⚠️ No throttle — sync queued actions |
| GET | `/api/v1/offline/queue/` | View pending sync queue |

### WebSocket (`ws://host:8007/ws`)

| Message Type | Direction | Required Fields |
|-------------|-----------|----------------|
| `connection_established` | Server → Client | `user_authenticated` |
| `subscribe_to_bus` | Client → Server | `bus_id` |
| `subscribe_to_line` | Client → Server | `line_id` |
| `subscribe` | Client → Server | `channel`, `user_id` |
| `heartbeat` | Client → Server | — |
| `subscription_confirmed` | Server → Client | `channel` |
| `heartbeat_response` | Server → Client | `timestamp` |
| `bus_location_update` | Server → Client | `bus_id`, lat, lon, speed, nearest_stop, passenger_count |
| `error` | Server → Client | `message` |

---

*End of DZ Bus Tracker API Comprehensive Expert Review*
*Document covers all 40 test phases from `api_test.py`, all known bugs from project memory, all duplicate systems, and full Algeria-specific context.*
*Codebase baseline: commit 747f984*
