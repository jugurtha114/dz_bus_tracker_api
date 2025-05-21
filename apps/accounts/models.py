"""
User account models for DZ Bus Tracker.
"""
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import LANGUAGE_CHOICES, USER_TYPE_CHOICES, USER_TYPE_PASSENGER
from apps.core.models import BaseModel
from apps.core.utils.validators import validate_phone_number

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for DZ Bus Tracker.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("ID"),
    )
    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={
            "unique": _("A user with that email already exists."),
        },
    )
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    phone_number = models.CharField(
        _("phone number"),
        max_length=20,
        blank=True,
        validators=[validate_phone_number],
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    user_type = models.CharField(
        _("user type"),
        max_length=10,
        choices=USER_TYPE_CHOICES,
        default=USER_TYPE_PASSENGER,
    )

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self):
        if self.get_full_name():
            return self.get_full_name()
        return self.email

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()

    def get_short_name(self):
        """
        Return the short name for the user.
        """
        return self.first_name

    @property
    def is_driver(self):
        """
        Check if user is a driver.
        """
        return self.user_type == "driver"

    @property
    def is_passenger(self):
        """
        Check if user is a passenger.
        """
        return self.user_type == "passenger"

    @property
    def is_admin(self):
        """
        Check if user is an admin.
        """
        return self.user_type == "admin" or self.is_staff


class Profile(BaseModel):
    """
    Extended profile information for users.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("user"),
    )
    avatar = models.ImageField(
        _("avatar"),
        upload_to="avatars/",
        blank=True,
        null=True,
    )
    bio = models.TextField(_("bio"), blank=True)
    language = models.CharField(
        _("language"),
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="fr",
    )
    push_notifications_enabled = models.BooleanField(
        _("push notifications enabled"),
        default=True,
    )
    email_notifications_enabled = models.BooleanField(
        _("email notifications enabled"),
        default=True,
    )
    sms_notifications_enabled = models.BooleanField(
        _("SMS notifications enabled"),
        default=False,
    )

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self):
        return f"{self.user}'s profile"