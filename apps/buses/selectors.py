"""
Selector functions for the buses app.
"""
from django.db.models import F, Q
import logging

from apps.core.constants import BUS_STATUS_ACTIVE
from apps.core.selectors import get_object_or_404
from apps.core.utils.cache import get_cached_bus_location, get_cached_bus_passengers

from .models import Bus, BusLocation

logger = logging.getLogger(__name__)


def get_bus_by_id(bus_id):
    """
    Get a bus by ID.

    Args:
        bus_id: ID of the bus

    Returns:
        Bus object
    """
    return get_object_or_404(Bus, id=bus_id)


def get_bus_by_license_plate(license_plate):
    """
    Get a bus by license plate.

    Args:
        license_plate: License plate of the bus

    Returns:
        Bus object
    """
    return get_object_or_404(Bus, license_plate=license_plate)


def get_buses_by_driver(driver_id):
    """
    Get buses by driver ID.

    Args:
        driver_id: ID of the driver

    Returns:
        Queryset of buses
    """
    return Bus.objects.filter(driver_id=driver_id, is_active=True)


def get_active_buses(driver_id=None):
    """
    Get active buses, optionally filtered by driver.

    Args:
        driver_id: Optional driver ID to filter by

    Returns:
        Queryset of active buses
    """
    queryset = Bus.objects.filter(
        is_active=True,
        status=BUS_STATUS_ACTIVE,
        is_approved=True,
    )

    if driver_id:
        queryset = queryset.filter(driver_id=driver_id)

    return queryset


def get_bus_location(bus_id):
    """
    Get the latest location of a bus.

    Args:
        bus_id: ID of the bus

    Returns:
        Latest BusLocation object or None
    """
    # Check cache first
    cached_location = get_cached_bus_location(bus_id)
    if cached_location:
        return cached_location

    # If not in cache, get from database
    try:
        return BusLocation.objects.filter(bus_id=bus_id).latest()
    except BusLocation.DoesNotExist:
        return None


def get_bus_location_history(bus_id, limit=10):
    """
    Get location history of a bus.

    Args:
        bus_id: ID of the bus
        limit: Maximum number of locations to return

    Returns:
        Queryset of BusLocation objects
    """
    return BusLocation.objects.filter(bus_id=bus_id).order_by('-created_at')[:limit]


def get_bus_passenger_count(bus_id):
    """
    Get the current passenger count of a bus.

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
        location = BusLocation.objects.filter(bus_id=bus_id).latest()
        return location.passenger_count
    except BusLocation.DoesNotExist:
        return 0


def search_buses(query, line_id=None):
    """
    Search for buses by license plate, model, or manufacturer.

    Args:
        query: Search query
        line_id: Optional line ID to filter by

    Returns:
        Queryset of buses
    """
    queryset = Bus.objects.filter(
        Q(license_plate__icontains=query) |
        Q(model__icontains=query) |
        Q(manufacturer__icontains=query)
    ).filter(
        is_active=True,
        status=BUS_STATUS_ACTIVE,
        is_approved=True,
    )

    if line_id:
        queryset = queryset.filter(lines__id=line_id)

    return queryset


def get_buses_by_line(line_id):
    """
    Get buses operating on a line.

    Args:
        line_id: ID of the line

    Returns:
        Queryset of buses
    """
    from apps.tracking.models import BusLine

    bus_ids = BusLine.objects.filter(
        line_id=line_id,
        is_active=True,
    ).values_list('bus_id', flat=True)

    return Bus.objects.filter(
        id__in=bus_ids,
        is_active=True,
        status=BUS_STATUS_ACTIVE,
        is_approved=True,
    )


def get_nearby_buses(latitude, longitude, radius_km=2.0):
    """
    Get buses near a location.

    Args:
        latitude: Latitude
        longitude: Longitude
        radius_km: Radius in kilometers

    Returns:
        Queryset of bus IDs
    """
    # This is a simplified implementation that doesn't do actual geospatial queries
    # In production, you would use PostGIS or another geospatial database

    # For now, just get all active buses
    return get_active_buses()