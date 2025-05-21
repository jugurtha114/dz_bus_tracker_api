"""
Models for the drivers app.
"""
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.constants import (
    DRIVER_STATUS_CHOICES,
    DRIVER_STATUS_PENDING,
    RATING_CHOICES,
)
from apps.core.models import BaseModel
from apps.core.utils.validators import validate_phone_number, validate_id_card_number


class Driver(BaseModel):
    """
    Model for bus drivers.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="driver",
        verbose_name=_("user"),
    )
    phone_number = models.CharField(
        _("phone number"),
        max_length=20,
        validators=[validate_phone_number],
    )
    id_card_number = models.CharField(
        _("ID card number"),
        max_length=20,
        validators=[validate_id_card_number],
        unique=True,
    )
    id_card_photo = models.ImageField(
        _("ID card photo"),
        upload_to="drivers/id_cards/",
    )
    driver_license_number = models.CharField(
        _("driver license number"),
        max_length=20,
        unique=True,
    )
    driver_license_photo = models.ImageField(
        _("driver license photo"),
        upload_to="drivers/licenses/",
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=DRIVER_STATUS_CHOICES,
        default=DRIVER_STATUS_PENDING,
    )
    status_changed_at = models.DateTimeField(
        _("status changed at"),
        auto_now_add=True,
    )
    rejection_reason = models.TextField(
        _("rejection reason"),
        blank=True,
    )
    years_of_experience = models.PositiveSmallIntegerField(
        _("years of experience"),
        default=0,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
    )
    is_available = models.BooleanField(
        _("available"),
        default=True,
    )
    rating = models.DecimalField(
        _("rating"),
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )

    total_ratings = models.PositiveIntegerField(
        _("total ratings"),
        default=0,
    )

    class Meta:
        verbose_name = _("driver")
        verbose_name_plural = _("drivers")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} ({self.id_card_number})"

    @property
    def is_approved(self):
        """
        Check if driver is approved.
        """
        return self.status == "approved"


class DriverRating(BaseModel):
    """
    Model for driver ratings.
    """
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="ratings",
        verbose_name=_("driver"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_ratings",
        verbose_name=_("user"),
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"),
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    # Add a date field to use in the constraint
    rating_date = models.DateField(_("rating date"), auto_now_add=True, db_index=True)

    comment = models.TextField(_("comment"), blank=True)

    class Meta:
        verbose_name = _("driver rating")
        verbose_name_plural = _("driver ratings")
        ordering = ["-created_at"]
        # Use the rating_date field in the constraint
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "user", "rating_date"],
                name="unique_driver_user_date_rating",
            )
        ]

    def __str__(self):
        return f"{self.driver} - {self.rating} stars"