from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel, GeoPointModel


class Line(BaseModel):
    name = models.CharField(
        _('name'),
        max_length=100,
    )
    
    description = models.TextField(
        _('description'),
        blank=True,
    )
    
    color = models.CharField(
        _('color'),
        max_length=7,  # Hex color code
        default='#3498db',
    )
    
    start_location = models.ForeignKey(
        'Stop',
        on_delete=models.CASCADE,
        related_name='lines_starting',
        verbose_name=_('start location'),
    )
    
    end_location = models.ForeignKey(
        'Stop',
        on_delete=models.CASCADE,
        related_name='lines_ending',
        verbose_name=_('end location'),
    )
    
    path = models.JSONField(
        _('path'),
        help_text=_('GeoJSON representation of the line path'),
        default=dict,
        blank=True,
    )
    
    estimated_duration = models.PositiveIntegerField(
        _('estimated duration (minutes)'),
        default=0,
    )
    
    distance = models.FloatField(
        _('distance (meters)'),
        default=0,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('line')
        verbose_name_plural = _('lines')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['start_location']),
            models.Index(fields=['end_location']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.start_location.name} - {self.end_location.name})"
    
    @property
    def stops_count(self):
        return self.line_stops.count()
    
    @property
    def active_buses_count(self):
        return self.tracking_sessions.filter(status='active').count()
    
    def get_ordered_stops(self):
        return [line_stop.stop for line_stop in self.line_stops.all().order_by('order')]


class Stop(BaseModel, GeoPointModel):
    name = models.CharField(
        _('name'),
        max_length=100,
    )
    
    code = models.CharField(
        _('code'),
        max_length=20,
        blank=True,
    )
    
    address = models.CharField(
        _('address'),
        max_length=255,
        blank=True,
    )
    
    image = models.ImageField(
        _('image'),
        upload_to='stop_images/',
        blank=True,
        null=True,
    )
    
    description = models.TextField(
        _('description'),
        blank=True,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('stop')
        verbose_name_plural = _('stops')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return self.name


class LineStop(BaseModel):
    line = models.ForeignKey(
        'Line',
        on_delete=models.CASCADE,
        related_name='line_stops',
        verbose_name=_('line'),
    )
    
    stop = models.ForeignKey(
        'Stop',
        on_delete=models.CASCADE,
        related_name='line_stops',
        verbose_name=_('stop'),
    )
    
    order = models.PositiveIntegerField(
        _('order'),
        default=0,
    )
    
    distance_from_start = models.FloatField(
        _('distance from start (meters)'),
        default=0,
    )
    
    estimated_time_from_start = models.PositiveIntegerField(
        _('estimated time from start (seconds)'),
        default=0,
    )
    
    class Meta:
        verbose_name = _('line stop')
        verbose_name_plural = _('line stops')
        ordering = ['line', 'order']
        unique_together = [['line', 'stop'], ['line', 'order']]
        indexes = [
            models.Index(fields=['line', 'order']),
        ]
    
    def __str__(self):
        return f"{self.line.name} - {self.stop.name} (Order: {self.order})"
    
    @property
    def is_terminal(self):
        return self.order == 0 or self.order == self.line.line_stops.count() - 1


class LineBus(BaseModel):
    line = models.ForeignKey(
        'Line',
        on_delete=models.CASCADE,
        related_name='line_buses',
        verbose_name=_('line'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='line_buses',
        verbose_name=_('bus'),
    )
    
    is_primary = models.BooleanField(
        _('primary'),
        default=False,
        help_text=_('Whether this is the primary line for this bus'),
    )
    
    class Meta:
        verbose_name = _('line bus')
        verbose_name_plural = _('line buses')
        ordering = ['line', 'bus']
        unique_together = [['line', 'bus']]
    
    def __str__(self):
        return f"{self.line.name} - {self.bus.matricule}"


class Favorite(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='favorites',
        verbose_name=_('user'),
    )
    
    line = models.ForeignKey(
        'Line',
        on_delete=models.CASCADE,
        related_name='favorites',
        verbose_name=_('line'),
    )
    
    notification_threshold = models.PositiveIntegerField(
        _('notification threshold (minutes)'),
        default=5,
        help_text=_('Notify when bus is this many minutes away'),
    )
    
    class Meta:
        verbose_name = _('favorite')
        verbose_name_plural = _('favorites')
        ordering = ['user', 'line']
        unique_together = [['user', 'line']]
    
    def __str__(self):
        return f"{self.user.email} - {self.line.name}"
