"""
Celery tasks for tracking-related operations.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Avg, Count, F, Max, Min, Sum
from django.utils import timezone

from apps.tracking.models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)
from tasks.base import RetryableTask

logger = logging.getLogger(__name__)


@shared_task(base=RetryableTask)
def process_location_updates():
    """
    Process location updates, calculating statistics and detecting anomalies.
    """
    try:
        # Get recent location updates
        cutoff_time = timezone.now() - timedelta(minutes=15)

        recent_updates = LocationUpdate.objects.filter(
            created_at__gte=cutoff_time,
            processed=False,
        ).select_related("bus")

        for update in recent_updates:
            # Calculate speed if not provided
            if not update.speed:
                # Get previous update
                try:
                    prev_update = LocationUpdate.objects.filter(
                        bus=update.bus,
                        created_at__lt=update.created_at,
                    ).latest("created_at")

                    # Calculate time difference
                    time_diff = (update.created_at - prev_update.created_at).total_seconds() / 3600

                    if time_diff > 0:
                        # Calculate distance
                        from apps.core.utils.geo import calculate_distance

                        distance = calculate_distance(
                            float(prev_update.latitude),
                            float(prev_update.longitude),
                            float(update.latitude),
                            float(update.longitude),
                        )

                        if distance:
                            # Calculate speed
                            speed = distance / time_diff
                            update.speed = speed
                except LocationUpdate.DoesNotExist:
                    pass

            # Find nearest stop
            if update.line:
                from apps.tracking.services import LocationUpdateService

                nearest_stop, distance = LocationUpdateService.find_nearest_stop(
                    latitude=update.latitude,
                    longitude=update.longitude,
                    line_id=update.line_id,
                )

                if nearest_stop:
                    update.nearest_stop = nearest_stop
                    update.distance_to_stop = distance

            # Mark as processed
            update.processed = True
            update.save()

            # Detect anomalies
            if update.speed and float(update.speed) > 100:  # Example threshold
                from apps.tracking.services import AnomalyService

                AnomalyService.detect_speed_anomaly(
                    bus_id=update.bus_id,
                    speed=float(update.speed),
                    latitude=update.latitude,
                    longitude=update.longitude,
                )

        logger.info(f"Processed {recent_updates.count()} location updates")
        return True

    except Exception as e:
        logger.error(f"Error processing location updates: {e}")
        return False


@shared_task(base=RetryableTask)
def calculate_eta():
    """
    Calculate ETA for buses to stops.
    """
    try:
        # Get active bus lines
        bus_lines = BusLine.objects.filter(
            is_active=True,
            tracking_status="active",
        ).select_related("bus", "line")

        for bus_line in bus_lines:
            # Get latest location update
            try:
                location = LocationUpdate.objects.filter(
                    bus=bus_line.bus,
                ).latest("created_at")
            except LocationUpdate.DoesNotExist:
                continue

            # Get line stops
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
                    float(location.speed) if location.speed else None,
                )

                if eta:
                    # Store ETA in cache
                    from django.core.cache import cache

                    cache_key = f"eta:{bus_line.bus_id}:{stop.id}"
                    cache.set(cache_key, eta.isoformat(), 300)  # 5 minutes

        logger.info(f"Calculated ETA for {bus_lines.count()} active buses")
        return True

    except Exception as e:
        logger.error(f"Error calculating ETA: {e}")
        return False


@shared_task(base=RetryableTask)
def detect_anomalies():
    """
    Detect anomalies in tracking data.
    """
    try:
        # Define detection timeframe
        cutoff_time = timezone.now() - timedelta(minutes=30)

        # Get active trips
        active_trips = Trip.objects.filter(
            is_completed=False,
            start_time__lte=timezone.now(),
        ).select_related("bus", "line", "driver")

        for trip in active_trips:
            # Get recent location updates
            location_updates = LocationUpdate.objects.filter(
                bus=trip.bus,
                created_at__gte=cutoff_time,
            ).order_by("created_at")

            if not location_updates.exists():
                # No recent updates - possible tracking issue
                from apps.tracking.services import AnomalyService

                AnomalyService.create_anomaly(
                    bus_id=trip.bus_id,
                    anomaly_type="tracking",
                    description=f"No location updates received since {cutoff_time}",
                    severity="medium",
                    trip=trip,
                )

                continue

            # Check for speed anomalies
            for update in location_updates:
                if update.speed and float(update.speed) > 100:  # Example threshold
                    from apps.tracking.services import AnomalyService

                    # Check if anomaly already exists
                    if not Anomaly.objects.filter(
                            bus=trip.bus,
                            trip=trip,
                            type="speed",
                            created_at__gte=update.created_at - timedelta(minutes=10),
                    ).exists():
                        AnomalyService.create_anomaly(
                            bus_id=trip.bus_id,
                            anomaly_type="speed",
                            description=f"Speed anomaly detected: {update.speed} km/h",
                            severity="high",
                            location_latitude=update.latitude,
                            location_longitude=update.longitude,
                            trip=trip,
                        )

            # Check for route deviations
            if trip.line:
                # Get furthest update from line's stops
                max_distance = 0
                furthest_update = None

                for update in location_updates:
                    # Find nearest stop
                    from apps.tracking.services import LocationUpdateService

                    nearest_stop, distance = LocationUpdateService.find_nearest_stop(
                        latitude=update.latitude,
                        longitude=update.longitude,
                        line_id=trip.line_id,
                    )

                    if distance and distance > max_distance:
                        max_distance = distance
                        furthest_update = update

                # If furthest update is more than 1 km from any stop, create anomaly
                if max_distance > 1000:  # 1 km in meters
                    from apps.tracking.services import AnomalyService

                    # Check if anomaly already exists
                    if not Anomaly.objects.filter(
                            bus=trip.bus,
                            trip=trip,
                            type="route",
                            created_at__gte=furthest_update.created_at - timedelta(minutes=10),
                    ).exists():
                        AnomalyService.create_anomaly(
                            bus_id=trip.bus_id,
                            anomaly_type="route",
                            description=f"Route deviation detected: {max_distance:.0f} meters from nearest stop",
                            severity="medium",
                            location_latitude=furthest_update.latitude,
                            location_longitude=furthest_update.longitude,
                            trip=trip,
                        )

        logger.info(f"Detected anomalies for {active_trips.count()} active trips")
        return True

    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        return False


@shared_task(base=RetryableTask)
def clean_old_location_data():
    """
    Clean old location data to prevent database bloat.
    """
    try:
        # Get retention period from settings
        from django.conf import settings

        retention_days = getattr(settings, "BUS_LOCATION_HISTORY_RETENTION", 7)
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

        # Delete old waiting passenger reports
        count = WaitingPassengers.objects.filter(
            created_at__lt=passenger_cutoff_date
        ).delete()[0]

        logger.info(f"Cleaned {count} old waiting passenger reports")

        return True

    except Exception as e:
        logger.error(f"Error cleaning old location data: {e}")
        return False


@shared_task(base=RetryableTask)
def update_trip_statistics():
    """
    Update statistics for active trips.
    """
    try:
        # Get active trips
        active_trips = Trip.objects.filter(
            is_completed=False,
            start_time__lte=timezone.now(),
        )

        for trip in active_trips:
            # Get location updates for this trip
            location_updates = LocationUpdate.objects.filter(
                bus=trip.bus,
                created_at__gte=trip.start_time,
            ).order_by("created_at")

            if not location_updates.exists():
                continue

            # Calculate distance
            total_distance = 0
            prev_update = None

            for update in location_updates:
                if prev_update:
                    from apps.core.utils.geo import calculate_distance

                    distance = calculate_distance(
                        float(prev_update.latitude),
                        float(prev_update.longitude),
                        float(update.latitude),
                        float(update.longitude),
                    )

                    if distance:
                        total_distance += distance

                prev_update = update

            # Calculate average speed
            if total_distance > 0:
                duration = (timezone.now() - trip.start_time).total_seconds() / 3600
                average_speed = total_distance / duration if duration > 0 else 0
            else:
                average_speed = 0

            # Get maximum passenger count
            max_passengers = PassengerCount.objects.filter(
                bus=trip.bus,
                created_at__gte=trip.start_time,
            ).aggregate(max=Max("count"))["max"] or 0

            # Count stops visited
            stops_visited = location_updates.values("nearest_stop").distinct().count()

            # Update trip
            trip.distance = total_distance
            trip.average_speed = average_speed
            trip.max_passengers = max_passengers
            trip.total_stops = stops_visited
            trip.save(update_fields=[
                "distance",
                "average_speed",
                "max_passengers",
                "total_stops",
                "updated_at",
            ])

        logger.info(f"Updated statistics for {active_trips.count()} active trips")
        return True

    except Exception as e:
        logger.error(f"Error updating trip statistics: {e}")
        return False