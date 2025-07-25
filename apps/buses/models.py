"""
Models for the buses app.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import BUS_STATUS_CHOICES, BUS_STATUS_ACTIVE
from apps.core.models import BaseModel
from apps.core.utils.validators import validate_plate_number
from apps.drivers.models import Driver


class Bus(BaseModel):
    """
    Model for buses.
    """
    license_plate = models.CharField(
        _("license plate"),
        max_length=15,
        validators=[validate_plate_number],
        unique=True,
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="buses",
        verbose_name=_("driver"),
    )
    model = models.CharField(_("model"), max_length=100)
    manufacturer = models.CharField(_("manufacturer"), max_length=100)
    year = models.PositiveSmallIntegerField(_("year"))
    capacity = models.PositiveSmallIntegerField(
        _("capacity"),
        help_text=_("Maximum number of passengers"),
    )
    average_speed = models.FloatField(
        _("average speed"),
        default=30.0,
        help_text=_("Average speed in km/h for ETA calculations"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=BUS_STATUS_CHOICES,
        default=BUS_STATUS_ACTIVE,
    )
    is_air_conditioned = models.BooleanField(_("air conditioned"), default=False)
    photo = models.ImageField(
        _("photo"),
        upload_to="buses/",
        blank=True,
        null=True,
    )
    features = models.JSONField(
        _("features"),
        default=list,
        blank=True,
        help_text=_("Additional features of the bus"),
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_approved = models.BooleanField(_("approved"), default=False)

    class Meta:
        verbose_name = _("bus")
        verbose_name_plural = _("buses")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.license_plate} ({self.model})"

    @property
    def is_available(self):
        """
        Check if bus is available.
        """
        return self.is_active and self.status == BUS_STATUS_ACTIVE
    
    @property
    def bus_number(self):
        """
        Get bus number (license plate without special characters).
        """
        return self.license_plate.replace('-', '')
    
    @property
    def current_passenger_count(self):
        """
        Get current passenger count from the latest tracking data.
        """
        from apps.tracking.models import PassengerCount
        latest_count = PassengerCount.objects.filter(
            bus=self
        ).order_by('-created_at').first()
        
        return latest_count.count if latest_count else 0


class BusLocation(BaseModel):
    """
    Model for bus locations.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="locations",
        verbose_name=_("bus"),
    )
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
    )
    altitude = models.DecimalField(
        _("altitude"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    speed = models.DecimalField(
        _("speed"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Speed in km/h"),
    )
    heading = models.DecimalField(
        _("heading"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Heading in degrees (0-360)"),
    )
    accuracy = models.DecimalField(
        _("accuracy"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Accuracy in meters"),
    )
    is_tracking_active = models.BooleanField(
        _("tracking active"),
        default=True,
    )
    passenger_count = models.PositiveSmallIntegerField(
        _("passenger count"),
        default=0,
    )

    class Meta:
        verbose_name = _("bus location")
        verbose_name_plural = _("bus locations")
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return f"{self.bus} at {self.created_at}"