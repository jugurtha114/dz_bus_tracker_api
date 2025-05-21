"""
Celery tasks for bus-related operations.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.buses.models import Bus, BusLocation
from apps.core.constants import BUS_STATUS_INACTIVE
from tasks.base import RetryableTask

logger = logging.getLogger(__name__)


@shared_task(base=RetryableTask)
def clean_inactive_buses():
    """
    Clean up data for inactive buses.
    """
    try:
        # Get inactive buses
        inactive_buses = Bus.objects.filter(
            Q(is_active=False) | Q(status=BUS_STATUS_INACTIVE)
        )

        # Delete old location data for inactive buses
        cutoff_date = timezone.now() - timedelta(days=30)

        for bus in inactive_buses:
            count = BusLocation.objects.filter(
                bus=bus,
                created_at__lt=cutoff_date
            ).delete()[0]

            if count > 0:
                logger.info(f"Deleted {count} old location records for inactive bus {bus.license_plate}")

        logger.info(f"Processed {inactive_buses.count()} inactive buses")
        return True

    except Exception as e:
        logger.error(f"Error cleaning inactive buses: {e}")
        return False


@shared_task(base=RetryableTask)
def check_bus_schedule():
    """
    Check bus schedule compliance.
    """
    try:
        # Get all active buses
        from apps.buses.selectors import get_active_buses
        buses = get_active_buses()

        # Get current time and date
        now = timezone.now()
        current_time = now.time()
        day_of_week = now.weekday()  # 0 = Monday, 6 = Sunday

        # Check each bus
        for bus in buses:
            # Get bus-line assignments
            from apps.tracking.models import BusLine
            bus_lines = BusLine.objects.filter(
                bus=bus,
                is_active=True,
            )

            for bus_line in bus_lines:
                # Get scheduled departure times
                from apps.lines.models import Schedule
                schedules = Schedule.objects.filter(
                    line=bus_line.line,
                    day_of_week=day_of_week,
                    start_time__lte=current_time,
                    end_time__gte=current_time,
                    is_active=True,
                )

                # If bus should be active but isn't tracking
                if schedules.exists() and bus_line.tracking_status != "active":
                    # Create notification for the driver
                    from apps.notifications.services import NotificationService
                    NotificationService.create_notification(
                        user_id=bus.driver.user.id,
                        notification_type="schedule",
                        title="Schedule Reminder",
                        message=f"You should be tracking on line {bus_line.line.code} now.",
                        channel="push",
                    )

                    logger.info(
                        f"Sent schedule reminder to driver {bus.driver.user.email} "
                        f"for bus {bus.license_plate} on line {bus_line.line.code}"
                    )

        logger.info("Checked bus schedule compliance")
        return True

    except Exception as e:
        logger.error(f"Error checking bus schedule: {e}")
        return False


@shared_task(base=RetryableTask)
def update_inactive_bus_status():
    """
    Update status of buses that haven't sent updates for a while.
    """
    try:
        # Define inactivity threshold
        threshold = timezone.now() - timedelta(hours=8)

        # Get buses with active tracking but no recent updates
        active_buses = Bus.objects.filter(is_active=True)

        for bus in active_buses:
            # Check for recent location updates
            has_recent_updates = BusLocation.objects.filter(
                bus=bus,
                created_at__gte=threshold,
            ).exists()

            if not has_recent_updates:
                # Update bus status to inactive
                bus.status = BUS_STATUS_INACTIVE
                bus.save(update_fields=["status", "updated_at"])

                # Update bus-line tracking status
                from apps.tracking.models import BusLine
                BusLine.objects.filter(
                    bus=bus,
                    tracking_status="active",
                ).update(
                    tracking_status="idle",
                    end_time=timezone.now(),
                )

                # End any active trips
                from apps.tracking.selectors import get_active_trip
                trip = get_active_trip(bus.id)

                if trip:
                    from apps.tracking.services import TripService
                    TripService.end_trip(trip.id)

                logger.info(
                    f"Updated status of inactive bus {bus.license_plate} "
                    f"(no updates since {threshold})"
                )

        logger.info("Updated inactive bus statuses")
        return True

    except Exception as e:
        logger.error(f"Error updating inactive bus status: {e}")
        return False