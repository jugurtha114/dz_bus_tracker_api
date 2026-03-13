# DZ Bus Tracker — Full Project Audit

> Perspective: real Algerian bus operator & daily commuter.
> Covers: Django backend architecture, business logic, security, and completeness.
> Generated: 2026-03-13

---

## 1. Project Overview

DZ Bus Tracker is a real-time bus tracking system for Algerian cities. It serves three user roles:

| Role | Purpose |
|------|---------|
| **Passenger** | Track live bus positions, report waiting counts at stops, earn virtual currency for accurate reports, purchase premium features |
| **Driver** | Send GPS coordinates, manage trips (start/end), update passenger counts, verify passenger waiting reports, earn performance-based rewards |
| **Admin** | Approve/reject/suspend drivers, manage lines/stops/buses, view ridership analytics, resolve anomalies |

**Stack:** Django 5.2 + DRF, PostgreSQL, Redis, Celery, Django Channels (WebSocket via Uvicorn), JWT auth. Frontend is Flutter (not yet built — only an audit document exists at `dz_bus_tracker_frontend/`).

**Model hierarchy:**
```
BaseModel (UUID pk + timestamps)
├── User (custom auth, email login, user_type: admin/driver/passenger)
├── Profile (1:1 User — avatar, language, notification prefs)
├── Driver (1:1 User — ID card, license, approval status, rating)
├── DriverRating (FK Driver, FK User — 1-5 stars per day)
├── DriverStatusLog (audit trail for status changes)
├── Bus (FK Driver — plate, capacity, type, approval, features)
├── Stop (lat/lon, wilaya, commune, features)
├── Line (code, name, color, fare_dza, M2M Stop via LineStop)
├── LineStop (through — order, distance, time from previous)
├── Schedule (FK Line — day_of_week, start/end times, frequency)
├── ServiceDisruption (FK Line — type, title, active period)
├── BusLine (FK Bus + FK Line — tracking status, trip_id)
├── Trip (FK Bus + FK Driver + FK Line — start/end times, stats)
├── LocationUpdate (FK Bus — lat/lon/speed/heading/accuracy/nearest_stop)
├── PassengerCount (FK Bus — count, capacity, occupancy_rate)
├── WaitingPassengers (DEPRECATED — FK Stop, FK Line)
├── WaitingCountReport (FK Stop, FK Bus/Line — crowdsourced, verifiable)
├── BusWaitingList (FK Bus + FK Stop + FK User — waiting list)
├── ReputationScore (1:1 User — total/correct reports, level, multiplier)
├── VirtualCurrency (1:1 User — balance, lifetime earned/spent)
├── CurrencyTransaction (FK User — ledger entries)
├── DriverPerformanceScore (1:1 Driver — trips, safety, streaks, level)
├── PremiumFeature (catalog — name, cost, duration, target users)
├── UserPremiumFeature (FK User + FK Feature — purchase record)
├── Anomaly (FK Bus — speed/route/bunching/gap detection)
├── RouteSegment (FK Stop→Stop — polyline, distance, duration)
├── Notification (FK User — type, title, message, read status)
├── NotificationPreference (FK User — channels, quiet hours, favorites)
├── NotificationSchedule (FK User — future delivery)
├── DeviceToken (FK User — FCM push tokens)
├── CacheConfiguration, UserCache, CachedData, SyncQueue, OfflineLog (offline mode)
```

---

## 2. All Workflows & Use Cases

### 2.1 Passenger Workflows

#### 2.1.1 Registration & Authentication
1. `POST /api/v1/accounts/register/` — register with email, password, user_type=passenger
2. `POST /api/v1/accounts/login/` — receive JWT access+refresh tokens
3. `GET /api/v1/accounts/profile/` — view/edit profile (language, notification prefs, avatar)
4. Profile auto-created via signal on User creation

#### 2.1.2 Browse & Search
1. `GET /api/v1/lines/lines/` — list all bus lines with stops, fare, frequency
2. `GET /api/v1/lines/stops/` — list stops, filter by wilaya/commune
3. `GET /api/v1/lines/stops/nearby/?latitude=X&longitude=Y&radius=Z` — find stops near GPS position (returns raw list, not paginated)
4. `GET /api/v1/lines/stops/{id}/lines/` — which lines serve a stop
5. `GET /api/v1/lines/schedules/` — view schedules by line/day
6. `GET /api/v1/lines/disruptions/` — active service disruptions

#### 2.1.3 Live Tracking
1. Connect WebSocket `ws://host:8007/ws?token=JWT`
2. Send `{"type": "subscribe_to_line", "line_id": "..."}` or `{"type": "subscribe_to_bus", "bus_id": "..."}`
3. Receive `bus_location_update` events (but see M4 — not currently broadcast)
4. `GET /api/v1/tracking/active-buses/` — REST fallback for currently active buses
5. `GET /api/v1/tracking/locations/?bus_id=X&limit=10` — recent location history

#### 2.1.4 Waiting Count Reports (Crowdsourced)
1. `POST /api/v1/tracking/waiting-reports/` — report how many people are waiting
   - Fields: `stop` (required), `bus` or `line` (one required), `reported_count`, `confidence_level`, `reporter_latitude/longitude`
   - Rate limit: 10-minute cooldown per stop per user
   - GPS proximity validation (100m radius → `location_verified=true`)
   - Coin reward: base(50) × trust_multiplier + proximity_bonus(20) + early_adopter_bonus(20), with diminishing returns for multiple reporters at same stop

#### 2.1.5 Bus Waiting List
1. `POST /api/v1/tracking/bus-waiting-lists/join/` — join waiting list for specific bus at stop
   - Earns 10 coins; 60-min anti-farming cooldown
   - System auto-computes ETA via `_compute_eta()` (uses line stops + bus speed)
2. `POST /api/v1/tracking/bus-waiting-lists/leave/` — leave list
3. `GET /api/v1/tracking/bus-waiting-lists/summary/?stop_id=X` — waiting summary
4. Celery task `notify_waiting_passengers_on_arrival` → fires when bus within 300m of stop

#### 2.1.6 Gamification
1. `GET /api/v1/tracking/virtual-currency/my_balance/` — balance + lifetime stats
2. `GET /api/v1/tracking/virtual-currency/transactions/` — full ledger
3. `GET /api/v1/tracking/virtual-currency/leaderboard/` — weekly/monthly/all-time
4. `GET /api/v1/tracking/reputation/my_score/` — level, multiplier, accuracy rate, streak, next-level progress
5. `GET /api/v1/tracking/premium-features/` — browse catalog
6. `POST /api/v1/tracking/user-premium-features/purchase/` — buy feature with coins
7. `GET /api/v1/tracking/my-currency/my_balance/` — unified endpoint (works for both passengers and drivers)

#### 2.1.7 Notifications
1. `GET /api/v1/notifications/notifications/` — list in-app notifications (filterable by `is_read`)
2. `POST /api/v1/notifications/notifications/{id}/mark_read/`
3. `GET /api/v1/notifications/notifications/unread_count/`
4. `POST /api/v1/notifications/device-tokens/` — register FCM push token
5. `GET/POST /api/v1/notifications/preferences/` — per-type preferences (channels, quiet hours, favorite stops/lines)
6. `GET/POST /api/v1/notifications/schedules/` — scheduled notifications
7. WebSocket: `{"type": "subscribe", "channel": "notifications", "user_id": "..."}`

#### 2.1.8 Offline Mode
1. `GET /api/v1/offline/cache-config/` — cache settings (duration, max size, what to cache)
2. `GET /api/v1/offline/sync-status/` — current sync state
3. `POST /api/v1/offline/sync/` — trigger manual sync
4. `GET /api/v1/offline/cached-data/` — retrieve cached items
5. `GET /api/v1/offline/sync-queue/` — view pending offline changes

---

### 2.2 Driver Workflows

#### 2.2.1 Registration & Approval
1. `POST /api/v1/accounts/register/` — user_type=driver
2. `POST /api/v1/drivers/drivers/` — multipart: `id_card_photo`, `driver_license_photo`, `id_card_number`, `driver_license_number`, `phone_number`, `years_of_experience`
3. Status: `pending` → admin calls approve/reject/suspend
4. `DriverStatusLog` captures all transitions with `changed_by` and `reason`
5. Suspension cascades: deactivates buses, ends active trips

#### 2.2.2 Trip Management
1. **Path A — Direct**: `POST /api/v1/tracking/trips/` (bus, line, start_time)
   - Validates: driver owns bus, no concurrent active trip (via `select_for_update`), driver approved
2. **Path B — Via BusLine**: `POST /api/v1/tracking/bus-lines/start_tracking/` (line_id)
   - Auto-creates trip, also checks concurrent trips for both bus AND driver
   - Auto-selects driver's first bus (see L1)
3. During trip: `POST /api/v1/tracking/locations/` — GPS updates (bus auto-detected from driver)
4. During trip: `POST /api/v1/tracking/passenger-counts/` — passenger count (validates against capacity in viewset)
5. **End trip — Path A**: `POST /api/v1/tracking/trips/{id}/end/`
   - Calculates: distance (sum of Haversine segments), avg speed, max passengers, total stops
   - Resets BusLine to idle if no more active trips
6. **End trip — Path B**: `POST /api/v1/tracking/bus-lines/stop_tracking/`
   - Same calculations, slightly different clamping logic

#### 2.2.3 Report Verification
1. `POST /api/v1/tracking/waiting-reports/{id}/verify/`
   - Fields: `actual_count`, `verification_status` (correct/incorrect/partially_correct)
   - Correct → reporter gets +100 coins, +1 correct_report
   - Incorrect → reporter gets -100 or -200 penalty (based on severity)
   - Partially correct → reporter gets +25 coins, +0.5 correct_report
   - Triggers consistency bonus (25 coins) for 5 consecutive accurate reports
   - Updates reporter's reputation level and trust multiplier

#### 2.2.4 Performance & Gamification
1. `GET /api/v1/tracking/driver-performance/my_stats/` — nested under `performance_score` key
   - Performance level: rookie → experienced → expert → master
   - Metrics: total_trips, on_time_%, safety_score, passenger_rating, fuel_efficiency, streaks
2. `GET /api/v1/tracking/driver-currency/my_balance/` — balance
3. `GET /api/v1/tracking/driver-currency/transactions/` — ledger
4. `GET /api/v1/tracking/driver-currency/earnings_summary/` — by type over N days
5. Coin sources: trip completion (50+25 on-time × level multiplier), verification accuracy (+15), streak bonuses

#### 2.2.5 Driver Ratings
1. `GET /api/v1/drivers/drivers/{id}/ratings/` — view received ratings
2. **BUG**: `POST /api/v1/drivers/drivers/{id}/ratings/` → 405 Method Not Allowed
3. `POST /api/v1/drivers/drivers/{id}/update_availability/` — toggle is_available

---

### 2.3 Admin Workflows

#### 2.3.1 Driver Management
1. `GET /api/v1/drivers/drivers/?status=pending` — list pending applications
2. `POST /api/v1/drivers/drivers/{id}/approve/` — approve
3. `POST /api/v1/drivers/drivers/{id}/reject/` — reject with reason
4. `POST /api/v1/drivers/drivers/{id}/suspend/` — suspend (cascade: deactivate buses, end trips)

#### 2.3.2 Fleet Management
1. CRUD: `/api/v1/buses/buses/` — buses assigned to drivers
2. `POST /api/v1/buses/buses/{id}/approve/` — approve bus
3. Status management: active / inactive / maintenance

#### 2.3.3 Route Management
1. CRUD: `/api/v1/lines/lines/`, `/api/v1/lines/stops/`
2. Manage stop ordering via `LineStop` (order + distance + time from previous)
3. CRUD: `/api/v1/lines/schedules/` — per-line, per-day schedules
4. CRUD: `/api/v1/lines/disruptions/` — service disruption alerts

#### 2.3.4 Analytics (R22)
1. `GET /api/v1/admin/stats/ridership/` — daily trip count + passenger totals, filterable by line and date range
2. `GET /api/v1/admin/stats/lines/` — per-line summary (trips, passengers, avg speed, total distance)
3. `GET /api/v1/admin/stats/stops/busiest/?top_n=20` — stops ranked by waiting report volume

#### 2.3.5 Anomaly Management
1. `GET /api/v1/tracking/anomalies/` — list (speed, route, bunching, gap, schedule, passengers, other)
2. `POST /api/v1/tracking/anomalies/{id}/resolve/` — resolve with notes

---

### 2.4 Background Tasks (Celery)

| Task | Frequency | What It Does |
|------|-----------|--------------|
| `process_location_updates` | Periodic | Calculate missing speeds from consecutive locations; detect speed anomalies (>100 km/h) and route deviations (>1km from any stop) |
| `calculate_eta_for_stops` | Periodic | For each active bus-line, compute ETA to each stop using Haversine distance and last known speed; cache in Redis for 5 minutes |
| `detect_anomalies` | Periodic | Detect bus bunching (<500m between buses on same line) and service gaps (>30 min between buses); create Anomaly records |
| `notify_waiting_passengers_on_arrival` | Every 30s | Check LocationUpdates vs BusWaitingList; notify users when bus within 300m of their stop |
| `process_scheduled_notifications` | Every 1min | Send due scheduled notifications |
| `check_arrival_notifications` | Every 2-3min | Check active trips vs users' favorite stops; schedule arrival alerts based on `minutes_before_arrival` preference |
| `send_trip_updates` | Every 1min | Notify users when trips start/end on their favorite lines |
| `clean_old_location_data` | Daily | Delete LocationUpdates >7 days, PassengerCounts >30 days, old WaitingPassengers |
| `cleanup_old_notifications` | Daily | Delete read notifications >30 days old |
| `cleanup_invalid_tokens` | Periodic | Remove expired/invalid FCM device tokens |

---

## 3. Critical Audit

### 3.1 Confirmed Bugs

| # | Bug | Impact | Severity |
|---|-----|--------|----------|
| **B1** | `POST /drivers/{id}/ratings/` → 405 Method Not Allowed | Passengers cannot rate drivers via API | **HIGH** |
| **B2** | Rejected driver can create trips — `IsApprovedDriver` blocks `pending` but `rejected` drivers pass through endpoints using `IsDriverOrAdmin` | Safety risk: rejected driver operates | **HIGH** |
| **B3** | Leaderboard uses `Count('amount')` instead of `Sum('amount')` in `VirtualCurrencyService.get_leaderboard()` | Rankings based on transaction count, not total coins earned | **HIGH** |
| **B4** | `detect_anomalies` task references `models.Max` without `from django.db import models` | Task crashes every execution | **MEDIUM** |
| **B5** | `check_arrival_notifications` queries `.order_by('-timestamp')` but field is `created_at` | Task returns no results or crashes | **MEDIUM** |
| **B6** | Passenger count capacity not enforced in `PassengerCountService.update_passenger_count()` — only in viewset | Direct service calls accept count=999 | **MEDIUM** |
| **B7** | No concurrent-trip guard in `TripService.create_trip()` — only in viewset `perform_create()` | Service-layer callers can create overlapping trips | **MEDIUM** |
| **B8** | `TripService.end_trip()` can overflow `average_speed` field (max_digits=5) for very short trips with large distance | Trip end fails with DB error for edge cases; clamped to 250.00 but distance can still overflow | **LOW** |

### 3.2 Duplicate / Redundant Features

| # | Duplication | Action |
|---|-------------|--------|
| **D1** | Two identical permission modules: `apps/api/permissions.py` AND `apps/core/permissions.py` | Delete `apps/api/permissions.py` — all imports use `apps.core.permissions` |
| **D2** | Two waiting systems: `WaitingPassengers` (deprecated) and `WaitingCountReport` (current) | Both have full ViewSets. `WaitingPassengers` adds deprecation headers but is fully functional. Remove after migration period. |
| **D3** | Two trip-start paths: direct `POST /trips/` and `POST /bus-lines/start_tracking/` | Different validation depth. `start_tracking` also checks driver-level concurrent trips. Direct creation doesn't. |
| **D4** | Three currency endpoints: `/virtual-currency/`, `/driver-currency/`, `/my-currency/` | `my-currency` was created to unify. The other two should be deprecated. |
| **D5** | Two trip-end code paths: `TripService.end_trip()` and `BusLineService.stop_tracking()` | Both independently calculate distance/speed/stats with slightly different clamping. Should share one calculation function. |
| **D6** | Welcome bonus granted inconsistently: `VirtualCurrencyService.get_or_create_currency()` gives 100 coins + transaction vs `DriverCurrencyService.add_driver_currency()` sets `defaults={'balance': 100}` without transaction record | Different initial state depending on first interaction path |

### 3.3 Missing Features

| # | Missing Feature | Why It Matters for Algeria |
|---|-----------------|--------------------------|
| **M1** | **No passenger trip history** | `TripViewSet.history()` returns `queryset.none()` for passengers. Essential for commuters tracking expenses. |
| **M2** | **No fare/payment integration** | `Line.fare_dza` is display-only. No CIB/Edahabia/Baridimob integration. Cash is king but digital payment adoption is growing. |
| **M3** | **No route polylines** | `RouteSegment` model exists but nothing populates it. Maps show straight lines between stops instead of actual street routes. |
| **M4** | **No WebSocket location broadcast** | Drivers POST locations via REST. The WebSocket consumer handles subscriptions but never broadcasts locations. Redis cache is updated but subscribers never receive updates. This is the **core real-time feature** and it doesn't work. |
| **M5** | **No passenger-facing ETA endpoint** | `calculate_eta_for_stops` caches ETAs in Redis but no public endpoint exposes them. `estimate_arrival` requires `IsApprovedDriver`. |
| **M6** | **No WebSocket unsubscribe** | subscribe_to_bus, subscribe_to_line exist but no unsubscribe. Must disconnect to stop updates. |
| **M7** | **No admin user management** | Can't list/search/deactivate passenger accounts. Only driver management exists. |
| **M8** | **No passenger feedback/complaint system** | No way to report driver behavior, service quality, or safety concerns beyond the technical anomaly system. |
| **M9** | **No SMS/email notification delivery** | `NotificationPreference` allows SMS/email channels. `NotificationService` only creates in-app records. Twilio/SMTP config vars exist but aren't wired up. |
| **M10** | **No password reset** | No forgot-password flow. Users locked out permanently. |
| **M11** | **No bus-driver reassignment** | `Bus.driver` is a direct FK. A bus is permanently bound to one driver. No shift rotation support. |
| **M12** | **No schedule-based ETA** | ETA uses GPS speed + Haversine distance. `Schedule` data (departure times, frequency) is never consulted. Buses not yet moving have no ETA. |
| **M13** | **No notification localization** | Profile supports ar/fr/en but notifications are hardcoded English. |
| **M14** | **No data export** | No CSV/PDF export for analytics, trip history, or reports. |
| **M15** | **Premium features are empty shells** | Purchasing a feature spends coins but `check_feature_access()` is never called anywhere. No feature is actually gated. |
| **M16** | **Offline sync queue doesn't process** | `SyncQueue` model stores pending actions but no service replays them when back online. |
| **M17** | **No geofence alerts** | No notification when bus enters/exits defined areas. Common need for school routes. |
| **M18** | **No multi-line trip support** | Trip bound to exactly one line. No modeling for variant routes or line-sharing. |

### 3.4 Illogical / Confusing Flows

| # | Issue | Detail |
|---|-------|--------|
| **L1** | **"Use first bus" pattern** | `start_tracking`, `stop_tracking`, location updates, passenger counts all do `bus = buses.first()`. Driver with multiple buses can't choose which one. System silently picks one. |
| **L2** | **Coins awarded before verification** | Reporter gets 50+ coins immediately with `transaction_type='accurate_report'`. If later verified incorrect: -100 penalty. Net: random reporting can still profit via partially_correct (+25 bonus, no claw-back of initial 50). |
| **L3** | **Reputation multiplier inconsistency** | `get_or_create` defaults bronze to `trust_multiplier=1.00`. But `update_reputation()` sets bronze to 0.50. `_get_level_benefits()` shows bronze as "0.5x". First report gets 1.0x; after first verification cycle, drops to 0.5x. |
| **L4** | **Bus approval has no workflow** | `Bus.is_approved` field exists but no admin action endpoint to approve/reject buses. Unlike drivers (approve/reject/suspend), buses just sit at `is_approved=False`. |
| **L5** | **Cross-driver bus access returns 404 not 403** | Driver1 accessing Driver2's bus gets 404 (queryset isolation). Bus exists — 403 would be more informative. Acceptable as security pattern but confusing for debugging. |
| **L6** | **Line fare not connected to anything** | `Line.fare_dza` is an integer field with no link to trips, payments, or revenue analytics. Pure display data. |
| **L7** | **Capacity validation only at viewset layer** | `PassengerCountService` accepts any count. Only the DRF viewset checks `count > bus.capacity`. Any direct service call bypasses this. |
| **L8** | **Anomaly doesn't distinguish system vs user reports** | `reported_by` is null for auto-detected anomalies. No field or flag explicitly marks the source, making it hard to filter in admin view. |
| **L9** | **WaitingCountReport model allows both `bus` and `line` null** | Service validates one is required, but DB allows neither. Direct ORM can create orphan reports. |
| **L10** | **Nearby stops returns raw list** | `GET /lines/stops/nearby/` returns `[...]` instead of paginated `{"count": N, "results": [...]}`. Breaks clients expecting standard DRF pagination. |
| **L11** | **Performance stats nested under key** | `GET /driver-performance/my_stats/` wraps response in `{"performance_score": {...}}` instead of returning flat object. Frontend must handle this nesting. |

### 3.5 Security Concerns

| # | Issue | Risk |
|---|-------|------|
| **S1** | JWT in WebSocket query string (`?token=JWT`) | Token visible in server logs, proxy logs, browser history. Should use first-message auth. |
| **S2** | No WebSocket connection rate limiting | Unlimited connections per IP/user. DoS vector. |
| **S3** | Full GPS history visible to all authenticated users | `GET /tracking/locations/?bus_id=X` exposes complete driver movement patterns to any logged-in user. |
| **S4** | Exception details leak to API consumers | `except Exception` → `raise ValidationError(str(e))` can expose DB errors, file paths, internal state. |
| **S5** | No anomaly description sanitization | User-supplied `description` stored/returned raw. XSS risk in web frontends. |
| **S6** | `save_user_profile` signal creates profile on every User save if missing | Unexpected side effect during bulk operations or migrations. |

---

## 4. Recommendations

### 4.1 Critical Fixes (Block Deployment)

**R1. Fix driver rating POST** — Add `@action(detail=True, methods=['post'])` to `DriverViewSet` for ratings, or create standalone `DriverRatingCreateView`.

**R2. Block rejected drivers** — In `TripViewSet.perform_create()`, explicitly check `request.user.driver.status == "approved"`. Also audit all driver-facing endpoints that use `IsDriverOrAdmin` — they should use `IsApprovedDriver` for write operations.

**R3. Fix leaderboard aggregation** — Change `Count('amount')` to `Sum('amount')` in `VirtualCurrencyService.get_leaderboard()`.

**R4. Fix Celery task crashes** — (a) Add `from django.db import models` in `detect_anomalies`. (b) Change `'-timestamp'` to `'-created_at'` in `check_arrival_notifications`.

**R5. Implement WebSocket location broadcast** — After `LocationUpdateService.record_location_update()`, add:
```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
layer = get_channel_layer()
async_to_sync(layer.group_send)(f"bus_{bus.id}", {
    "type": "bus_location_update",
    "bus_id": str(bus.id),
    "location": location_dict,
    "timestamp": location.created_at.isoformat()
})
```
This is the **core feature** of the entire application and it's not wired up.

**R6. Add password reset** — Use Django's `PasswordResetTokenGenerator` + email delivery. Two endpoints: `POST /accounts/password-reset/` and `POST /accounts/password-reset/confirm/`.

### 4.2 High Priority Fixes

**R7. Enforce capacity at service level** — Move `count > bus.capacity` check into `PassengerCountService.update_passenger_count()`.

**R8. Add concurrent trip guard to TripService** — Add `Trip.objects.filter(bus=bus, is_completed=False).exists()` check inside `TripService.create_trip()` within `@transaction.atomic`.

**R9. Expose ETA to passengers** — Create `GET /api/v1/tracking/eta/?bus_id=X&stop_id=Y` (permission: `IsAuthenticated`) reading from Redis ETA cache.

**R10. Fix coin timing** — Hold report coins in escrow (create transaction but mark as `pending`). Release after verification or after 24-hour auto-release window. This prevents gaming via random reports.

**R11. Fix reputation multiplier inconsistency** — Set `get_or_create` default for bronze to `trust_multiplier=0.50` to match `update_reputation()` and documented benefits.

**R12. Fix the "first bus" pattern** — Add optional `bus_id` parameter to all driver endpoints. If driver has >1 bus, require it. If exactly 1, auto-select.

### 4.3 Architecture Improvements

**R13. Delete duplicate permissions** — Remove `apps/api/permissions.py`. All views import from `apps.core.permissions.py`.

**R14. Deprecate `WaitingPassengers`** — Return 410 Gone. Only `WaitingCountReport` should exist.

**R15. Consolidate currency to `/my-currency/`** — Deprecate `/virtual-currency/` and `/driver-currency/`.

**R16. Unify trip creation** — Move all validation into `TripService.create_trip()`. Either remove direct trip POST or have both paths call the same service method with identical checks.

**R17. Unify trip-end statistics** — Extract stat calculation (distance, speed, max passengers, stops) into a shared `_calculate_trip_stats(trip_id)` function called by both `TripService.end_trip()` and `BusLineService.stop_tracking()`.

**R18. Implement push/SMS/email delivery** — Wire up Firebase (push), SMTP (email), Twilio (SMS) in `NotificationService`. Route based on user's `NotificationPreference.channels`.

**R19. Process offline sync queue** — Add `POST /api/v1/offline/sync/process/` that replays `SyncQueue` items (pending → syncing → completed/failed).

### 4.4 Missing Feature Priorities

| Priority | Feature | Effort |
|----------|---------|--------|
| Critical | Password reset (R6) | 1 day |
| Critical | WebSocket broadcast (R5) | 1 day |
| High | Passenger ETA endpoint (R9) | 0.5 day |
| High | Push/SMS/email delivery (R18) | 3 days |
| High | Admin user management | 2 days |
| High | Bus approval workflow | 0.5 day |
| Medium | Route polylines (from OSRM) | 2 days |
| Medium | Passenger trip history | 2 days |
| Medium | Notification localization (ar/fr/en) | 2 days |
| Medium | Driver shift/rotation model | 3 days |
| Medium | Bus-driver reassignment | 1 day |
| Medium | Passenger complaint system | 2 days |
| Low | Data export (CSV/PDF) | 2 days |
| Low | Premium feature gating | 2 days |
| Low | Schedule-based ETA | 3 days |
| Low | Geofence alerts | 3 days |
| Low | Multi-line trip support | 3 days |

### 4.5 Algeria-Specific Recommendations

**R20. Wilaya-based filtering** — Add `wilaya` to `Line` model. Filter analytics, buses, and notifications by wilaya. Algeria has 58 wilayas; most bus systems are wilaya-scoped.

**R21. Friday schedule handling** — Friday is the weekly rest day (not Sunday). Ensure Schedule model treats `day_of_week=4` (Friday) as reduced/no service. Frontend should display Friday with appropriate styling.

**R22. Peak hour ETA adjustment** — Algerian cities have brutal peak congestion (7-9 AM, 4-6 PM). Apply time-of-day speed multiplier: `peak_factor = 0.4` (40% of normal speed during rush hour).

**R23. Payment integration** — When ready, integrate with:
- **CIB** (Carte Interbancaire) for card payments
- **Baridimob** (Algérie Poste) for mobile money
- **Edahabia** card for transport-specific payment

**R24. Arabic RTL support** — The `Profile.language` supports `ar`. Ensure all notification messages, disruption descriptions, and API string responses support Arabic.

**R25. Offline map tiles** — For Flutter frontend, support downloading OpenStreetMap tile packages. Mobile data coverage is spotty outside Algiers/Oran/Constantine.

**R26. Intercity vs intracity** — Add `line_type` field: `urban`, `intercity`, `suburban`. ETUSA (Algiers) vs SNTV (intercity) vs private operators have very different operational patterns.

---

## Summary Scorecard

| Category | Score | Key Issue |
|----------|-------|-----------|
| **Core tracking** | 5/10 | GPS storage works but WebSocket broadcast (the core feature) is not wired up |
| **Gamification** | 6/10 | Well-designed system. Leaderboard bug, pre-verification rewards, premium features are shells |
| **Driver management** | 7/10 | Approval workflow solid. Rating POST broken. No shift rotation. |
| **Admin tools** | 5/10 | Basic analytics. No user management, no data export, no real-time dashboard. |
| **Notifications** | 3/10 | In-app only. Push/SMS/email not implemented despite config being ready. |
| **Offline mode** | 2/10 | Config + models exist. Sync queue doesn't process. No real offline capability. |
| **Security** | 6/10 | JWT auth solid. WebSocket auth weak. Exception messages leak. |
| **Algeria context** | 4/10 | Wilaya field exists on stops. No payment integration, no localization, no Friday awareness. |
| **Frontend** | 0/10 | Not built. Only audit document exists. |
| **Code quality** | 6/10 | Clean architecture (services/selectors/views). Duplicated permissions, broken tasks, inconsistent validation layers. |
