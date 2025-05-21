"""
Service functions for the accounts app.
"""
import logging
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object

from .models import Profile, User

logger = logging.getLogger(__name__)


class UserService(BaseService):
    """
    Service for user-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_user(cls, email, password, user_type="passenger", **kwargs):
        """
        Create a new user.

        Args:
            email: User's email
            password: User's password
            user_type: Type of user to create
            **kwargs: Additional user data

        Returns:
            Created user
        """
        try:
            # Normalize email
            email = email.lower().strip()

            # Create user
            user = User.objects.create_user(
                email=email,
                password=password,
                user_type=user_type,
                **kwargs
            )

            logger.info(f"Created new user: {user.email} ({user.user_type})")
            return user

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_user(cls, user_id, **data):
        """
        Update a user's information.

        Args:
            user_id: ID of user to update
            **data: User data to update

        Returns:
            Updated user
        """
        from .selectors import get_user_by_id

        user = get_user_by_id(user_id)

        # Don't allow updating email or user_type through this method
        data.pop("email", None)
        data.pop("user_type", None)

        try:
            update_object(user, data)
            logger.info(f"Updated user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Error updating user: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_user_password(cls, user_id, password):
        """
        Update a user's password.

        Args:
            user_id: ID of user to update
            password: New password

        Returns:
            Updated user
        """
        from .selectors import get_user_by_id

        user = get_user_by_id(user_id)

        try:
            user.set_password(password)
            user.save(update_fields=["password"])
            logger.info(f"Updated password for user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Error updating password: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_user(cls, user_id):
        """
        Deactivate a user.

        Args:
            user_id: ID of user to deactivate

        Returns:
            Deactivated user
        """
        from .selectors import get_user_by_id

        user = get_user_by_id(user_id)

        try:
            user.is_active = False
            user.save(update_fields=["is_active"])
            logger.info(f"Deactivated user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Error deactivating user: {e}")
            raise ValidationError(str(e))

    @classmethod
    def generate_password_reset_token(cls, user):
        """
        Generate a password reset token for a user.

        Args:
            user: User to generate token for

        Returns:
            Dictionary with UID and token
        """
        return {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }


class ProfileService(BaseService):
    """
    Service for profile-related operations.
    """

    @classmethod
    @transaction.atomic
    def update_profile(cls, user_id, **data):
        """
        Update a user's profile.

        Args:
            user_id: ID of user to update profile for
            **data: Profile data to update

        Returns:
            Updated profile
        """
        from .selectors import get_profile_by_user_id

        profile = get_profile_by_user_id(user_id)

        try:
            update_object(profile, data)
            logger.info(f"Updated profile for user: {profile.user.email}")
            return profile

        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_notification_preferences(cls, user_id, **preferences):
        """
        Update a user's notification preferences.

        Args:
            user_id: ID of user to update preferences for
            **preferences: Notification preferences to update

        Returns:
            Updated profile
        """
        from .selectors import get_profile_by_user_id

        profile = get_profile_by_user_id(user_id)

        # Filter only notification preference fields
        notification_fields = {
            k: v for k, v in preferences.items()
            if k in [
                "push_notifications_enabled",
                "email_notifications_enabled",
                "sms_notifications_enabled",
            ]
        }

        if not notification_fields:
            raise ValidationError("No valid notification preferences provided.")

        try:
            update_object(profile, notification_fields)
            logger.info(f"Updated notification preferences for user: {profile.user.email}")
            return profile

        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}")
            raise ValidationError(str(e))