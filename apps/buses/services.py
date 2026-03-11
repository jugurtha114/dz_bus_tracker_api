"""
Service functions for the buses app.
"""
import logging
from django.db import transaction
from django.utils import timezone

from apps.core.constants import BUS_STATUS_ACTIVE, BUS_STATUS_INACTIVE
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object
from apps.drivers.selectors import get_driver_by_id

from .models import Bus
from .selectors import get_bus_by_id

logger = logging.getLogger(__name__)


class BusService(BaseService):
    """
    Service for bus-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_bus(cls, driver_id, license_plate, model, manufacturer, year, capacity, **kwargs):
        """
        Create a new bus.

        Args:
            driver_id: ID of the driver
            license_plate: License plate of the bus
            model: Model of the bus
            manufacturer: Manufacturer of the bus
            year: Year of the bus
            capacity: Capacity of the bus
            **kwargs: Additional bus data

        Returns:
            Created bus
        """
        try:
            # Get driver
            driver = get_driver_by_id(driver_id)

            # Normalize license plate
            license_plate = license_plate.upper().strip()

            # Validate inputs
            if not license_plate:
                raise ValidationError("License plate is required.")

            if not model:
                raise ValidationError("Model is required.")

            if not manufacturer:
                raise ValidationError("Manufacturer is required.")

            if not year or year < 1900 or year > timezone.now().year:
                raise ValidationError("Invalid year.")

            if not capacity or capacity <= 0:
                raise ValidationError("Capacity must be greater than zero.")

            # Create bus
            bus_data = {
                "driver": driver,
                "license_plate": license_plate,
                "model": model,
                "manufacturer": manufacturer,
                "year": year,
                "capacity": capacity,
                **kwargs
            }

            bus = create_object(Bus, bus_data)

            logger.info(f"Created new bus: {bus.license_plate} for driver {driver.user.email}")
            return bus

        except Exception as e:
            logger.error(f"Error creating bus: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_bus(cls, bus_id, **data):
        """
        Update a bus.

        Args:
            bus_id: ID of the bus to update
            **data: Bus data to update

        Returns:
            Updated bus
        """
        bus = get_bus_by_id(bus_id)

        try:
            # Don't allow updating license_plate
            data.pop("license_plate", None)

            update_object(bus, data)
            logger.info(f"Updated bus: {bus.license_plate}")
            return bus

        except Exception as e:
            logger.error(f"Error updating bus: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def activate_bus(cls, bus_id):
        """
        Activate a bus.

        Args:
            bus_id: ID of the bus to activate

        Returns:
            Activated bus
        """
        bus = get_bus_by_id(bus_id)

        try:
            bus.is_active = True
            bus.status = BUS_STATUS_ACTIVE
            bus.save(update_fields=["is_active", "status", "updated_at"])

            logger.info(f"Activated bus: {bus.license_plate}")
            return bus

        except Exception as e:
            logger.error(f"Error activating bus: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_bus(cls, bus_id):
        """
        Deactivate a bus.

        Args:
            bus_id: ID of the bus to deactivate

        Returns:
            Deactivated bus
        """
        bus = get_bus_by_id(bus_id)

        try:
            bus.is_active = False
            bus.status = BUS_STATUS_INACTIVE
            bus.save(update_fields=["is_active", "status", "updated_at"])

            logger.info(f"Deactivated bus: {bus.license_plate}")
            return bus

        except Exception as e:
            logger.error(f"Error deactivating bus: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def approve_bus(cls, bus_id):
        """
        Approve a bus.

        Args:
            bus_id: ID of the bus to approve

        Returns:
            Approved bus
        """
        bus = get_bus_by_id(bus_id)

        try:
            bus.is_approved = True
            bus.save(update_fields=["is_approved", "updated_at"])

            logger.info(f"Approved bus: {bus.license_plate}")
            return bus

        except Exception as e:
            logger.error(f"Error approving bus: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def unapprove_bus(cls, bus_id):
        """
        Unapprove a bus.

        Args:
            bus_id: ID of the bus to unapprove

        Returns:
            Unapproved bus
        """
        bus = get_bus_by_id(bus_id)

        try:
            bus.is_approved = False
            bus.save(update_fields=["is_approved", "updated_at"])

            logger.info(f"Unapproved bus: {bus.license_plate}")
            return bus

        except Exception as e:
            logger.error(f"Error unapproving bus: {e}")
            raise ValidationError(str(e))
