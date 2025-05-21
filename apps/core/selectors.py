"""
Core selectors for DZ Bus Tracker.
"""
from django.shortcuts import _get_queryset
import logging

from .exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)


def get_object_or_404(klass, *args, **kwargs):
    """
    Get an object or raise ResourceNotFoundError if it doesn't exist.

    Similar to Django's get_object_or_404 but raises a custom exception.
    """
    queryset = _get_queryset(klass)

    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        logger.warning(
            f"Object not found: {queryset.model.__name__} with args {args} and kwargs {kwargs}"
        )
        raise ResourceNotFoundError(
            f"{queryset.model._meta.verbose_name.title()} not found."
        )


def bulk_get_objects_or_404(klass, id_list, id_field='id'):
    """
    Get multiple objects by ID or raise ResourceNotFoundError if any doesn't exist.
    """
    queryset = _get_queryset(klass)

    # Get objects
    objects = list(queryset.filter(**{f"{id_field}__in": id_list}))

    # Check if all objects were found
    found_ids = [getattr(obj, id_field) for obj in objects]
    missing_ids = [id for id in id_list if id not in found_ids]

    if missing_ids:
        logger.warning(
            f"Objects not found: {queryset.model.__name__} with ids {missing_ids}"
        )
        raise ResourceNotFoundError(
            f"Some {queryset.model._meta.verbose_name_plural} not found: {missing_ids}"
        )

    return objects


def get_active_objects(klass, *args, **kwargs):
    """
    Get active objects based on is_active field.
    """
    queryset = _get_queryset(klass)

    # Check if model has is_active field
    if not hasattr(queryset.model, 'is_active'):
        logger.warning(
            f"Model {queryset.model.__name__} does not have is_active field"
        )
        return queryset.filter(*args, **kwargs)

    return queryset.filter(is_active=True, *args, **kwargs)


def get_non_deleted_objects(klass, *args, **kwargs):
    """
    Get non-deleted objects based on is_deleted field.
    """
    queryset = _get_queryset(klass)

    # Check if model has is_deleted field
    if not hasattr(queryset.model, 'is_deleted'):
        logger.warning(
            f"Model {queryset.model.__name__} does not have is_deleted field"
        )
        return queryset.filter(*args, **kwargs)

    return queryset.filter(is_deleted=False, *args, **kwargs)


def count_objects(klass, *args, **kwargs):
    """
    Count objects matching the given criteria.
    """
    queryset = _get_queryset(klass)
    return queryset.filter(*args, **kwargs).count()


def exists_object(klass, *args, **kwargs):
    """
    Check if an object exists.
    """
    queryset = _get_queryset(klass)
    return queryset.filter(*args, **kwargs).exists()