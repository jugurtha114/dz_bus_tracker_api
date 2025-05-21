"""
Selector functions for the tracking app.
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.utils import timezone

from apps.core.selectors import get_object_or_404
from apps.core.utils.cache import (
    get_cached_bus_location,
    get_cached_bus_passengers,
    get_cached_line_buses,
    get_cached_stop_waiting,
)
from apps.core.utils.geo import calculate_eta

from .models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)

logger = logging.getLogger(__name__)


def get_bus_line(bus_id, line_id):
    """
    Get a bus-line assignment.

    Args:
        bus_id: ID of the bus
        line_id: ID of the line

    Returns:
        BusLine object
    """
    return get_object_or_404(BusLine, bus_id=bus_id, line_id=line_id)


def get_active_bus_lines(line_id=None):
    """
    Get active bus-line assignments.

    Args:
        line_id: Optional line ID to filter by

    Returns:
        Queryset of BusLine objects
    """
    queryset = BusLine.objects.filter(is_active=True)

    if line_id:
        queryset = queryset.filter(line_id=line_id)

    return queryset


def get_tracking_buses(line_id=None):
    """
    Get buses that are currently tracking.

    Args:
        line_id: Optional line ID to filter by

    Returns:
        Queryset of BusLine objects
    """
    queryset = BusLine.objects.filter(
        is_active=True,
        tracking_status="active",
    )

    if line_id:
        queryset = queryset.filter(line_id=line_id)

    return queryset


def get_latest_location_update(bus_id):
    """
    Get the latest location update for a bus.

    Args:
        bus_id: ID of the bus

    Returns:
        LocationUpdate object or None
    """
    # Check cache first
    cached_location = get_cached_bus_location(bus_id)
    if cached_location:
        return cached_location

    # If not in cache, get from database
    try:
        return LocationUpdate.objects.filter(bus_id=bus_id).latest("created_at")
    except LocationUpdate.DoesNotExist:
        return None


def get_location_history(bus_id, limit=10):
    """
    Get location history for a bus.

    Args:
        bus_id: ID of the bus
        limit: Maximum number of updates to return

    Returns:
        Queryset of LocationUpdate objects
    """
    return LocationUpdate.objects.filter(bus_id=bus_id).order_by('-created_at')[:limit]


def get_buses_on_line(line_id):
    """
    Get buses currently on a line.

    Args:
        line_id: ID of the line

    Returns:
        List of buses with their latest locations
    """
    # Check cache first
    cached_buses = get_cached_line_buses(line_id)
    if cached_buses:
        return cached_buses

    # If not in cache, get from database
    buses = []

    # Get active bus-line assignments
    bus_lines = get_active_bus_lines(line_id)

    for bus_line in bus_lines:
        # Get latest location
        location = get_latest_location_update(bus_line.bus_id)
        if location:
            # Get passenger count
            passenger_count = get_current_passenger_count(bus_line.bus_id)

            buses.append({
                "bus_id": str(bus_line.bus_id),
                "license_plate": bus_line.bus.license_plate,
                "tracking_status": bus_line.tracking_status,
                "latitude": location.get("latitude") if isinstance(location, dict) else float(location.latitude),
                "longitude": location.get("longitude") if isinstance(location, dict) else float(location.longitude),
                "speed": location.get("speed") if isinstance(location, dict) else float(location.speed or 0),
                "heading": location.get("heading") if isinstance(location, dict) else float(location.heading or 0),
                "passenger_count": passenger_count,
                "capacity": bus_line.bus.capacity,
                "last_updated": location.get("timestamp") if isinstance(location,
                                                                        dict) else location.created_at.isoformat(),
            })

    return buses


def get_current_passenger_count(bus_id):
    """
    Get the current passenger count for a bus.

    Args:
        bus_id: ID of the bus

    Returns:
        Current passenger count
    """
    # Check cache first
    cached_count = get_cached_bus_passengers(bus_id)
    if cached_count is not None:
        return cached_count

    # If not in cache, get from database
    try:
        latest = PassengerCount.objects.filter(bus_id=bus_id).latest("created_at")
        return latest.count
    except PassengerCount.DoesNotExist:
        return 0


def get_waiting_passengers(stop_id, line_id=None):
    """
    Get the number of waiting passengers at a stop.

    Args:
        stop_id: ID of the stop
        line_id: Optional line ID to filter by

    Returns:
        Number of waiting passengers
    """
    # Check cache first
    cached_count = get_cached_stop_waiting(stop_id)
    if cached_count is not None:
        return cached_count

    # If not in cache, get from database
    try:
        queryset = WaitingPassengers.objects.filter(stop_id=stop_id)

        if line_id:
            queryset = queryset.filter(line_id=line_id)

        latest = queryset.latest("created_at")
        return latest.count
    except WaitingPassengers.DoesNotExist:
        return 0


def estimate_arrival_time(bus_id, stop_id):
    """
    Estimate the arrival time of a bus at a stop.

    Args:
        bus_id: ID of the bus
        stop_id: ID of the stop

    Returns:
        Estimated arrival time or None
    """
    try:
        # Get latest location
        location = get_latest_location_update(bus_id)
        if not location:
            return None

        # Get stop
        from apps.lines.models import Stop
        stop = Stop.objects.get(id=stop_id)

        # Get current speed
        speed = location.speed if hasattr(location, "speed") else None

        # Calculate ETA
        return calculate_eta(
            float(location.latitude),
            float(location.longitude),
            float(stop.latitude),
            float(stop.longitude),
            float(speed) if speed else None
        )

    except Exception as e:
        logger.error(f"Error estimating arrival time: {e}")
        return None


def get_active_trip(bus_id):
    """
    Get the active trip for a bus.

    Args:
        bus_id: ID of the bus

    Returns:
        Trip object or None
    """
    try:
        return Trip.objects.filter(
            bus_id=bus_id,
            is_completed=False,
            start_time__lte=timezone.now()
        ).latest("start_time")
    except Trip.DoesNotExist:
        return None


def get_trip_by_id(trip_id):
    """
    Get a trip by ID.

    Args:
        trip_id: ID of the trip

    Returns:
        Trip object
    """
    return get_object_or_404(Trip, id=trip_id)


def get_trip_statistics(trip_id):
    """
    Get statistics for a trip.

    Args:
        trip_id: ID of the trip

    Returns:
        Dictionary of trip statistics
    """
    try:
        trip = get_trip_by_id(trip_id)

        # Get location updates for this trip
        location_updates = LocationUpdate.objects.filter(trip_id=trip_id)

        # Get passenger counts for this trip
        passenger_counts = PassengerCount.objects.filter(trip_id=trip_id)

        # Calculate statistics
        stats = {
            "trip_id": str(trip.id),
            "bus": trip.bus.license_plate,
            "driver": trip.driver.user.get_full_name(),
            "line": trip.line.code,
            "start_time": trip.start_time.isoformat(),
            "end_time": trip.end_time.isoformat() if trip.end_time else None,
            "is_completed": trip.is_completed,
            "distance": float(trip.distance) if trip.distance else None,
            "average_speed": float(trip.average_speed) if trip.average_speed else None,
            "max_passengers": trip.max_passengers,
            "total_stops": trip.total_stops,
            "duration_minutes": (
                (trip.end_time - trip.start_time).total_seconds() / 60
                if trip.end_time else None
            ),
            "location_updates_count": location_updates.count(),
            "passenger_counts_count": passenger_counts.count(),
            "average_occupancy": passenger_counts.aggregate(
                avg=Avg("occupancy_rate")
            )["avg"],
        }

        return stats

    except Exception as e:
        logger.error(f"Error getting trip statistics: {e}")
        return {}


def get_anomalies(bus_id=None, resolved=None, severity=None):
    """
    Get anomalies.

    Args:
        bus_id: Optional bus ID to filter by
        resolved: Optional resolved status to filter by
        severity: Optional severity to filter by

    Returns:
        Queryset of Anomaly objects
    """
    queryset = Anomaly.objects.all()

    if bus_id:
        queryset = queryset.filter(bus_id=bus_id)

    if resolved is not None:
        queryset = queryset.filter(resolved=resolved)

    if severity:
        queryset = queryset.filter(severity=severity)

    return queryset.order_by("-created_at")


def get_line_performance(line_id, date_from=None, date_to=None):
    """
    Get performance statistics for a line.

    Args:
        line_id: ID of the line
        date_from: Optional start date
        date_to: Optional end date

    Returns:
        Dictionary of performance statistics
    """
    try:
        # Default date range is last 7 days
        if not date_to:
            date_to = timezone.now()

        if not date_from:
            date_from = date_to - timedelta(days=7)

        # Get trips for this line in the date range
        trips = Trip.objects.filter(
            line_id=line_id,
            start_time__gte=date_from,
            start_time__lte=date_to,
        )

        # Get location updates for these trips
        trip_ids = trips.values_list("id", flat=True)

        location_updates = LocationUpdate.objects.filter(
            trip_id__in=trip_ids
        )

        passenger_counts = PassengerCount.objects.filter(
            trip_id__in=trip_ids
        )

        # Calculate statistics
        stats = {
            "line_id": str(line_id),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "trips_count": trips.count(),
            "completed_trips_count": trips.filter(is_completed=True).count(),
            "total_distance": trips.aggregate(
                sum=Sum("distance")
            )["sum"] or 0,
            "average_speed": trips.aggregate(
                avg=Avg("average_speed")
            )["avg"] or 0,
            "max_passengers": trips.aggregate(
                max=Max("max_passengers")
            )["max"] or 0,
            "average_occupancy": passenger_counts.aggregate(
                avg=Avg("occupancy_rate")
            )["avg"] or 0,
            "anomalies_count": Anomaly.objects.filter(
                trip_id__in=trip_ids
            ).count(),
        }

        return stats

    except Exception as e:
        logger.error(f"Error getting line performance: {e}")
        return {}