"""
Selector functions for the drivers app.
"""
from django.db.models import Avg, Count, F, Q
import logging

from apps.core.constants import DRIVER_STATUS_APPROVED
from apps.core.selectors import get_object_or_404
from apps.core.utils.cache import get_cached_driver_rating

from .models import Driver, DriverRating

logger = logging.getLogger(__name__)


def get_driver_by_id(driver_id):
    """
    Get a driver by ID.

    Args:
        driver_id: ID of the driver

    Returns:
        Driver object
    """
    return get_object_or_404(Driver, id=driver_id)


def get_driver_by_user(user_id):
    """
    Get a driver by user ID.

    Args:
        user_id: ID of the user

    Returns:
        Driver object
    """
    return get_object_or_404(Driver, user_id=user_id)


def get_driver_by_id_card(id_card_number):
    """
    Get a driver by ID card number.

    Args:
        id_card_number: ID card number of the driver

    Returns:
        Driver object
    """
    return get_object_or_404(Driver, id_card_number=id_card_number)


def get_driver_ratings(driver_id, limit=None):
    """
    Get ratings for a driver.

    Args:
        driver_id: ID of the driver
        limit: Maximum number of ratings to return

    Returns:
        Queryset of DriverRating objects
    """
    queryset = DriverRating.objects.filter(driver_id=driver_id).order_by('-created_at')

    if limit:
        queryset = queryset[:limit]

    return queryset


def get_driver_average_rating(driver_id):
    """
    Get the average rating for a driver.

    Args:
        driver_id: ID of the driver

    Returns:
        Average rating or None
    """
    # Check cache first
    cached_rating = get_cached_driver_rating(driver_id)
    if cached_rating is not None:
        return cached_rating

    # If not in cache, get from database
    try:
        driver = get_driver_by_id(driver_id)
        if driver.total_ratings > 0:
            return driver.rating
        return None
    except Exception as e:
        logger.error(f"Error getting driver rating: {e}")
        return None


def get_approved_drivers():
    """
    Get all approved drivers.

    Returns:
        Queryset of approved drivers
    """
    return Driver.objects.filter(
        status=DRIVER_STATUS_APPROVED,
        is_active=True,
    )


def get_top_drivers(limit=10):
    """
    Get top-rated drivers.

    Args:
        limit: Maximum number of drivers to return

    Returns:
        Queryset of top-rated drivers
    """
    return Driver.objects.filter(
        status=DRIVER_STATUS_APPROVED,
        is_active=True,
        total_ratings__gt=0,
    ).order_by('-rating')[:limit]


def search_drivers(query):
    """
    Search for drivers by name, phone, or ID.

    Args:
        query: Search query

    Returns:
        Queryset of drivers
    """
    return Driver.objects.filter(
        Q(user__first_name__icontains=query) |
        Q(user__last_name__icontains=query) |
        Q(user__email__icontains=query) |
        Q(phone_number__icontains=query) |
        Q(id_card_number__icontains=query)
    ).filter(
        status=DRIVER_STATUS_APPROVED,
        is_active=True,
    )


def get_pending_drivers():
    """
    Get all pending drivers.

    Returns:
        Queryset of pending drivers
    """
    return Driver.objects.filter(
        status="pending",
        is_active=True,
    )


def get_driver_stats(driver_id):
    """
    Get statistics for a driver.

    Args:
        driver_id: ID of the driver

    Returns:
        Dictionary of driver statistics
    """
    from apps.buses.models import Bus
    from apps.tracking.models import LocationUpdate

    try:
        driver = get_driver_by_id(driver_id)

        # Get bus IDs for this driver
        bus_ids = Bus.objects.filter(
            driver_id=driver_id,
            is_active=True,
        ).values_list('id', flat=True)

        # Get location updates for these buses
        location_updates = LocationUpdate.objects.filter(
            bus_id__in=bus_ids
        )

        # Calculate statistics
        total_distance = location_updates.aggregate(
            total_distance=Sum('distance')
        ).get('total_distance') or 0

        total_trips = location_updates.values('trip_id').distinct().count()

        return {
            "driver_id": str(driver.id),
            "name": driver.user.get_full_name(),
            "rating": float(driver.rating) if driver.rating else 0,
            "total_ratings": driver.total_ratings,
            "years_of_experience": driver.years_of_experience,
            "total_distance": float(total_distance),
            "total_trips": total_trips,
            "buses_count": len(bus_ids),
        }

    except Exception as e:
        logger.error(f"Error getting driver stats: {e}")
        return {}