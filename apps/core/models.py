"""
Core models for DZ Bus Tracker.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from .mixins.models import TimeStampedMixin, UUIDMixin


class BaseModel(UUIDMixin, TimeStampedMixin):
    """
    Base model for all models in the application.
    """
    class Meta:
        abstract = True
        ordering = ["-created_at"]


class Address(BaseModel):
    """
    Address model for locations throughout the application.
    """
    street = models.CharField(_("street"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100)
    state = models.CharField(_("state/wilaya"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    country = models.CharField(_("country"), max_length=100, default="Algeria")
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    def __str__(self):
        if self.street:
            return f"{self.street}, {self.city}, {self.state}"
        return f"{self.city}, {self.state}"

    class Meta(BaseModel.Meta):
        verbose_name = _("address")
        verbose_name_plural = _("addresses")