"""
Celery tasks for driver-related operations.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.core.constants import DRIVER_STATUS_PENDING
from apps.drivers.models import Driver, DriverRating
from tasks.base import RetryableTask

logger = logging.getLogger(__name__)


@shared_task(base=RetryableTask)
def process_driver_application(driver_id):
    """
    Process a driver application (auto-approval after checks).
    """
    try:
        # Get driver
        from apps.drivers.selectors import get_driver_by_id
        driver = get_driver_by_id(driver_id)

        # Skip if not pending
        if driver.status != DRIVER_STATUS_PENDING:
            logger.info(f"Driver {driver.id} is not pending approval")
            return False

        # Check if auto-approval is enabled
        from django.conf import settings
        if not getattr(settings, "DRIVER_APPROVAL_REQUIRED", True):
            # Auto-approve driver
            from apps.drivers.services import DriverService
            DriverService.approve_driver(driver.id)

            logger.info(f"Auto-approved driver {driver.user.email}")
            return True

        # Otherwise, notify admins
        admin_emails = []

        # Get admin users
        from django.contrib.auth import get_user_model
        User = get_user_model()

        admins = User.objects.filter(is_staff=True, is_active=True)

        for admin in admins:
            # Create notification
            from apps.notifications.services import NotificationService
            NotificationService.create_notification(
                user_id=admin.id,
                notification_type="admin",
                title="New Driver Application",
                message=f"New driver application from {driver.user.get_full_name() or driver.user.email}.",
                channel="in_app",
                data={"driver_id": str(driver.id)},
            )

            admin_emails.append(admin.email)

        logger.info(
            f"Notified {len(admin_emails)} admins about new driver application: {driver.user.email}"
        )
        return True

    except Exception as e:
        logger.error(f"Error processing driver application: {e}")
        return False


@shared_task(base=RetryableTask)
def update_driver_stats():
    """
    Update statistics for all drivers.
    """
    try:
        # Get active drivers
        from apps.drivers.selectors import get_approved_drivers
        drivers = get_approved_drivers()

        for driver in drivers:
            # Update driver rating
            from apps.drivers.services import DriverRatingService
            DriverRatingService.update_driver_rating(driver.id)

            # Calculate trip statistics
            from apps.tracking.models import Trip
            trips = Trip.objects.filter(driver=driver, is_completed=True)

            total_trips = trips.count()
            total_distance = trips.aggregate(
                sum=Sum("distance")
            )["sum"] or 0

            # Update driver object with statistics
            driver.total_trips = total_trips
            driver.total_distance = total_distance
            driver.save(update_fields=["total_trips", "total_distance", "updated_at"])

            logger.info(
                f"Updated stats for driver {driver.user.email}: "
                f"{total_trips} trips, {total_distance:.2f} km"
            )

        logger.info(f"Updated stats for {drivers.count()} drivers")
        return True

    except Exception as e:
        logger.error(f"Error updating driver stats: {e}")
        return False


@shared_task(base=RetryableTask)
def clean_old_ratings():
    """
    Clean old driver ratings to reduce database size.
    """
    try:
        # Define retention period (e.g., keep ratings for 1 year)
        cutoff_date = timezone.now() - timedelta(days=365)

        # Get count of old ratings
        old_ratings_count = DriverRating.objects.filter(
            created_at__lt=cutoff_date
        ).count()

        # For each driver, ensure their average rating is updated before deleting old ratings
        from apps.drivers.selectors import get_approved_drivers
        drivers = get_approved_drivers()

        for driver in drivers:
            # Update driver rating
            from apps.drivers.services import DriverRatingService
            DriverRatingService.update_driver_rating(driver.id)

        # Delete old ratings
        deleted_count = DriverRating.objects.filter(
            created_at__lt=cutoff_date
        ).delete()[0]

        logger.info(f"Cleaned {deleted_count} old driver ratings")
        return True

    except Exception as e:
        logger.error(f"Error cleaning old ratings: {e}")
        return False