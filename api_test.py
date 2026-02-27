#!/usr/bin/env python3
"""
DZ Bus Tracker — Comprehensive API Integration Test Script
===========================================================
Tests all API endpoints in correct dependency order using HTTP requests.
Creates test users via API (driver, passenger) — admin must pre-exist via createsuperuser.

Usage:
    # Run all phases (server must be running on port 8007)
    python api_test.py

    # Custom server URL
    python api_test.py --base-url http://192.168.1.10:8007

    # Custom admin credentials
    python api_test.py --admin-email admin@dzbus.com --admin-password MyPass123

    # Run single phase
    python api_test.py --phase 7

    # Keep test data (don't run cleanup phase)
    python api_test.py --skip-cleanup

Pre-requisites:
    1. Server running: uvicorn config.asgi:application --host 0.0.0.0 --port 8007 --reload
    2. Admin user exists: python manage.py createsuperuser
    3. pip install requests

Log output: api_test_<RUN_ID>.log
"""

import argparse
import io
import json
import os
import struct
import sys
import time
import zlib
from datetime import date, datetime, timedelta
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required. Install: pip install requests")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "http://localhost:8007"
DEFAULT_ADMIN_EMAIL = "admin@dzbus.com"
DEFAULT_ADMIN_PASSWORD = "Green+114"

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=7)

RUN_ID = time.strftime("%m%d%H%M%S")

LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, f"api_test_{RUN_ID}.log")

DIVIDER_THICK = "=" * 78
DIVIDER_THIN = "-" * 78

# Algerian GPS coordinates
ALGIERS_MARTYRS = {"latitude": "36.7538000", "longitude": "3.0588000"}
ALGIERS_POSTE = {"latitude": "36.7620000", "longitude": "3.0550000"}
ALGIERS_BENAKNOUN = {"latitude": "36.7725000", "longitude": "3.0420000"}


def _minimal_png() -> bytes:
    """Generate a valid 1x1 red PNG image for multipart uploads."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00\xff\x00\x00")
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", raw) + _chunk(b"IEND", b"")


# ─────────────────────────────────────────────────────────────────────────────
# Main Tester Class
# ─────────────────────────────────────────────────────────────────────────────
class DZBusTrackerAPITester:
    """Orchestrates all API integration tests in 14 phases."""

    def __init__(
        self,
        base_url: str,
        admin_email: str,
        admin_password: str,
        timeout: int = 30,
        log_file: Optional[str] = None,
        phase: Optional[int] = None,
        skip_cleanup: bool = False,
    ):
        self.BASE_URL = base_url.rstrip("/")
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.timeout = timeout
        self.phase = phase
        self.skip_cleanup = skip_cleanup

        # Test user credentials (unique per run)
        self.driver_email = f"driver_test_{RUN_ID}@dzbus.com"
        self.driver_password = "Green+114"
        self.passenger_email = f"passenger_test_{RUN_ID}@dzbus.com"
        self.passenger_password = "Green+114"

        # Sessions
        self.admin_session = requests.Session()
        self.driver_session = requests.Session()
        self.passenger_session = requests.Session()
        self.anon_session = requests.Session()

        # Stored IDs for cross-phase references
        self.ids: dict[str, Any] = {}

        # Counters
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

        # Log file
        self._log_file = open(log_file or LOG_FILE, "w", encoding="utf-8")

    # ── Logging ─────────────────────────────────────────────────────────────

    def _write(self, text: str) -> None:
        print(text)
        self._log_file.write(text + "\n")
        self._log_file.flush()

    def _log_request(
        self,
        label: str,
        method: str,
        url: str,
        headers: dict,
        body: Any,
        response: requests.Response,
        expected: int,
    ) -> None:
        self._log_file.write(f"\n{DIVIDER_THICK}\n")
        self._log_file.write(f"[TEST] {label}\n")
        self._log_file.write(f"{DIVIDER_THIN}\n")
        self._log_file.write(f"REQUEST: {method.upper()} {url}\n")
        self._log_file.write("HEADERS:\n")
        for k, v in headers.items():
            if k.lower() == "authorization" and len(str(v)) > 60:
                v = str(v)[:40] + "..." + str(v)[-10:]
            self._log_file.write(f"  {k}: {v}\n")
        if body is not None:
            self._log_file.write("BODY:\n")
            if isinstance(body, dict):
                self._log_file.write(json.dumps(body, indent=2, default=str) + "\n")
            else:
                self._log_file.write(str(body)[:500] + "\n")
        self._log_file.write(f"{DIVIDER_THIN}\n")
        self._log_file.write(f"EXPECTED: {expected}  |  GOT: {response.status_code}\n")
        try:
            resp_body = response.json()
            resp_str = json.dumps(resp_body, indent=2, default=str)
        except Exception:
            resp_str = response.text[:2000]
        self._log_file.write(f"RESPONSE BODY:\n{resp_str[:3000]}\n")
        self._log_file.write(f"{DIVIDER_THICK}\n")
        self._log_file.flush()

    # ── Core Request Helper ─────────────────────────────────────────────────

    def request(
        self,
        session: requests.Session,
        method: str,
        path: str,
        expected_status: int = 200,
        label: str = "",
        json_body: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Send a request, log it, compare status code to expected.
        Returns parsed JSON on success, None on failure.
        """
        url = f"{self.BASE_URL}{path}"
        label = label or f"{method.upper()} {path}"

        send_kwargs: dict[str, Any] = {
            "params": params,
            "timeout": self.timeout,
        }

        if files:
            send_kwargs["files"] = files
            send_kwargs["data"] = data or {}
        elif json_body is not None:
            send_kwargs["json"] = json_body
        elif data is not None:
            send_kwargs["data"] = data

        try:
            resp = session.request(method.upper(), url, **send_kwargs)
        except requests.exceptions.ConnectionError as e:
            self._write(f"  FAIL  {label} — CONNECTION ERROR: {e}")
            self.failed += 1
            self.errors.append(f"{label}: Connection error")
            return None
        except requests.exceptions.Timeout as e:
            self._write(f"  FAIL  {label} — TIMEOUT: {e}")
            self.failed += 1
            self.errors.append(f"{label}: Timeout")
            return None

        # Log to file
        log_headers = dict(session.headers)
        self._log_request(label, method, url, log_headers, json_body or data, resp, expected_status)

        # Check status
        if resp.status_code == expected_status:
            self.passed += 1
            status_icon = "PASS"
        else:
            self.failed += 1
            status_icon = "FAIL"
            self.errors.append(f"{label}: expected {expected_status}, got {resp.status_code}")

        self._write(f"  {status_icon}  [{resp.status_code}] {label}")

        try:
            return resp.json()
        except Exception:
            return {"_raw": resp.text[:500]} if resp.text else {}

    # ── Utility Helpers ─────────────────────────────────────────────────────

    def _set_auth(self, session: requests.Session, token: str) -> None:
        session.headers.update({"Authorization": f"Bearer {token}"})

    def _extract_id(self, resp: Optional[dict], key: str = "id") -> Optional[str]:
        if resp and key in resp:
            return str(resp[key])
        if resp and "results" in resp and resp["results"]:
            return str(resp["results"][0].get(key, ""))
        return None

    def _phase(self, number: int, title: str) -> None:
        banner = f"\n{'#' * 78}\n##  PHASE {number}: {title}\n{'#' * 78}"
        self._write(banner)

    # ── Phase Methods ───────────────────────────────────────────────────────

    def phase_01_health_and_schema(self):
        self._phase(1, "Health & Schema")

        self.request(self.anon_session, "GET", "/health/", 200,
                     "Health check")

        self.request(self.anon_session, "GET", "/api/schema/", 200,
                     "OpenAPI schema")

        self.request(self.anon_session, "GET", "/api/schema/swagger-ui/", 200,
                     "Swagger UI")

        self.request(self.anon_session, "GET", "/api/schema/redoc/", 200,
                     "ReDoc UI")

    def phase_02_authentication(self):
        self._phase(2, "Authentication (JWT)")

        # Admin login via JWT token endpoint
        resp = self.request(self.anon_session, "POST", "/api/token/", 200,
                            "Admin JWT login",
                            json_body={"email": self.admin_email, "password": self.admin_password})
        if resp and "access" in resp:
            self.ids["admin_access"] = resp["access"]
            self.ids["admin_refresh"] = resp["refresh"]
            self._set_auth(self.admin_session, resp["access"])
        else:
            self._write("  CRITICAL: Admin login failed — cannot continue")
            return

        # Token refresh
        resp = self.request(self.anon_session, "POST", "/api/token/refresh/", 200,
                            "JWT token refresh",
                            json_body={"refresh": self.ids["admin_refresh"]})

        # Token verify
        self.request(self.anon_session, "POST", "/api/token/verify/", 200,
                     "JWT token verify",
                     json_body={"token": self.ids["admin_access"]})

        # Wrong password
        self.request(self.anon_session, "POST", "/api/token/", 401,
                     "JWT login — wrong password",
                     json_body={"email": self.admin_email, "password": "wrongpassword"})

        # Non-existent user
        self.request(self.anon_session, "POST", "/api/token/", 401,
                     "JWT login — non-existent user",
                     json_body={"email": "nobody@nowhere.com", "password": "whatever"})

    def phase_03_user_registration(self):
        self._phase(3, "User Registration & Login")

        # Register passenger
        resp = self.request(self.anon_session, "POST", "/api/v1/accounts/register/", 201,
                            "Register passenger",
                            json_body={
                                "email": self.passenger_email,
                                "password": self.passenger_password,
                                "confirm_password": self.passenger_password,
                                "first_name": "Test",
                                "last_name": "Passenger",
                                "phone_number": "+213551234567",
                                "user_type": "passenger",
                            })
        if resp and "access" in resp:
            self.ids["passenger_access"] = resp["access"]
            self.ids["passenger_refresh"] = resp["refresh"]
            self.ids["passenger_user_id"] = resp.get("user", {}).get("id")
            self._set_auth(self.passenger_session, resp["access"])

        # Login as passenger
        resp = self.request(self.anon_session, "POST", "/api/v1/accounts/login/", 200,
                            "Login as passenger",
                            json_body={
                                "email": self.passenger_email,
                                "password": self.passenger_password,
                            })

        # Duplicate email
        self.request(self.anon_session, "POST", "/api/v1/accounts/register/", 400,
                     "Register — duplicate email",
                     json_body={
                         "email": self.passenger_email,
                         "password": "Green+114",
                         "confirm_password": "Green+114",
                         "first_name": "Dup",
                         "last_name": "User",
                         "phone_number": "+213551111111",
                         "user_type": "passenger",
                     })

        # Missing fields
        self.request(self.anon_session, "POST", "/api/v1/accounts/register/", 400,
                     "Register — missing required fields",
                     json_body={"email": "incomplete@test.com"})

        # Password mismatch
        self.request(self.anon_session, "POST", "/api/v1/accounts/register/", 400,
                     "Register — password mismatch",
                     json_body={
                         "email": f"mismatch_{RUN_ID}@test.com",
                         "password": "Green+114",
                         "confirm_password": "DifferentPassword",
                         "first_name": "Mis",
                         "last_name": "Match",
                         "phone_number": "+213550000000",
                         "user_type": "passenger",
                     })

    def phase_04_driver_registration(self):
        self._phase(4, "Driver Registration (multipart)")

        png_bytes = _minimal_png()
        id_card_file = ("id_card.png", io.BytesIO(png_bytes), "image/png")
        license_file = ("license.png", io.BytesIO(png_bytes), "image/png")

        # Register driver (multipart)
        resp = self.request(
            self.anon_session, "POST", "/api/v1/accounts/register-driver/", 201,
            "Register driver (multipart)",
            data={
                "email": self.driver_email,
                "password": self.driver_password,
                "confirm_password": self.driver_password,
                "first_name": "Test",
                "last_name": "Driver",
                "phone_number": f"+2135523{RUN_ID[-5:]}",
                "id_card_number": f"1234567890{RUN_ID}",
                "driver_license_number": f"DL-{RUN_ID}",
                "years_of_experience": "5",
            },
            files={
                "id_card_photo": id_card_file,
                "driver_license_photo": license_file,
            },
        )
        if resp:
            if "access" in resp:
                self.ids["driver_access"] = resp["access"]
                self.ids["driver_refresh"] = resp["refresh"]
                self._set_auth(self.driver_session, resp["access"])
            if "driver_id" in resp:
                self.ids["driver_id"] = resp["driver_id"]
            if resp.get("user", {}).get("id"):
                self.ids["driver_user_id"] = resp["user"]["id"]

        # Duplicate email
        png_bytes2 = _minimal_png()
        self.request(
            self.anon_session, "POST", "/api/v1/accounts/register-driver/", 400,
            "Register driver — duplicate email",
            data={
                "email": self.driver_email,
                "password": "Green+114",
                "confirm_password": "Green+114",
                "first_name": "Dup",
                "last_name": "Driver",
                "phone_number": "+213553333333",
                "id_card_number": "999999999999999999",
                "driver_license_number": "DL-DUP",
                "years_of_experience": "2",
            },
            files={
                "id_card_photo": ("id.png", io.BytesIO(png_bytes2), "image/png"),
                "driver_license_photo": ("lic.png", io.BytesIO(png_bytes2), "image/png"),
            },
        )

        # Missing images
        self.request(
            self.anon_session, "POST", "/api/v1/accounts/register-driver/", 400,
            "Register driver — missing images",
            data={
                "email": f"noimg_{RUN_ID}@test.com",
                "password": "Green+114",
                "confirm_password": "Green+114",
                "first_name": "No",
                "last_name": "Images",
                "phone_number": "+213554444444",
                "id_card_number": "111111111111111111",
                "driver_license_number": "DL-NOIMG",
                "years_of_experience": "1",
            },
        )

    def phase_05_user_profile_management(self):
        self._phase(5, "User & Profile Management")

        # Admin: list all users
        resp = self.request(self.admin_session, "GET", "/api/v1/accounts/users/", 200,
                            "Admin — list all users")

        # Passenger: get own user via /me/
        resp = self.request(self.passenger_session, "GET", "/api/v1/accounts/users/me/", 200,
                            "Passenger — GET /users/me/")
        if resp and resp.get("id"):
            self.ids["passenger_user_id"] = resp["id"]

        # Passenger: update own user via /me/
        self.request(self.passenger_session, "PATCH", "/api/v1/accounts/users/me/", 200,
                     "Passenger — PATCH /users/me/",
                     json_body={"first_name": "Updated"})

        # Get specific user by ID
        if self.ids.get("passenger_user_id"):
            self.request(self.admin_session, "GET",
                         f"/api/v1/accounts/users/{self.ids['passenger_user_id']}/", 200,
                         "Admin — GET user by ID")

        # Change password
        if self.ids.get("passenger_user_id"):
            self.request(self.passenger_session, "POST",
                         f"/api/v1/accounts/users/{self.ids['passenger_user_id']}/change_password/", 200,
                         "Passenger — change password",
                         json_body={
                             "current_password": self.passenger_password,
                             "new_password": "NewGreen+114",
                             "confirm_password": "NewGreen+114",
                         })
            # Update stored password and re-login to get new token
            self.passenger_password = "NewGreen+114"
            resp = self.request(self.anon_session, "POST", "/api/token/", 200,
                                "Passenger — re-login after password change",
                                json_body={"email": self.passenger_email, "password": self.passenger_password})
            if resp and "access" in resp:
                self.ids["passenger_access"] = resp["access"]
                self._set_auth(self.passenger_session, resp["access"])

        # Profile: GET /profiles/me/
        self.request(self.passenger_session, "GET", "/api/v1/accounts/profiles/me/", 200,
                     "Passenger — GET /profiles/me/")

        # Profile: PATCH /profiles/update_me/
        self.request(self.passenger_session, "PATCH", "/api/v1/accounts/profiles/update_me/", 200,
                     "Passenger — PATCH /profiles/update_me/",
                     json_body={"bio": "Test bio for passenger"})

        # Profile: PATCH /profiles/update_notification_preferences/
        self.request(self.passenger_session, "PATCH",
                     "/api/v1/accounts/profiles/update_notification_preferences/", 200,
                     "Passenger — update notification preferences",
                     json_body={
                         "push_notifications_enabled": True,
                         "email_notifications_enabled": False,
                         "sms_notifications_enabled": False,
                     })

        # Permission test: passenger listing all users (should be filtered to self or 403)
        self.request(self.passenger_session, "GET", "/api/v1/accounts/users/", 200,
                     "Passenger — list users (filtered to self)")

    def phase_06_driver_management(self):
        self._phase(6, "Driver Management (Admin)")

        # Admin: list drivers
        resp = self.request(self.admin_session, "GET", "/api/v1/drivers/drivers/", 200,
                            "Admin — list drivers")

        # Find driver ID if not set
        if not self.ids.get("driver_id") and resp:
            results = resp.get("results", resp) if isinstance(resp, dict) else resp
            if isinstance(results, list) and results:
                self.ids["driver_id"] = str(results[0].get("id", ""))

        # Get specific driver
        if self.ids.get("driver_id"):
            self.request(self.admin_session, "GET",
                         f"/api/v1/drivers/drivers/{self.ids['driver_id']}/", 200,
                         "Admin — GET driver by ID")

            # Approve driver
            self.request(self.admin_session, "POST",
                         f"/api/v1/drivers/drivers/{self.ids['driver_id']}/approve/", 200,
                         "Admin — approve driver",
                         json_body={"approve": True})

            # Driver: get own profile
            self.request(self.driver_session, "GET",
                         "/api/v1/drivers/drivers/profile/", 200,
                         "Driver — GET own profile")

            # Update availability
            self.request(self.driver_session, "POST",
                         f"/api/v1/drivers/drivers/{self.ids['driver_id']}/update_availability/", 200,
                         "Driver — update availability",
                         json_body={"is_available": True})

        # Permission test: passenger trying to approve
        if self.ids.get("driver_id"):
            self.request(self.passenger_session, "POST",
                         f"/api/v1/drivers/drivers/{self.ids['driver_id']}/approve/", 403,
                         "Permission: passenger approve driver -> 403",
                         json_body={"approve": True})

    def phase_07_stops_and_lines(self):
        self._phase(7, "Stops & Lines (Admin creates, all read)")

        # Create stops
        stop_data = [
            {"name": f"Place des Martyrs {RUN_ID}", "address": "Place des Martyrs, Algiers",
             **ALGIERS_MARTYRS},
            {"name": f"La Grande Poste {RUN_ID}", "address": "La Grande Poste, Algiers",
             **ALGIERS_POSTE},
            {"name": f"Ben Aknoun {RUN_ID}", "address": "Ben Aknoun, Algiers",
             **ALGIERS_BENAKNOUN},
        ]

        for i, sd in enumerate(stop_data):
            resp = self.request(self.admin_session, "POST", "/api/v1/lines/stops/", 201,
                                f"Admin — create stop {i + 1}: {sd['name']}", json_body=sd)
            if resp and resp.get("id"):
                self.ids[f"stop_{i + 1}"] = str(resp["id"])

        # List stops
        self.request(self.passenger_session, "GET", "/api/v1/lines/stops/", 200,
                     "List all stops")

        # Get single stop
        if self.ids.get("stop_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/lines/stops/{self.ids['stop_1']}/", 200,
                         "GET stop by ID")

        # Update stop
        if self.ids.get("stop_1"):
            self.request(self.admin_session, "PATCH",
                         f"/api/v1/lines/stops/{self.ids['stop_1']}/", 200,
                         "Admin — update stop",
                         json_body={"description": "Updated description"})

        # Nearby stops
        self.request(self.passenger_session, "GET", "/api/v1/lines/stops/nearby/", 200,
                     "Nearby stops",
                     params={"latitude": "36.7538", "longitude": "3.0588"})

        # Create lines
        line_data = [
            {"name": f"Line A {RUN_ID}", "code": f"LA{RUN_ID}", "color": "#FF0000",
             "frequency": 15, "description": "Test line A"},
            {"name": f"Line B {RUN_ID}", "code": f"LB{RUN_ID}", "color": "#0000FF",
             "frequency": 20, "description": "Test line B"},
        ]

        for i, ld in enumerate(line_data):
            resp = self.request(self.admin_session, "POST", "/api/v1/lines/lines/", 201,
                                f"Admin — create line {i + 1}: {ld['name']}", json_body=ld)
            if resp and resp.get("id"):
                self.ids[f"line_{i + 1}"] = str(resp["id"])

        # List lines
        self.request(self.passenger_session, "GET", "/api/v1/lines/lines/", 200,
                     "List all lines")

        # Add stops to line
        if self.ids.get("line_1") and self.ids.get("stop_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/add_stop/", 201,
                         "Admin — add stop 1 to line 1",
                         json_body={"stop_id": self.ids["stop_1"], "order": 1})

        if self.ids.get("line_1") and self.ids.get("stop_2"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/add_stop/", 201,
                         "Admin — add stop 2 to line 1",
                         json_body={"stop_id": self.ids["stop_2"], "order": 2})

        if self.ids.get("line_1") and self.ids.get("stop_3"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/add_stop/", 201,
                         "Admin — add stop 3 to line 1",
                         json_body={"stop_id": self.ids["stop_3"], "order": 3})

        # List stops for line
        if self.ids.get("line_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/stops/", 200,
                         "List stops for line 1")

        # Add schedule
        if self.ids.get("line_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/add_schedule/", 201,
                         "Admin — add schedule to line 1",
                         json_body={
                             "day_of_week": TODAY.weekday(),
                             "start_time": "06:00:00",
                             "end_time": "22:00:00",
                             "frequency_minutes": 15,
                         })

        # List schedules for line
        if self.ids.get("line_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/schedules/", 200,
                         "List schedules for line 1")

        # Search lines
        self.request(self.passenger_session, "GET", "/api/v1/lines/lines/search/", 200,
                     "Search lines", params={"q": f"Line A {RUN_ID}"})

        # Deactivate / Activate line
        if self.ids.get("line_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/deactivate/", 200,
                         "Admin — deactivate line 1")
            self.request(self.admin_session, "POST",
                         f"/api/v1/lines/lines/{self.ids['line_1']}/activate/", 200,
                         "Admin — activate line 1")

        # List all schedules
        self.request(self.passenger_session, "GET", "/api/v1/lines/schedules/", 200,
                     "List all schedules")

        # Permission test: passenger creating stop
        self.request(self.passenger_session, "POST", "/api/v1/lines/stops/", 403,
                     "Permission: passenger create stop -> 403",
                     json_body={"name": "Unauthorized", "latitude": "36.75", "longitude": "3.05"})

    def phase_08_buses(self):
        self._phase(8, "Buses (Driver creates, Admin approves)")

        # Driver creates bus
        bus_data = {
            "license_plate": f"{RUN_ID[:5]}-{RUN_ID[5:8]}-{RUN_ID[8:10]}",
            "model": "Mercedes Sprinter",
            "manufacturer": "Mercedes-Benz",
            "year": 2023,
            "capacity": 50,
            "is_air_conditioned": True,
            "description": f"Test bus {RUN_ID}",
        }
        # If we have the driver ID (Driver model PK), set it
        if self.ids.get("driver_id"):
            bus_data["driver"] = self.ids["driver_id"]

        resp = self.request(self.driver_session, "POST", "/api/v1/buses/buses/", 201,
                            "Driver — create bus", json_body=bus_data)
        if resp and resp.get("id"):
            self.ids["bus_1"] = str(resp["id"])

        # List buses
        self.request(self.passenger_session, "GET", "/api/v1/buses/buses/", 200,
                     "List all buses")

        # Get bus by ID
        if self.ids.get("bus_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/", 200,
                         "GET bus by ID")

        # Get bus with query expansion
        if self.ids.get("bus_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/", 200,
                         "GET bus with expanded fields",
                         params={"expand_driver": "true", "expand_location": "true"})

        # Admin approves bus
        if self.ids.get("bus_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/approve/", 200,
                         "Admin — approve bus",
                         json_body={"approve": True})

        # Admin activates bus
        if self.ids.get("bus_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/activate/", 200,
                         "Admin — activate bus")

        # Driver: update location
        if self.ids.get("bus_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/update_location/", 200,
                         "Driver — update bus location",
                         json_body={
                             "latitude": ALGIERS_MARTYRS["latitude"],
                             "longitude": ALGIERS_MARTYRS["longitude"],
                             "speed": "30.5",
                             "heading": "90.0",
                             "accuracy": "10.0",
                         })

        # Driver: update passenger count
        if self.ids.get("bus_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/update_passenger_count/", 200,
                         "Driver — update passenger count",
                         json_body={"count": 25})

        # Driver: start tracking
        if self.ids.get("bus_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/start_tracking/", 200,
                         "Driver — start bus tracking")

        # Driver: stop tracking
        if self.ids.get("bus_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/stop_tracking/", 200,
                         "Driver — stop bus tracking")

        # List bus locations
        self.request(self.passenger_session, "GET", "/api/v1/buses/locations/", 200,
                     "List bus locations")

        # Permission test: passenger creating bus
        self.request(self.passenger_session, "POST", "/api/v1/buses/buses/", 403,
                     "Permission: passenger create bus -> 403",
                     json_body={"license_plate": "99999-999-16", "capacity": 30})

    def phase_09_tracking(self):
        self._phase(9, "Tracking — Bus-Lines, Locations, Trips")

        # Assign bus to line (admin)
        if self.ids.get("bus_1") and self.ids.get("line_1"):
            resp = self.request(self.admin_session, "POST", "/api/v1/tracking/bus-lines/", 201,
                                "Admin — assign bus to line",
                                json_body={
                                    "bus": self.ids["bus_1"],
                                    "line": self.ids["line_1"],
                                })
            if resp and resp.get("id"):
                self.ids["bus_line_1"] = str(resp["id"])

        # Start tracking (driver)
        if self.ids.get("line_1"):
            resp = self.request(self.driver_session, "POST",
                                "/api/v1/tracking/bus-lines/start_tracking/", 200,
                                "Driver — start tracking on bus-line",
                                json_body={"line_id": self.ids["line_1"]})

        # Location update (driver)
        resp = self.request(self.driver_session, "POST", "/api/v1/tracking/locations/", 201,
                            "Driver — GPS location update",
                            json_body={
                                "latitude": ALGIERS_MARTYRS["latitude"],
                                "longitude": ALGIERS_MARTYRS["longitude"],
                                "speed": "35.0",
                                "heading": "180.0",
                                "accuracy": "5.0",
                            })
        if resp and resp.get("id"):
            self.ids["location_1"] = str(resp["id"])

        # List locations
        self.request(self.passenger_session, "GET", "/api/v1/tracking/locations/", 200,
                     "List location updates")

        # Passenger count (driver)
        resp = self.request(self.driver_session, "POST", "/api/v1/tracking/passenger-counts/", 201,
                            "Driver — report passenger count",
                            json_body={
                                "count": 30,
                                "stop": self.ids.get("stop_1"),
                            })

        # Create trip (driver)
        trip_data = {
            "bus": self.ids.get("bus_1"),
            "line": self.ids.get("line_1"),
            "start_stop": self.ids.get("stop_1"),
            "start_time": datetime.utcnow().isoformat() + "Z",
            "notes": f"Test trip {RUN_ID}",
        }
        if self.ids.get("driver_id"):
            trip_data["driver"] = self.ids["driver_id"]
        resp = self.request(self.driver_session, "POST", "/api/v1/tracking/trips/", 201,
                            "Driver — create trip", json_body=trip_data)
        if resp and resp.get("id"):
            self.ids["trip_1"] = str(resp["id"])

        # Get trip
        if self.ids.get("trip_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/tracking/trips/{self.ids['trip_1']}/", 200,
                         "GET trip by ID")

        # Trip statistics
        if self.ids.get("trip_1"):
            self.request(self.passenger_session, "GET",
                         f"/api/v1/tracking/trips/{self.ids['trip_1']}/statistics/", 200,
                         "GET trip statistics")

        # End trip
        if self.ids.get("trip_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/tracking/trips/{self.ids['trip_1']}/end/", 200,
                         "Driver — end trip",
                         json_body={"end_stop": self.ids.get("stop_3")})

        # Trip history
        self.request(self.driver_session, "GET", "/api/v1/tracking/trips/history/", 200,
                     "Driver — trip history")

        # Active buses (public)
        self.request(self.anon_session, "GET", "/api/v1/tracking/active-buses/", 200,
                     "Public — active buses")

        # Estimate arrival (must be before stop_tracking — needs active trip)
        if self.ids.get("stop_1"):
            self.request(self.driver_session, "POST",
                         "/api/v1/tracking/locations/estimate_arrival/", 200,
                         "Driver — estimate arrival",
                         json_body={"stop_id": self.ids["stop_1"]})

        # Stop tracking (driver)
        self.request(self.driver_session, "POST",
                     "/api/v1/tracking/bus-lines/stop_tracking/", 200,
                     "Driver — stop tracking on bus-line")

    def phase_10_waiting_system(self):
        self._phase(10, "Waiting System & Reports")

        # Waiting passengers (passenger reports)
        if self.ids.get("stop_1") and self.ids.get("line_1"):
            resp = self.request(self.passenger_session, "POST",
                                "/api/v1/tracking/waiting-passengers/", 201,
                                "Passenger — report waiting passengers",
                                json_body={
                                    "stop": self.ids["stop_1"],
                                    "line": self.ids["line_1"],
                                    "count": 12,
                                })
            if resp and resp.get("id"):
                self.ids["waiting_1"] = str(resp["id"])

        # List waiting passengers
        self.request(self.passenger_session, "GET", "/api/v1/tracking/waiting-passengers/", 200,
                     "List waiting passengers")

        # Waiting count report (passenger)
        if self.ids.get("stop_1"):
            report_data = {
                "stop": self.ids["stop_1"],
                "reported_count": 8,
                "confidence_level": "high",
                "reporter_latitude": ALGIERS_MARTYRS["latitude"],
                "reporter_longitude": ALGIERS_MARTYRS["longitude"],
            }
            if self.ids.get("bus_1"):
                report_data["bus"] = self.ids["bus_1"]
            if self.ids.get("line_1"):
                report_data["line"] = self.ids["line_1"]
            resp = self.request(self.passenger_session, "POST",
                                "/api/v1/tracking/waiting-reports/", 201,
                                "Passenger — create waiting count report",
                                json_body=report_data)
            if resp and resp.get("id"):
                self.ids["waiting_report_1"] = str(resp["id"])

        # List waiting reports
        self.request(self.passenger_session, "GET", "/api/v1/tracking/waiting-reports/", 200,
                     "List waiting count reports")

        # Verify report (driver)
        if self.ids.get("waiting_report_1"):
            self.request(self.driver_session, "POST",
                         f"/api/v1/tracking/waiting-reports/{self.ids['waiting_report_1']}/verify/",
                         200, "Driver — verify waiting report",
                         json_body={
                             "actual_count": 7,
                             "verification_status": "correct",
                             "notes": "Count was close",
                         })

        # Bus waiting list — join
        if self.ids.get("bus_1") and self.ids.get("stop_1"):
            self.request(self.passenger_session, "POST",
                         "/api/v1/tracking/bus-waiting-lists/join/", 201,
                         "Passenger — join bus waiting list",
                         json_body={
                             "bus_id": self.ids["bus_1"],
                             "stop_id": self.ids["stop_1"],
                         })

        # Waiting list summary (requires stop_id)
        summary_url = "/api/v1/tracking/bus-waiting-lists/summary/"
        if self.ids.get("stop_1"):
            summary_url += f"?stop_id={self.ids['stop_1']}"
        self.request(self.passenger_session, "GET", summary_url, 200,
                     "Waiting list summary")

        # Bus waiting list — leave
        if self.ids.get("bus_1") and self.ids.get("stop_1"):
            # Get waiting list ID first
            resp = self.request(self.passenger_session, "GET",
                                "/api/v1/tracking/bus-waiting-lists/", 200,
                                "List bus waiting lists")
            wl_id = None
            if resp:
                results = resp.get("results", resp) if isinstance(resp, dict) else resp
                if isinstance(results, list) and results:
                    wl_id = str(results[0].get("id", ""))
            if wl_id:
                self.request(self.passenger_session, "POST",
                             "/api/v1/tracking/bus-waiting-lists/leave/", 200,
                             "Passenger — leave bus waiting list",
                             json_body={"waiting_list_id": wl_id, "reason": "boarded"})

        # Anomaly (driver reports)
        resp = self.request(self.driver_session, "POST", "/api/v1/tracking/anomalies/", 201,
                            "Driver — report anomaly",
                            json_body={
                                "type": "schedule",
                                "description": f"Traffic jam on route {RUN_ID}",
                                "severity": "medium",
                                "location_latitude": ALGIERS_POSTE["latitude"],
                                "location_longitude": ALGIERS_POSTE["longitude"],
                            })
        if resp and resp.get("id"):
            self.ids["anomaly_1"] = str(resp["id"])

        # Resolve anomaly (admin)
        if self.ids.get("anomaly_1"):
            self.request(self.admin_session, "POST",
                         f"/api/v1/tracking/anomalies/{self.ids['anomaly_1']}/resolve/", 200,
                         "Admin — resolve anomaly",
                         json_body={"resolution_notes": "Traffic cleared"})

    def phase_11_gamification(self):
        self._phase(11, "Gamification & Reputation")

        # ── Tracking-level gamification ──
        self.request(self.passenger_session, "GET", "/api/v1/tracking/reputation/", 200,
                     "Tracking — list reputation scores")

        self.request(self.passenger_session, "GET", "/api/v1/tracking/reputation/my_stats/", 200,
                     "Tracking — my reputation stats")

        self.request(self.passenger_session, "GET", "/api/v1/tracking/reputation/leaderboard/", 200,
                     "Tracking — reputation leaderboard")

        self.request(self.passenger_session, "GET",
                     "/api/v1/tracking/virtual-currency/my_balance/", 200,
                     "Tracking — my virtual currency balance")

        self.request(self.passenger_session, "GET",
                     "/api/v1/tracking/virtual-currency/transactions/", 200,
                     "Tracking — currency transactions")

        self.request(self.passenger_session, "GET",
                     "/api/v1/tracking/virtual-currency/leaderboard/", 200,
                     "Tracking — currency leaderboard")

        self.request(self.driver_session, "GET", "/api/v1/tracking/driver-performance/", 200,
                     "Tracking — list driver performance")

        self.request(self.driver_session, "GET",
                     "/api/v1/tracking/driver-performance/my_stats/", 200,
                     "Tracking — driver my_stats")

        self.request(self.driver_session, "GET",
                     "/api/v1/tracking/driver-performance/leaderboard/", 200,
                     "Tracking — driver performance leaderboard")

        self.request(self.passenger_session, "GET", "/api/v1/tracking/premium-features/", 200,
                     "Tracking — list premium features")

        self.request(self.passenger_session, "GET",
                     "/api/v1/tracking/premium-features/available/", 200,
                     "Tracking — available premium features")

        self.request(self.passenger_session, "GET",
                     "/api/v1/tracking/user-premium-features/active/", 200,
                     "Tracking — active user premium features")

        self.request(self.driver_session, "GET",
                     "/api/v1/tracking/driver-currency/balance/", 200,
                     "Tracking — driver currency balance")

        self.request(self.driver_session, "GET",
                     "/api/v1/tracking/driver-currency/earnings_summary/", 200,
                     "Tracking — driver currency earnings summary")

        # ── Gamification app endpoints ──
        self.request(self.passenger_session, "GET", "/api/v1/gamification/profile/me/", 200,
                     "Gamification — my profile")

        self.request(self.passenger_session, "GET", "/api/v1/gamification/achievements/", 200,
                     "Gamification — list achievements")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/achievements/unlocked/", 200,
                     "Gamification — unlocked achievements")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/achievements/progress/", 200,
                     "Gamification — achievements progress")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/transactions/summary/", 200,
                     "Gamification — transactions summary")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/leaderboard/daily/", 200,
                     "Gamification — daily leaderboard")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/leaderboard/weekly/", 200,
                     "Gamification — weekly leaderboard")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/leaderboard/my_rank/", 200,
                     "Gamification — my rank")

        self.request(self.passenger_session, "GET", "/api/v1/gamification/challenges/", 200,
                     "Gamification — list challenges")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/challenges/my_challenges/", 200,
                     "Gamification — my challenges")

        self.request(self.passenger_session, "GET", "/api/v1/gamification/rewards/", 200,
                     "Gamification — list rewards")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/rewards/my_rewards/", 200,
                     "Gamification — my rewards")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/reputation/stats/", 200,
                     "Gamification — reputation stats")

        self.request(self.passenger_session, "GET",
                     "/api/v1/gamification/virtual-currency/balance/", 200,
                     "Gamification — virtual currency balance")

    def phase_12_notifications(self):
        self._phase(12, "Notifications")

        # Admin creates notification
        resp = self.request(self.admin_session, "POST",
                            "/api/v1/notifications/notifications/", 201,
                            "Admin — create notification",
                            json_body={
                                "notification_type": "system",
                                "title": f"Test notification {RUN_ID}",
                                "message": "This is a test system notification.",
                                "channel": "in_app",
                            })
        if resp and resp.get("id"):
            self.ids["notification_1"] = str(resp["id"])

        # List notifications
        self.request(self.passenger_session, "GET",
                     "/api/v1/notifications/notifications/", 200,
                     "Passenger — list notifications")

        # Unread count
        self.request(self.passenger_session, "GET",
                     "/api/v1/notifications/notifications/unread_count/", 200,
                     "Passenger — unread notification count")

        # Mark read
        if self.ids.get("notification_1"):
            self.request(self.passenger_session, "POST",
                         f"/api/v1/notifications/notifications/{self.ids['notification_1']}/mark_read/",
                         200, "Passenger — mark notification read")

        # Mark all read
        self.request(self.passenger_session, "POST",
                     "/api/v1/notifications/notifications/mark_all_read/", 200,
                     "Passenger — mark all notifications read")

        # Register device token
        resp = self.request(self.passenger_session, "POST",
                            "/api/v1/notifications/device-tokens/", 201,
                            "Passenger — register device token",
                            json_body={
                                "token": f"fcm_test_token_{RUN_ID}",
                                "device_type": "android",
                            })
        if resp and resp.get("id"):
            self.ids["device_token_1"] = str(resp["id"])

        # List device tokens
        self.request(self.passenger_session, "GET",
                     "/api/v1/notifications/device-tokens/", 200,
                     "Passenger — list device tokens")

        # List preferences
        self.request(self.passenger_session, "GET",
                     "/api/v1/notifications/preferences/", 200,
                     "Passenger — list notification preferences")

        # List schedules
        self.request(self.passenger_session, "GET",
                     "/api/v1/notifications/schedules/", 200,
                     "Passenger — list notification schedules")

        # Permission test: passenger creating system notification
        self.request(self.passenger_session, "POST",
                     "/api/v1/notifications/notifications/", 403,
                     "Permission: passenger create notification -> 403",
                     json_body={
                         "notification_type": "system",
                         "title": "Unauthorized",
                         "message": "Should fail",
                         "channel": "in_app",
                     })

    def phase_13_offline_mode(self):
        self._phase(13, "Offline Mode")

        self.request(self.passenger_session, "GET", "/api/v1/offline/config/", 200,
                     "Offline — list cache configurations")

        self.request(self.passenger_session, "GET", "/api/v1/offline/config/current/", 404,
                     "Offline — current cache config (none seeded)")

        self.request(self.passenger_session, "GET", "/api/v1/offline/cache/status/", 200,
                     "Offline — cache status")

        self.request(self.passenger_session, "POST", "/api/v1/offline/cache/sync/", 400,
                     "Offline — trigger cache sync (no active config)")

        self.request(self.passenger_session, "GET", "/api/v1/offline/cache/statistics/", 200,
                     "Offline — cache statistics")

        self.request(self.passenger_session, "GET", "/api/v1/offline/data/lines/", 200,
                     "Offline — cached lines data")

        self.request(self.passenger_session, "GET", "/api/v1/offline/data/stops/", 200,
                     "Offline — cached stops data")

        self.request(self.passenger_session, "GET", "/api/v1/offline/data/schedules/", 200,
                     "Offline — cached schedules data")

        self.request(self.passenger_session, "GET", "/api/v1/offline/data/buses/", 200,
                     "Offline — cached buses data")

        self.request(self.passenger_session, "GET", "/api/v1/offline/data/notifications/", 200,
                     "Offline — cached notifications data")

        self.request(self.passenger_session, "POST",
                     "/api/v1/offline/sync-queue/queue_action/", 201,
                     "Offline — queue sync action",
                     json_body={
                         "action_type": "create",
                         "model_name": "waiting_report",
                         "data": {"stop_id": self.ids.get("stop_1", ""), "count": 5},
                     })

        self.request(self.passenger_session, "GET",
                     "/api/v1/offline/sync-queue/pending/", 200,
                     "Offline — list pending sync actions")

        self.request(self.passenger_session, "GET", "/api/v1/offline/logs/", 200,
                     "Offline — list logs")

        self.request(self.passenger_session, "GET", "/api/v1/offline/logs/summary/", 200,
                     "Offline — logs summary")

    def phase_14_cleanup_and_edge_cases(self):
        self._phase(14, "Cleanup & Edge Cases")

        # Logout
        if self.ids.get("passenger_refresh"):
            self.request(self.passenger_session, "POST", "/api/v1/accounts/users/logout/", 200,
                         "Passenger — logout",
                         json_body={"refresh": self.ids["passenger_refresh"]})

        # Soft delete tests
        if self.ids.get("bus_1"):
            self.request(self.admin_session, "DELETE",
                         f"/api/v1/buses/buses/{self.ids['bus_1']}/", 204,
                         "Admin — delete bus (soft delete)")

        if self.ids.get("stop_3"):
            self.request(self.admin_session, "DELETE",
                         f"/api/v1/lines/stops/{self.ids['stop_3']}/", 204,
                         "Admin — delete stop (soft delete)")

        # Unauthenticated access
        self.request(self.anon_session, "GET", "/api/v1/accounts/users/me/", 401,
                     "Anon — access /users/me/ -> 401")

        self.request(self.anon_session, "GET", "/api/v1/buses/buses/", 401,
                     "Anon — access /buses/ -> 401")

        self.request(self.anon_session, "GET", "/api/v1/tracking/trips/", 401,
                     "Anon — access /trips/ -> 401")

        # Invalid UUID
        self.request(self.admin_session, "GET",
                     "/api/v1/buses/buses/00000000-0000-0000-0000-000000000000/", 404,
                     "Invalid UUID — non-existent bus -> 404")

        self.request(self.admin_session, "GET",
                     "/api/v1/lines/stops/00000000-0000-0000-0000-000000000000/", 404,
                     "Invalid UUID — non-existent stop -> 404")

        # Empty body on required-body endpoint
        self.request(self.admin_session, "POST", "/api/v1/lines/stops/", 400,
                     "Empty body — create stop -> 400",
                     json_body={})

        self.request(self.admin_session, "POST", "/api/v1/accounts/register/", 400,
                     "Empty body — register user -> 400",
                     json_body={})

    # ── Runner ──────────────────────────────────────────────────────────────

    def _print_summary(self):
        total = self.passed + self.failed
        self._write(f"\n{'=' * 78}")
        self._write(f"  FINAL SUMMARY")
        self._write(f"{'=' * 78}")
        self._write(f"  Total tests:  {total}")
        self._write(f"  Passed:       {self.passed}")
        self._write(f"  Failed:       {self.failed}")
        if self.errors:
            self._write(f"\n  FAILURES ({len(self.errors)}):")
            for i, err in enumerate(self.errors, 1):
                self._write(f"    {i}. {err}")
        else:
            self._write(f"\n  ALL TESTS PASSED!")
        self._write(f"{'=' * 78}")
        self._write(f"  Log file: {self._log_file.name}")
        self._write(f"  Run ID:   {RUN_ID}")
        self._write(f"{'=' * 78}\n")

    def run(self):
        phases = [
            (1, self.phase_01_health_and_schema),
            (2, self.phase_02_authentication),
            (3, self.phase_03_user_registration),
            (4, self.phase_04_driver_registration),
            (5, self.phase_05_user_profile_management),
            (6, self.phase_06_driver_management),
            (7, self.phase_07_stops_and_lines),
            (8, self.phase_08_buses),
            (9, self.phase_09_tracking),
            (10, self.phase_10_waiting_system),
            (11, self.phase_11_gamification),
            (12, self.phase_12_notifications),
            (13, self.phase_13_offline_mode),
            (14, self.phase_14_cleanup_and_edge_cases),
        ]

        self._write(f"\n{'=' * 78}")
        self._write(f"  DZ Bus Tracker — API Integration Tests")
        self._write(f"  Base URL:  {self.BASE_URL}")
        self._write(f"  Admin:     {self.admin_email}")
        self._write(f"  Run ID:    {RUN_ID}")
        self._write(f"  Timestamp: {datetime.now().isoformat()}")
        self._write(f"{'=' * 78}\n")

        start_time = time.time()

        try:
            for num, fn in phases:
                if self.phase is not None and num != self.phase:
                    continue
                if self.skip_cleanup and num == 14:
                    self._write("\n  [SKIPPED] Phase 14 (cleanup) — --skip-cleanup flag set")
                    continue

                # For single-phase runs, we need auth setup first
                if self.phase is not None and num > 2 and not self.ids.get("admin_access"):
                    self._write("\n  [AUTO] Running Phase 2 (auth) as prerequisite...")
                    self.phase_02_authentication()

                fn()
        except KeyboardInterrupt:
            self._write("\n\n  [INTERRUPTED] Test run aborted by user.\n")
        except Exception as e:
            self._write(f"\n\n  [FATAL ERROR] {type(e).__name__}: {e}\n")
            import traceback
            self._log_file.write(traceback.format_exc())
        finally:
            elapsed = time.time() - start_time
            self._write(f"\n  Elapsed: {elapsed:.1f}s")
            self._print_summary()
            self._log_file.close()

        return self.failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="DZ Bus Tracker — Comprehensive API Test Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python api_test.py                                  # Run all phases
  python api_test.py --base-url http://X:8007         # Custom server
  python api_test.py --phase 7                        # Single phase
  python api_test.py --skip-cleanup                   # Keep test data
  python api_test.py --admin-email me@x.com --admin-password pass
        """,
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--admin-email", default=DEFAULT_ADMIN_EMAIL,
        help=f"Admin email (default: {DEFAULT_ADMIN_EMAIL})",
    )
    parser.add_argument(
        "--admin-password", default=DEFAULT_ADMIN_PASSWORD,
        help="Admin password",
    )
    parser.add_argument(
        "--phase", type=int, default=None, choices=range(1, 15),
        help="Run only a specific phase (1-14)",
    )
    parser.add_argument(
        "--skip-cleanup", action="store_true",
        help="Skip phase 14 (cleanup/edge cases) — keep test data",
    )
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--log-file", default=None,
        help=f"Path to log file (default: api_test_<RUN_ID>.log)",
    )
    args = parser.parse_args()

    tester = DZBusTrackerAPITester(
        base_url=args.base_url,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        timeout=args.timeout,
        log_file=args.log_file,
        phase=args.phase,
        skip_cleanup=args.skip_cleanup,
    )
    success = tester.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
