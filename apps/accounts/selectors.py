"""
Selector functions for the accounts app.
"""
import logging

from django.db.models import Q

from apps.core.exceptions import ResourceNotFoundError
from apps.core.selectors import get_object_or_404
from .models import Profile, User

logger = logging.getLogger(__name__)


def get_user_by_id(user_id):
    """
    Get a user by ID.

    Args:
        user_id: ID of the user

    Returns:
        User object
    """
    return get_object_or_404(User, id=user_id)


def get_user_by_email(email):
    """
    Get a user by email.

    Args:
        email: Email of the user

    Returns:
        User object
    """
    return get_object_or_404(User, email=email)


def get_profile_by_user_id(user_id):
    """
    Get a user's profile by user ID.

    Args:
        user_id: ID of the user

    Returns:
        Profile object
    """
    try:
        return Profile.objects.get(user_id=user_id)
    except Profile.DoesNotExist:
        user = get_user_by_id(user_id)
        # Create profile if it doesn't exist
        return Profile.objects.create(user=user)


def get_active_users():
    """
    Get all active users.

    Returns:
        Queryset of active users
    """
    return User.objects.filter(is_active=True)


def get_users_by_type(user_type):
    """
    Get users by type.

    Args:
        user_type: Type of users to get (admin, driver, passenger)

    Returns:
        Queryset of users of the specified type
    """
    return User.objects.filter(user_type=user_type, is_active=True)


def search_users(query):
    """
    Search for users by email, name, or phone number.

    Args:
        query: Search query

    Returns:
        Queryset of matching users
    """
    return User.objects.filter(
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(phone_number__icontains=query)
    ).filter(is_active=True)


def get_user_with_profile(user_id):
    """
    Get a user with their profile using a single query.

    Args:
        user_id: ID of the user

    Returns:
        User object with profile loaded
    """
    try:
        return User.objects.select_related("profile").get(id=user_id)
    except User.DoesNotExist:
        raise ResourceNotFoundError("User not found.")


def count_users_by_type():
    """
    Count users by type.

    Returns:
        Dictionary of user counts by type
    """
    from django.db.models import Count

    return dict(User.objects.values("user_type").annotate(count=Count("id")).values_list("user_type", "count"))