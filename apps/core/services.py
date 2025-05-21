"""
Core services for DZ Bus Tracker.
"""
import logging
from functools import wraps

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .exceptions import ValidationError

logger = logging.getLogger(__name__)


class BaseService:
    """
    Base service class with common utility methods.
    """

    @staticmethod
    def atomic_transaction(func):
        """
        Decorator to wrap service methods in atomic transactions.
        """

        @wraps(func)
        def wrapper(*args, **kwargs):
            with transaction.atomic():
                return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def validate_fields(data, required_fields=None, optional_fields=None):
        """
        Validate that all required fields are present and only allowed fields are provided.

        Args:
            data: Dictionary of data to validate
            required_fields: List of required field names
            optional_fields: List of optional field names

        Raises:
            ValidationError: If validation fails
        """
        required_fields = required_fields or []
        optional_fields = optional_fields or []

        # Check for missing required fields
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValidationError(
                _(f"Missing required fields: {', '.join(missing_fields)}")
            )

        # Check for unexpected fields
        allowed_fields = required_fields + optional_fields
        unexpected_fields = [field for field in data if field not in allowed_fields]
        if unexpected_fields:
            raise ValidationError(
                _(f"Unexpected fields: {', '.join(unexpected_fields)}")
            )

        return True


def create_object(model, data, commit=True):
    """
    Create an object with the given data.

    Args:
        model: Model class to create an instance of
        data: Dictionary of data to create the object with
        commit: Whether to save the object to the database

    Returns:
        The created object
    """
    try:
        instance = model(**data)
        if commit:
            instance.full_clean()
            instance.save()
        return instance
    except Exception as e:
        logger.error(f"Error creating {model.__name__} object: {e}")
        raise ValidationError(str(e))


@transaction.atomic
def update_object(instance, data, commit=True):
    """
    Update an object with the given data.

    Args:
        instance: Object to update
        data: Dictionary of data to update the object with
        commit: Whether to save the object to the database

    Returns:
        The updated object
    """
    try:
        for key, value in data.items():
            setattr(instance, key, value)

        if commit:
            instance.full_clean()
            instance.save()

        return instance
    except Exception as e:
        logger.error(f"Error updating {instance.__class__.__name__} object: {e}")
        raise ValidationError(str(e))


@transaction.atomic
def delete_object(instance, soft_delete=True):
    """
    Delete an object.

    Args:
        instance: Object to delete
        soft_delete: Whether to soft delete the object if supported

    Returns:
        True if the object was deleted
    """
    try:
        if soft_delete and hasattr(instance, "is_deleted"):
            instance.is_deleted = True
            instance.save(update_fields=["is_deleted", "deleted_at"])
        else:
            instance.delete()
        return True
    except Exception as e:
        logger.error(f"Error deleting {instance.__class__.__name__} object: {e}")
        raise ValidationError(str(e))
