"""
Models for the tracking app.
"""
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.buses.models import Bus
from apps.core.constants import (
    BUS_TRACKING_STATUS_CHOICES,
    BUS_TRACKING_STATUS_IDLE,
)
from apps.core.models import BaseModel
from apps.drivers.models import Driver
from apps.lines.models import Line, Stop


class BusLine(BaseModel):
    """
    Model for bus-line assignments.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("bus"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="buses",
        verbose_name=_("line"),
    )
    is_active = models.BooleanField(_("active"), default=True)
    tracking_status = models.CharField(
        _("tracking status"),
        max_length=20,
        choices=BUS_TRACKING_STATUS_CHOICES,
        default=BUS_TRACKING_STATUS_IDLE,
    )
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    start_time = models.DateTimeField(
        _("start time"),
        null=True,
        blank=True,
    )
    end_time = models.DateTimeField(
        _("end time"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("bus line")
        verbose_name_plural = _("bus lines")
        ordering = ["-created_at"]
        unique_together = [["bus", "line"]]

    def __str__(self):
        return f"{self.bus} on {self.line}"


class LocationUpdate(BaseModel):
    """
    Model for bus location updates.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="location_updates",
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
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    nearest_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_updates",
        verbose_name=_("nearest stop"),
    )
    distance_to_stop = models.DecimalField(
        _("distance to stop"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance to nearest stop in meters"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_updates",
        verbose_name=_("line"),
    )

    class Meta:
        verbose_name = _("location update")
        verbose_name_plural = _("location updates")
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["bus", "-created_at"]),
            models.Index(fields=["line", "-created_at"]),
            models.Index(fields=["trip_id"]),
        ]

    def __str__(self):
        return f"{self.bus} at {self.created_at}"


class PassengerCount(BaseModel):
    """
    Model for passenger count updates.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="passenger_counts",
        verbose_name=_("bus"),
    )
    count = models.PositiveSmallIntegerField(_("count"))
    capacity = models.PositiveSmallIntegerField(
        _("capacity"),
        help_text=_("Total capacity of the bus"),
    )
    occupancy_rate = models.DecimalField(
        _("occupancy rate"),
        max_digits=5,
        decimal_places=2,
        help_text=_("Occupancy rate (0-1)"),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    trip_id = models.UUIDField(
        _("trip ID"),
        null=True,
        blank=True,
        help_text=_("ID of the current trip"),
    )
    stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="passenger_counts",
        verbose_name=_("stop"),
        help_text=_("Stop where the count was recorded"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="passenger_counts",
        verbose_name=_("line"),
    )

    class Meta:
        verbose_name = _("passenger count")
        verbose_name_plural = _("passenger counts")
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        indexes = [
            models.Index(fields=["bus", "-created_at"]),
            models.Index(fields=["line", "-created_at"]),
            models.Index(fields=["trip_id"]),
        ]

    def __str__(self):
        return f"{self.bus}: {self.count} passengers at {self.created_at}"


class WaitingPassengers(BaseModel):
    """
    Model for waiting passengers at a stop.
    """
    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name="waiting_passengers",
        verbose_name=_("stop"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="waiting_passengers",
        verbose_name=_("line"),
        null=True,
        blank=True,
    )
    count = models.PositiveSmallIntegerField(_("count"))
    reported_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_waiting",
        verbose_name=_("reported by"),
    )

    class Meta:
        verbose_name = _("waiting passengers")
        verbose_name_plural = _("waiting passengers")
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return f"{self.stop}: {self.count} waiting at {self.created_at}"


class Trip(BaseModel):
    """
    Model for bus trips.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("bus"),
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("driver"),
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="trips",
        verbose_name=_("line"),
    )
    start_time = models.DateTimeField(_("start time"))
    end_time = models.DateTimeField(
        _("end time"),
        null=True,
        blank=True,
    )
    start_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_starts",
        verbose_name=_("start stop"),
    )
    end_stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trip_ends",
        verbose_name=_("end stop"),
    )
    is_completed = models.BooleanField(_("completed"), default=False)
    distance = models.DecimalField(
        _("distance"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance traveled in km"),
    )
    average_speed = models.DecimalField(
        _("average speed"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Average speed in km/h"),
    )
    max_passengers = models.PositiveSmallIntegerField(
        _("max passengers"),
        default=0,
        help_text=_("Maximum number of passengers during the trip"),
    )
    total_stops = models.PositiveSmallIntegerField(
        _("total stops"),
        default=0,
        help_text=_("Total number of stops made"),
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("trip")
        verbose_name_plural = _("trips")
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["bus", "-start_time"]),
            models.Index(fields=["driver", "-start_time"]),
            models.Index(fields=["line", "-start_time"]),
        ]

    def __str__(self):
        return f"{self.bus} on {self.line} at {self.start_time}"


class Anomaly(BaseModel):
    """
    Model for tracking anomalies.
    """
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name="anomalies",
        verbose_name=_("bus"),
    )
    trip = models.ForeignKey(
        Trip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomalies",
        verbose_name=_("trip"),
    )
    type = models.CharField(
        _("type"),
        max_length=50,
        choices=[
            ("speed", _("Speed anomaly")),
            ("route", _("Route deviation")),
            ("schedule", _("Schedule deviation")),
            ("passengers", _("Unusual passenger count")),
            ("gap", _("Service gap")),
            ("bunching", _("Bus bunching")),
            ("other", _("Other")),
        ],
    )
    description = models.TextField(_("description"))
    severity = models.CharField(
        _("severity"),
        max_length=20,
        choices=[
            ("low", _("Low")),
            ("medium", _("Medium")),
            ("high", _("High")),
        ],
        default="medium",
    )
    location_latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    location_longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    resolved = models.BooleanField(_("resolved"), default=False)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    resolution_notes = models.TextField(_("resolution notes"), blank=True)

    class Meta:
        verbose_name = _("anomaly")
        verbose_name_plural = _("anomalies")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} anomaly for {self.bus} at {self.created_at}"


class RouteSegment(BaseModel):
    """
    Store route segments between stops for visualization.
    """
    from_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='route_segments_from'
    )
    to_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='route_segments_to'
    )
    polyline = models.TextField(
        help_text=_('Encoded polyline for the route segment')
    )
    distance = models.FloatField(
        help_text=_('Distance in kilometers')
    )
    duration = models.IntegerField(
        help_text=_('Estimated duration in minutes')
    )
    
    class Meta:
        db_table = 'tracking_route_segments'
        unique_together = ['from_stop', 'to_stop']
        indexes = [
            models.Index(fields=['from_stop', 'to_stop']),
        ]
    
    def __str__(self):
        return f"{self.from_stop} -> {self.to_stop}"


__all__ = [
    'LocationUpdate',
    'Trip',
    'PassengerCount',
    'WaitingPassengers',
    'BusLine',
    'Anomaly',
    'RouteSegment',
]