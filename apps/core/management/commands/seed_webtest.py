"""
Management command to seed fixed test users and data for web UI tests.
Idempotent — safe to run multiple times.

Usage:
    DB_PORT=15432 DB_NAME=dz_bus_tracker_db DB_USER=postgres DB_PASSWORD="99999999." \\
        DB_HOST=127.0.0.1 python manage.py seed_webtest
"""
import logging
from datetime import timedelta, date

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Seed fixed test users with realistic data for web UI tests (idempotent)'

    def add_arguments(self, parser):
        parser.add_argument('--pass-email', default='fixed_pass@dzbus.com')
        parser.add_argument('--pass-password', default='FixedPass+114')
        parser.add_argument('--drv-email', default='fixed_drv@dzbus.com')
        parser.add_argument('--drv-password', default='FixedDrv+114')
        parser.add_argument('--live-email', default='fixed_live@dzbus.com')
        parser.add_argument('--live-password', default='FixedLive+114')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding web test data...'))

        pass_email = options['pass_email']
        pass_pwd = options['pass_password']
        drv_email = options['drv_email']
        drv_pwd = options['drv_password']
        live_email = options['live_email']
        live_pwd = options['live_password']

        # ── 1. Ensure fixed passenger ────────────────────────────────────────
        pass_user = self._ensure_passenger(pass_email, pass_pwd)
        if pass_user:
            self.stdout.write(f'  ✓ Fixed passenger: {pass_email}')
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed to create passenger: {pass_email}'))

        # ── 2. Ensure fixed driver ───────────────────────────────────────────
        drv_user, drv_driver = self._ensure_driver(drv_email, drv_pwd, 'FixedDrv', 'Test')
        if drv_driver:
            self.stdout.write(f'  ✓ Fixed driver: {drv_email}')
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed to create driver: {drv_email}'))

        # ── 3. Ensure fixed live driver ──────────────────────────────────────
        live_user, live_driver = self._ensure_driver(live_email, live_pwd, 'FixedLive', 'Active')
        if live_driver:
            self.stdout.write(f'  ✓ Fixed live driver: {live_email}')
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed to create live driver: {live_email}'))

        # ── 4. Ensure a seed line + stops exist ──────────────────────────────
        line, stops = self._ensure_line_and_stops()
        if line:
            self.stdout.write(f'  ✓ Seed line: {line.name} ({len(stops)} stops)')

        # ── 5. Ensure fixed driver has a bus and completed trips ─────────────
        if drv_driver and line and stops:
            drv_bus = self._ensure_bus(drv_driver, 'FIXDRV-001', 'Karsan Jest', 2023)
            if drv_bus:
                self.stdout.write(f'  ✓ Fixed driver bus: {drv_bus.license_plate}')
                self._seed_completed_trips(drv_driver, drv_bus, line, stops[0], count=5)
                self.stdout.write('  ✓ Seeded 5 completed trips for fixed driver')

        # ── 6. Ensure fixed live driver has bus + ACTIVE trip + GPS ─────────
        if live_driver and line and stops:
            live_bus = self._ensure_bus(live_driver, 'FIXLIV-001', 'Karsan Star', 2024)
            if live_bus:
                self.stdout.write(f'  ✓ Fixed live driver bus: {live_bus.license_plate}')
                self._ensure_active_trip(live_driver, live_bus, line, stops[0])
                self.stdout.write('  ✓ Active trip seeded for live driver')

        # ── 7. Seed waiting reports for passenger → earn coins ───────────────
        if pass_user and stops:
            self._seed_waiting_reports(pass_user, stops)
            self.stdout.write('  ✓ Waiting reports seeded for fixed passenger')

        # ── 8. Seed anomalies for the fixed driver's bus ────────────────────
        if drv_driver:
            from apps.buses.selectors import get_buses_by_driver
            buses = get_buses_by_driver(drv_driver.id)
            if buses:
                self._seed_anomalies(buses.first())
                self.stdout.write('  ✓ Anomalies seeded')

        # ── 9. Advance live bus GPS along the route ───────────────────────
        if live_driver and line and stops:
            from apps.buses.models import Bus as BusModel
            live_bus_qs = BusModel.objects.filter(license_plate='FIXLIV-001')
            if live_bus_qs.exists():
                self._advance_bus_gps(live_bus_qs.first(), stops)
                self.stdout.write('  ✓ Live bus GPS advanced along route')

        # ── 10. Seed notifications for fixed passenger ────────────────────────
        if pass_user:
            self._seed_notifications(pass_user, drv_driver)
            self.stdout.write('  ✓ Notifications seeded for fixed passenger')

        self.stdout.write(self.style.SUCCESS('Seed complete!'))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _advance_bus_gps(self, bus, stops):
        """Push a fresh GPS location that advances along the route each call.

        The bus cycles through 3 positions: approaching stop-0, halfway to
        stop-0, and close to stop-0.  Using the current LocationUpdate count
        mod 3 to determine position so each run moves the bus forward.
        """
        from apps.tracking.models import LocationUpdate, Trip, BusLine
        import math

        # Positions: start→alpha stop, interpolated
        start = (36.7372, 3.0869)
        stop_alpha = (float(stops[0].latitude), float(stops[0].longitude))
        stop_beta  = (float(stops[1].latitude), float(stops[1].longitude))

        # Count existing GPS updates to determine step (cycles 0-5)
        count = LocationUpdate.objects.filter(bus=bus).count()
        step = count % 8  # 8-step cycle

        def lerp(a, b, t):
            return (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)

        if step < 4:
            # Approaching stop_alpha (0% → 75%)
            t = step / 4.0 * 0.75
            pos = lerp(start, stop_alpha, t)
        else:
            # Approaching stop_beta (stop_alpha → 75% to beta)
            t = (step - 4) / 4.0 * 0.75
            pos = lerp(stop_alpha, stop_beta, t)

        lat, lon = pos
        # Speed decreases as it approaches a stop
        speed = 35.0 - (step % 4) * 5.0  # 35, 30, 25, 20 km/h

        active_trip = Trip.objects.filter(bus=bus, end_time__isnull=True).first()
        try:
            LocationUpdate.objects.create(
                bus=bus,
                trip_id=active_trip.id if active_trip else None,
                latitude=str(round(lat, 7)),
                longitude=str(round(lon, 7)),
                speed=str(speed),
                heading='315.0',  # Northwest toward Algiers centre
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    GPS advance: {e}'))

    def _seed_notifications(self, user, drv_driver=None):
        """Create realistic notification records for the passenger user."""
        from apps.notifications.models import Notification
        now = timezone.now()
        notifications = [
            ('bus_arrival', 'Bus arriving soon',
             'Bus FIXLIV-001 on FixedTest Line 01 will arrive at Stop Alpha in ~4 minutes.',
             False, now - timedelta(minutes=3)),
            ('achievement', 'Achievement Unlocked!',
             'You earned the "Reporter" badge for submitting 5 waiting reports. +150 coins!',
             True,  now - timedelta(hours=1)),
            ('system', 'Welcome to DZ Bus Tracker',
             'Track buses in real time, report waiting counts, and earn coins for your contributions!',
             True,  now - timedelta(days=1)),
            ('tracking', 'Bus delayed',
             'Bus FIXLIV-001 is running ~8 minutes late on FixedTest Line 01 due to traffic.',
             False, now - timedelta(minutes=30)),
            ('reward', 'Coins credited',
             'You received 50 coins for your accurate waiting count report at Stop Beta.',
             True,  now - timedelta(hours=3)),
        ]
        for ntype, title, msg, is_read, created in notifications:
            if Notification.objects.filter(user=user, title=title).exists():
                continue
            try:
                n = Notification(
                    user=user,
                    notification_type=ntype,
                    title=title,
                    message=msg,
                    channel='push',
                    is_read=is_read,
                )
                n.save()
                # Manually set created_at using update to get historical timestamps
                Notification.objects.filter(pk=n.pk).update(created_at=created)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'    Notification "{title[:30]}": {e}'))

    def _ensure_passenger(self, email: str, password: str):
        """Create or return existing passenger user."""
        try:
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name='Fixed',
                    last_name='Passenger',
                    user_type='passenger',
                    phone_number='+213555100200',
                    is_active=True,
                )
                self.stdout.write(f'    Created passenger: {email}')
            else:
                user.set_password(password)
                user.is_active = True
                user.save()
                self.stdout.write(f'    Passenger already exists: {email}')
            return user
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    Error creating passenger: {e}'))
            return None

    def _ensure_driver(self, email: str, password: str, first: str, last: str):
        """Create or return existing driver user + driver profile."""
        from apps.drivers.models import Driver
        try:
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first,
                    last_name=last,
                    user_type='driver',
                    phone_number=f'+213555{abs(hash(email)) % 1000000:06d}',
                    is_active=True,
                )
                self.stdout.write(f'    Created driver user: {email}')
            else:
                user.set_password(password)
                user.is_active = True
                user.user_type = 'driver'
                user.save()

            # Ensure driver profile
            driver = Driver.objects.filter(user=user).first()
            if not driver:
                # Save a minimal placeholder PNG image for required photo fields
                import os, struct, zlib
                from django.core.files.base import ContentFile

                def _tiny_png():
                    def chunk(name, d):
                        c = struct.pack('>I', len(d)) + name + d
                        crc = zlib.crc32(name + d) & 0xffffffff
                        return c + struct.pack('>I', crc)
                    sig = b'\x89PNG\r\n\x1a\n'
                    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                    idat = chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff'))
                    iend = chunk(b'IEND', b'')
                    return sig + ihdr + idat + iend

                png_content = ContentFile(_tiny_png(), name='placeholder.png')
                driver = Driver(
                    user=user,
                    phone_number=f'+213555{abs(hash(email)) % 1000000:06d}',
                    id_card_number=f'IC{abs(hash(email)) % 10000000:07d}',
                    driver_license_number=f'DL{abs(hash(email)) % 10000000:07d}',
                    years_of_experience=5,
                    status='approved',
                    is_available=True,
                )
                driver.id_card_photo.save('id_placeholder.png', png_content, save=False)
                driver.driver_license_photo.save('lic_placeholder.png', png_content, save=False)
                driver.save()
                self.stdout.write(f'    Created driver profile for: {email}')
            else:
                driver.status = 'approved'
                driver.is_available = True
                driver.save()

            return user, driver
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    Error creating driver {email}: {e}'))
            return None, None

    def _ensure_line_and_stops(self):
        """Ensure seed line and stops exist."""
        from apps.lines.models import Line, Stop, LineStop
        try:
            # Create or get stops
            stops_data = [
                ('FixedTest Stop Alpha', '36.7538', '3.0588', 'Place des Martyrs, Alger'),
                ('FixedTest Stop Beta',  '36.7620', '3.0550', 'Grande Poste, Alger'),
                ('FixedTest Stop Gamma', '36.7725', '3.0420', 'Ben Aknoun, Alger'),
            ]
            stops = []
            for name, lat, lon, addr in stops_data:
                stop, _ = Stop.objects.get_or_create(
                    name=name,
                    defaults={'latitude': lat, 'longitude': lon, 'address': addr}
                )
                stops.append(stop)

            # Create or get line
            line, created = Line.objects.get_or_create(
                name='FixedTest Line 01',
                defaults={'code': 'FTL01'}
            )
            if created:
                for order, stop in enumerate(stops, start=1):
                    LineStop.objects.get_or_create(
                        line=line, stop=stop,
                        defaults={'order': order}
                    )
                self.stdout.write(f'    Created line: {line.name}')
            else:
                self.stdout.write(f'    Line already exists: {line.name}')

            return line, stops
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    Error ensuring line/stops: {e}'))
            return None, []

    def _ensure_bus(self, driver, plate: str, model: str, year: int):
        """Create or return existing approved bus for driver."""
        from apps.buses.models import Bus
        try:
            bus = Bus.objects.filter(license_plate=plate).first()
            if not bus:
                bus = Bus.objects.create(
                    license_plate=plate,
                    model=model,
                    manufacturer='Karsan',
                    year=year,
                    capacity=40,
                    is_air_conditioned=True,
                    driver=driver,
                    status='active',
                    is_approved=True,
                    is_active=True,
                )
                self.stdout.write(f'    Created bus: {plate}')
            else:
                bus.status = 'active'
                bus.is_approved = True
                bus.is_active = True
                bus.driver = driver
                bus.save()
            return bus
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    Error creating bus {plate}: {e}'))
            return None

    def _seed_completed_trips(self, driver, bus, line, start_stop, count: int = 5):
        """Seed completed trips for the driver."""
        from apps.tracking.models import Trip
        existing = Trip.objects.filter(bus=bus, end_time__isnull=False, is_completed=True).count()
        trips_needed = max(0, count - existing)
        for i in range(trips_needed):
            start_dt = timezone.now() - timedelta(days=i + 1, hours=9)
            end_dt = start_dt + timedelta(hours=2)
            try:
                Trip.objects.create(
                    bus=bus,
                    driver=driver,
                    line=line,
                    start_stop=start_stop,
                    start_time=start_dt,
                    end_time=end_dt,
                    is_completed=True,
                    max_passengers=15 + i,
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'    Trip {i} create: {e}'))

    def _ensure_active_trip(self, driver, bus, line, start_stop):
        """Ensure there is exactly one active trip for the live driver's bus,
        and a BusLine record with tracking_status='active' (used by active-buses endpoint)."""
        from apps.tracking.models import Trip, BusLine

        # Check for existing active trip (not completed, no end_time)
        active_trips = Trip.objects.filter(bus=bus, end_time__isnull=True, is_completed=False)
        if active_trips.exists():
            self.stdout.write(f'    Active trip already exists for bus {bus.license_plate}')
            trip = active_trips.first()
        else:
            trip = Trip.objects.create(
                bus=bus,
                driver=driver,
                line=line,
                start_stop=start_stop,
                start_time=timezone.now() - timedelta(minutes=30),
                is_completed=False,
                max_passengers=12,
            )
            self.stdout.write(f'    Created active trip: {trip.id}')

        # Ensure BusLine record with tracking_status='active'
        bus_line, created = BusLine.objects.get_or_create(
            bus=bus, line=line,
            defaults={
                'is_active': True,
                'tracking_status': 'active',
                'trip_id': trip.id,
                'start_time': trip.start_time,
            }
        )
        if not created:
            bus_line.tracking_status = 'active'
            bus_line.trip_id = trip.id
            bus_line.start_time = trip.start_time
            bus_line.is_active = True
            bus_line.save()

        # Push a fresh GPS location
        try:
            from apps.tracking.models import LocationUpdate
            LocationUpdate.objects.create(
                bus=bus,
                trip_id=trip.id,
                latitude='36.7372',
                longitude='3.0869',
                speed='35.0',
                heading='90.0',
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    GPS location: {e}'))

    def _seed_waiting_reports(self, user, stops):
        """Submit waiting reports for passenger to earn coins."""
        from apps.tracking.models import WaitingCountReport
        from apps.tracking.services.waiting_service import WaitingReportService
        existing = WaitingCountReport.objects.filter(reporter=user).count()
        needed = max(0, 10 - existing)
        for i in range(needed):
            stop = stops[i % len(stops)]
            try:
                WaitingReportService.create_report(
                    reporter_id=str(user.id),
                    stop_id=str(stop.id),
                    reported_count=5 + i,
                    confidence_level='high',
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'    Waiting report {i}: {e}'))

    def _seed_anomalies(self, bus):
        """Create anomaly records for the given bus."""
        from apps.tracking.models import Anomaly
        existing = Anomaly.objects.filter(bus=bus, resolved=False).count()
        if existing >= 2:
            return
        anomalies = [
            ('speed', 'Bus exceeded speed limit (90 km/h in 60 zone)', 'high',
             '36.7538', '3.0588'),
            ('route', 'Bus deviated 500m from assigned route', 'medium',
             '36.7620', '3.0550'),
        ]
        for atype, desc, severity, lat, lon in anomalies:
            try:
                Anomaly.objects.create(
                    bus=bus,
                    type=atype,
                    description=desc,
                    severity=severity,
                    location_latitude=lat,
                    location_longitude=lon,
                    resolved=False,
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'    Anomaly {atype}: {e}'))
