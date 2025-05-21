"""
Celery tasks for the tracking app.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import F
from django.utils import timezone

from apps.core.utils.geo import calculate_distance

from .models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)
from .services import AnomalyService

logger = logging.getLogger(__name__)


@shared_task
def process_location_updates():
    """
    Process location updates, calculating statistics and detecting anomalies.
    """
    try:
        # Get active bus-line assignments
        bus_lines = BusLine.objects.filter(
            is_active=True,
            tracking_status="active",
        )

        for bus_line in bus_lines:
            # Get latest location updates
            location_updates = LocationUpdate.objects.filter(
                bus_id=bus_line.bus_id,
                created_at__gte=timezone.now() - timedelta(minutes=60),
            ).order_by("-created_at")[:2]

            if len(location_updates) < 2:
                continue

            # Calculate speed if not provided
            current = location_updates[0]
            previous = location_updates[1]

            if not current.speed:
                time_diff = (current.created_at - previous.created_at).total_seconds() / 3600

                if time_diff > 0:
                    distance = calculate_distance(
                        float(previous.latitude),
                        float(previous.longitude),
                        float(current.latitude),
                        float(current.longitude)
                    )

                    if distance:
                        speed = distance / time_diff
                        current.speed = speed
                        current.save(update_fields=["speed"])

            # Detect anomalies
            if current.speed and float(current.speed) > 100:  # Example threshold
                AnomalyService.detect_speed_anomaly(
                    bus_id=bus_line.bus_id,
                    speed=float(current.speed),
                    latitude=current.latitude,
                    longitude=current.longitude,
                )

            # Detect route deviations
            AnomalyService.detect_route_deviation(
                bus_id=bus_line.bus_id,
                latitude=current.latitude,
                longitude=current.longitude,
                line_id=bus_line.line_id,
            )

        logger.info("Processed location updates")
        return True

    except Exception as e:
        logger.error(f"Error processing location updates: {e}")
        return False


@shared_task
def calculate_eta_for_stops():
    """
    Calculate ETA for buses to stops.
    """
    try:
        # Get active bus-line assignments
        bus_lines = BusLine.objects.filter(
            is_active=True,
            tracking_status="active",
        )

        for bus_line in bus_lines:
            # Get latest location update
            try:
                location = LocationUpdate.objects.filter(
                    bus_id=bus_line.bus_id
                ).latest("created_at")
            except LocationUpdate.DoesNotExist:
                continue

            # Get stops for the line
            from apps.lines.selectors import get_stops_by_line
            stops = get_stops_by_line(bus_line.line_id)

            # Calculate ETA for each stop
            for stop in stops:
                from apps.core.utils.geo import calculate_eta

                eta = calculate_eta(
                    float(location.latitude),
                    float(location.longitude),
                    float(stop.latitude),
                    float(stop.longitude),
                    float(location.speed) if location.speed else None
                )

                if eta:
                    # Store ETA in cache
                    from django.core.cache import cache

                    cache_key = f"eta:{bus_line.bus_id}:{stop.id}"
                    cache.set(cache_key, eta.isoformat(), 300)  # 5 minutes

        logger.info("Calculated ETA for stops")
        return True

    except Exception as e:
        logger.error(f"Error calculating ETA for stops: {e}")
        return False


@shared_task
def clean_old_location_data():
    """
    Clean old location data to prevent database bloat.
    """
    try:
        # Get retention period from settings
        from django.conf import settings

        retention_days = getattr(
            settings, "BUS_LOCATION_HISTORY_RETENTION", 7
        )
        cutoff_date = timezone.now() - timedelta(days=retention_days)

        # Delete old location updates
        count = LocationUpdate.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]

        logger.info(f"Cleaned {count} old location updates")

        # Delete old passenger counts
        passenger_retention_days = getattr(
            settings, "PASSENGER_COUNT_HISTORY_RETENTION", 30
        )
        passenger_cutoff_date = timezone.now() - timedelta(days=passenger_retention_days)

        count = PassengerCount.objects.filter(
            created_at__lt=passenger_cutoff_date
        ).delete()[0]

        logger.info(f"Cleaned {count} old passenger counts")

        # Delete old waiting passengers
        count = WaitingPassengers.objects.filter(
            created_at__lt=passenger_cutoff_date
        ).delete()[0]

        logger.info(f"Cleaned {count} old waiting passengers records")

        return True

    except Exception as e:
        logger.error(f"Error cleaning old location data: {e}")
        return False


@shared_task
def detect_anomalies():
    """
    Detect anomalies in bus tracking data.
    """
    try:
        # Detect bus bunching (multiple buses close together on the same line)
        from django.db import connection

        # This is a simplified approach and would need to be optimized in production
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT l1.bus_id, l2.bus_id, l1.line_id, 
                       l1.latitude, l1.longitude, l2.latitude, l2.longitude
                FROM tracking_locationupdate l1
                JOIN tracking_locationupdate l2 ON 
                    l1.line_id = l2.line_id AND 
                    l1.bus_id != l2.bus_id AND
                    l1.created_at >= %s AND
                    l2.created_at >= %s
                WHERE l1.id > l2.id
                ORDER BY l1.created_at DESC, l2.created_at DESC
            """, [timezone.now() - timedelta(minutes=10), timezone.now() - timedelta(minutes=10)])

            bunching_candidates = cursor.fetchall()

        for row in bunching_candidates:
            bus1_id, bus2_id, line_id, lat1, lon1, lat2, lon2 = row

            distance = calculate_distance(
                float(lat1), float(lon1),
                float(lat2), float(lon2)
            )

            if distance and distance < 0.5:  # If buses are less than 500m apart
                # Check if there's already an anomaly for this
                if not Anomaly.objects.filter(
                        bus_id=bus1_id,
                        type="bunching",
                        created_at__gte=timezone.now() - timedelta(minutes=30),
                        resolved=False
                ).exists():
                    AnomalyService.create_anomaly(
                        bus_id=bus1_id,
                        anomaly_type="bunching",
                        description=f"Bus bunching detected: {bus1_id} and {bus2_id} are {distance:.2f} km apart on line {line_id}",
                        severity="medium",
                        location_latitude=lat1,
                        location_longitude=lon1,
                    )

        # Detect service gaps (long time between buses)
        lines = LocationUpdate.objects.values('line_id').distinct()

        for line_data in lines:
            line_id = line_data['line_id']
            if not line_id:
                continue

            # Get the latest update for each bus on this line
            latest_updates = LocationUpdate.objects.filter(
                line_id=line_id
            ).values('bus_id').annotate(
                latest=models.Max('created_at')
            )

            if len(latest_updates) < 2:
                continue

            # Sort by time
            sorted_updates = sorted(latest_updates, key=lambda x: x['latest'])

            # Check gaps between buses
            for i in range(len(sorted_updates) - 1):
                gap = (sorted_updates[i + 1]['latest'] - sorted_updates[i]['latest']).total_seconds() / 60

                # If gap is more than 30 minutes, create anomaly
                if gap > 30:
                    if not Anomaly.objects.filter(
                            bus_id=sorted_updates[i + 1]['bus_id'],
                            type="gap",
                            created_at__gte=timezone.now() - timedelta(minutes=30),
                            resolved=False
                    ).exists():
                        # Get bus location
                        location = LocationUpdate.objects.filter(
                            bus_id=sorted_updates[i + 1]['bus_id'],
                            created_at=sorted_updates[i + 1]['latest']
                        ).first()

                        if location:
                            AnomalyService.create_anomaly(
                                bus_id=sorted_updates[i + 1]['bus_id'],
                                anomaly_type="gap",
                                description=f"Service gap detected: {gap:.1f} minutes between buses on line {line_id}",
                                severity="low",
                                location_latitude=location.latitude,
                                location_longitude=location.longitude,
                            )

        logger.info("Detected anomalies")
        return True

    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        return False