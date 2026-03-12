"""
Service functions for the drivers app.
"""
import logging
from django.db import transaction
from django.db.models import Avg, F
from django.utils import timezone

from apps.accounts.selectors import get_user_by_id
from apps.core.constants import DRIVER_STATUS_APPROVED, DRIVER_STATUS_REJECTED
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object
from apps.core.utils.cache import cache_driver_rating

from .models import Driver, DriverRating, DriverStatusLog
from .selectors import get_driver_by_id

logger = logging.getLogger(__name__)


def _end_active_trips_for_driver(driver):
    """End all active trips for the given driver. Called on reject/suspend/deactivate."""
    from apps.tracking.models import Trip
    from apps.tracking.services import TripService
    active_trips = Trip.objects.filter(driver=driver, is_completed=False)
    for trip in active_trips:
        try:
            TripService.end_trip(trip.id)
            logger.info(f"Auto-ended trip {trip.id} due to driver status change ({driver.status})")
        except Exception as e:
            logger.warning(f"Could not auto-end trip {trip.id} on driver status change: {e}")


class DriverService(BaseService):
    """
    Service for driver-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_driver(cls, user_id, phone_number, id_card_number, id_card_photo,
                      driver_license_number, driver_license_photo, **kwargs):
        """
        Create a new driver.

        Args:
            user_id: ID of the user
            phone_number: Phone number
            id_card_number: ID card number
            id_card_photo: ID card photo
            driver_license_number: Driver license number
            driver_license_photo: Driver license photo
            **kwargs: Additional driver data

        Returns:
            Created driver
        """
        try:
            # Get user
            user = get_user_by_id(user_id)

            # Validate inputs
            if not phone_number:
                raise ValidationError("Phone number is required.")

            if not id_card_number:
                raise ValidationError("ID card number is required.")

            if not id_card_photo:
                raise ValidationError("ID card photo is required.")

            if not driver_license_number:
                raise ValidationError("Driver license number is required.")

            if not driver_license_photo:
                raise ValidationError("Driver license photo is required.")

            # Create driver
            driver_data = {
                "user": user,
                "phone_number": phone_number,
                "id_card_number": id_card_number,
                "id_card_photo": id_card_photo,
                "driver_license_number": driver_license_number,
                "driver_license_photo": driver_license_photo,
                **kwargs
            }

            driver = create_object(Driver, driver_data)

            # Update user type
            user.user_type = "driver"
            user.save(update_fields=["user_type"])

            logger.info(f"Created new driver: {driver.user.email}")
            return driver

        except Exception as e:
            logger.error(f"Error creating driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_driver(cls, driver_id, **data):
        """
        Update a driver.

        Args:
            driver_id: ID of the driver to update
            **data: Driver data to update

        Returns:
            Updated driver
        """
        driver = get_driver_by_id(driver_id)

        # Don't allow updating these fields directly
        data.pop("user", None)
        data.pop("rating", None)
        data.pop("total_ratings", None)

        try:
            update_object(driver, data)
            logger.info(f"Updated driver: {driver.user.email}")
            return driver

        except Exception as e:
            logger.error(f"Error updating driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def approve_driver(cls, driver_id):
        """
        Approve a driver.

        Args:
            driver_id: ID of the driver to approve

        Returns:
            Approved driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            old_status = driver.status
            driver.status = DRIVER_STATUS_APPROVED
            driver.status_changed_at = timezone.now()
            driver.rejection_reason = ""
            driver.save(update_fields=["status", "status_changed_at", "rejection_reason"])

            # Record status change audit log
            DriverStatusLog.objects.create(
                driver=driver,
                from_status=old_status,
                to_status=driver.status,
                reason="",
            )

            logger.info(f"Approved driver: {driver.user.email}")

            # Queue notification
            from apps.notifications.services import NotificationService
            NotificationService.create_notification(
                user_id=driver.user_id,
                notification_type="driver_approved",
                title="Driver Application Approved",
                message="Congratulations! Your driver application has been approved.",
            )

            return driver

        except Exception as e:
            logger.error(f"Error approving driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def reject_driver(cls, driver_id, rejection_reason):
        """
        Reject a driver.

        Args:
            driver_id: ID of the driver to reject
            rejection_reason: Reason for rejection

        Returns:
            Rejected driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            old_status = driver.status
            driver.status = DRIVER_STATUS_REJECTED
            driver.status_changed_at = timezone.now()
            driver.rejection_reason = rejection_reason
            driver.save(update_fields=["status", "status_changed_at", "rejection_reason"])

            # Record status change audit log
            DriverStatusLog.objects.create(
                driver=driver,
                from_status=old_status,
                to_status=driver.status,
                reason=rejection_reason,
            )

            # End any active trips for this driver
            _end_active_trips_for_driver(driver)

            logger.info(f"Rejected driver: {driver.user.email}")

            # Queue notification
            from apps.notifications.services import NotificationService
            NotificationService.create_notification(
                user_id=driver.user_id,
                notification_type="driver_rejected",
                title="Driver Application Rejected",
                message=f"Unfortunately, your driver application has been rejected. Reason: {rejection_reason}",
            )

            return driver

        except Exception as e:
            logger.error(f"Error rejecting driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def suspend_driver(cls, driver_id, reason=""):
        """
        Suspend a driver.

        Args:
            driver_id: ID of the driver to suspend
            reason: Reason for suspension

        Returns:
            Suspended driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            old_status = driver.status
            driver.status = "suspended"
            driver.status_changed_at = timezone.now()
            if reason:
                driver.rejection_reason = reason
            driver.save(update_fields=["status", "status_changed_at", "rejection_reason"])

            # Record status change audit log
            DriverStatusLog.objects.create(
                driver=driver,
                from_status=old_status,
                to_status=driver.status,
                reason=reason,
            )

            # End any active trips for this driver
            _end_active_trips_for_driver(driver)

            logger.info(f"Suspended driver: {driver.user.email}")

            # Queue notification
            from apps.notifications.services import NotificationService
            NotificationService.create_notification(
                user_id=driver.user_id,
                notification_type="system",
                title="Driver Account Suspended",
                message=(
                    f"Your driver account has been suspended. Reason: {reason}"
                    if reason
                    else "Your driver account has been suspended."
                ),
            )

            return driver

        except Exception as e:
            logger.error(f"Error suspending driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_driver(cls, driver_id):
        """
        Deactivate a driver.

        Args:
            driver_id: ID of the driver to deactivate

        Returns:
            Deactivated driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            driver.is_active = False
            driver.save(update_fields=["is_active"])

            # End any active trips for this driver
            _end_active_trips_for_driver(driver)

            logger.info(f"Deactivated driver: {driver.user.email}")
            return driver

        except Exception as e:
            logger.error(f"Error deactivating driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_availability(cls, driver_id, is_available):
        """
        Update a driver's availability.

        Args:
            driver_id: ID of the driver to update
            is_available: Whether the driver is available

        Returns:
            Updated driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            driver.is_available = is_available
            driver.save(update_fields=["is_available"])

            logger.info(f"Updated availability for driver: {driver.user.email}")
            return driver

        except Exception as e:
            logger.error(f"Error updating driver availability: {e}")
            raise ValidationError(str(e))


def _verify_user_rode_with_driver(user, driver):
    """
    R28 — Verify that *user* has a recent interaction with *driver*.

    Interaction counts as either:
    - A BusWaitingList entry for a bus driven by *driver* in the last 48h, OR
    - A WaitingCountReport submitted for a bus driven by *driver* in the last 48h.

    Admins bypass this check entirely.
    """
    if user.is_staff or user.user_type == 'admin':
        return

    from django.utils import timezone
    from datetime import timedelta
    from apps.tracking.models import BusWaitingList, WaitingCountReport, Trip

    cutoff = timezone.now() - timedelta(hours=48)

    # Find trips completed by this driver in the last 48h
    recent_trips = Trip.objects.filter(
        driver=driver,
        start_time__gte=cutoff,
    )
    recent_bus_ids = recent_trips.values_list('bus_id', flat=True)

    # Check BusWaitingList
    waited = BusWaitingList.objects.filter(
        user=user,
        bus_id__in=recent_bus_ids,
        joined_at__gte=cutoff,
    ).exists()

    if waited:
        return

    # Check WaitingCountReport
    reported = WaitingCountReport.objects.filter(
        user=user,
        bus_id__in=recent_bus_ids,
        created_at__gte=cutoff,
    ).exists()

    if reported:
        return

    raise ValidationError(
        "You can only rate a driver after riding with them. "
        "No verified interaction with this driver found in the last 48 hours."
    )


class DriverRatingService(BaseService):
    """
    Service for driver rating-related operations.
    """

    @classmethod
    @transaction.atomic
    def rate_driver(cls, driver_id, user_id, rating, comment=""):
        """
        Rate a driver.

        Args:
            driver_id: ID of the driver to rate
            user_id: ID of the user rating the driver
            rating: Rating (1-5)
            comment: Optional comment

        Returns:
            Created DriverRating
        """
        try:
            # Get driver and user
            driver = get_driver_by_id(driver_id)
            user = get_user_by_id(user_id)

            # Validate rating
            if rating < 1 or rating > 5:
                raise ValidationError("Rating must be between 1 and 5.")

            # R28 — Ride verification: user must have interacted with this driver
            # (waiting list entry OR waiting report) in the last 48 hours.
            _verify_user_rode_with_driver(user, driver)

            # Create rating
            rating_data = {
                "driver": driver,
                "user": user,
                "rating": rating,
                "comment": comment,
            }

            driver_rating = create_object(DriverRating, rating_data)

            # Update driver's average rating
            cls.update_driver_rating(driver_id)

            logger.info(f"Rated driver {driver.user.email}: {rating} stars")
            return driver_rating

        except Exception as e:
            logger.error(f"Error rating driver: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_driver_rating(cls, driver_id):
        """
        Update a driver's average rating.

        Args:
            driver_id: ID of the driver to update rating for

        Returns:
            Updated driver
        """
        driver = get_driver_by_id(driver_id)

        try:
            # Calculate new average rating
            ratings = DriverRating.objects.filter(driver_id=driver_id)
            total_ratings = ratings.count()

            if total_ratings > 0:
                avg_rating = ratings.aggregate(Avg('rating'))['rating__avg']
                driver.rating = avg_rating
                driver.total_ratings = total_ratings
                driver.save(update_fields=["rating", "total_ratings"])

                # Update cache
                cache_driver_rating(driver_id, float(avg_rating))

            logger.info(f"Updated rating for driver: {driver.user.email}")
            return driver

        except Exception as e:
            logger.error(f"Error updating driver rating: {e}")
            raise ValidationError(str(e))
