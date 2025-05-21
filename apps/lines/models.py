"""
Models for the lines app.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Stop(BaseModel):
    """
    Model for bus stops.
    """
    name = models.CharField(_("name"), max_length=100)
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
    address = models.CharField(_("address"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    description = models.TextField(_("description"), blank=True)
    features = models.JSONField(
        _("features"),
        default=list,
        blank=True,
        help_text=_("Features of the stop (shelter, bench, etc.)"),
    )
    photo = models.ImageField(
        _("photo"),
        upload_to="stops/",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("stop")
        verbose_name_plural = _("stops")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return self.name


class Line(BaseModel):
    """
    Model for bus lines.
    """
    name = models.CharField(_("name"), max_length=100)
    code = models.CharField(_("code"), max_length=20, unique=True)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    color = models.CharField(
        _("color"),
        max_length=7,
        default="#000000",
        help_text=_("Hex color code for the line (e.g., #FF0000)"),
    )
    frequency = models.PositiveSmallIntegerField(
        _("frequency"),
        help_text=_("Average frequency in minutes"),
        null=True,
        blank=True,
    )
    stops = models.ManyToManyField(
        Stop,
        through="LineStop",
        related_name="lines",
        verbose_name=_("stops"),
    )

    class Meta:
        verbose_name = _("line")
        verbose_name_plural = _("lines")
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class LineStop(BaseModel):
    """
    Through model for line-stop relationship with order.
    """
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="line_stops",
        verbose_name=_("line"),
    )
    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name="line_stops",
        verbose_name=_("stop"),
    )
    order = models.PositiveSmallIntegerField(_("order"))
    distance_from_previous = models.DecimalField(
        _("distance from previous"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Distance from previous stop in meters"),
    )
    average_time_from_previous = models.PositiveSmallIntegerField(
        _("average time from previous"),
        null=True,
        blank=True,
        help_text=_("Average time from previous stop in seconds"),
    )

    class Meta:
        verbose_name = _("line stop")
        verbose_name_plural = _("line stops")
        ordering = ["line", "order"]
        unique_together = [["line", "stop"], ["line", "order"]]

    def __str__(self):
        return f"{self.line} - {self.stop} (#{self.order})"


class Schedule(BaseModel):
    """
    Model for line schedules.
    """
    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("line"),
    )
    day_of_week = models.PositiveSmallIntegerField(
        _("day of week"),
        choices=[
            (0, _("Monday")),
            (1, _("Tuesday")),
            (2, _("Wednesday")),
            (3, _("Thursday")),
            (4, _("Friday")),
            (5, _("Saturday")),
            (6, _("Sunday")),
        ],
    )
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    is_active = models.BooleanField(_("active"), default=True)
    frequency_minutes = models.PositiveSmallIntegerField(
        _("frequency minutes"),
        help_text=_("Bus frequency in minutes during this schedule"),
    )

    class Meta:
        verbose_name = _("schedule")
        verbose_name_plural = _("schedules")
        ordering = ["line", "day_of_week", "start_time"]
        unique_together = [["line", "day_of_week", "start_time"]]

    def __str__(self):
        days = [
            _("Monday"), _("Tuesday"), _("Wednesday"),
            _("Thursday"), _("Friday"), _("Saturday"), _("Sunday")
        ]
        return f"{self.line} - {days[self.day_of_week]}: {self.start_time} - {self.end_time}"