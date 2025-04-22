from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.core.base.models import BaseModel, TimeStampedModel, UUIDModel, GeoPointModel
from apps.core.constants import TRACKING_STATUSES, TRACKING_STATUS_ACTIVE


class TrackingSession(BaseModel):
    """
    Model for tracking sessions.
    """
    driver = models.ForeignKey(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name='tracking_sessions',
        verbose_name=_('driver'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='tracking_sessions',
        verbose_name=_('bus'),
    )
    
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='tracking_sessions',
        verbose_name=_('line'),
    )
    
    schedule = models.ForeignKey(
        'schedules.Schedule',
        on_delete=models.SET_NULL,
        related_name='tracking_sessions',
        verbose_name=_('schedule'),
        null=True,
        blank=True,
    )
    
    start_time = models.DateTimeField(
        _('start time'),
        default=timezone.now,
    )
    
    end_time = models.DateTimeField(
        _('end time'),
        null=True,
        blank=True,
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=TRACKING_STATUSES,
        default=TRACKING_STATUS_ACTIVE,
    )
    
    last_update = models.DateTimeField(
        _('last update'),
        null=True,
        blank=True,
    )
    
    total_distance = models.FloatField(
        _('total distance (meters)'),
        default=0,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('tracking session')
        verbose_name_plural = _('tracking sessions')
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['driver']),
            models.Index(fields=['bus']),
            models.Index(fields=['line']),
            models.Index(fields=['status']),
            models.Index(fields=['start_time']),
        ]
    
    def __str__(self):
        return f"Session {self.id} - {self.bus} on {self.line}"
    
    @property
    def duration(self):
        """
        Get the duration of the tracking session.
        """
        if self.end_time:
            return self.end_time - self.start_time
        
        return timezone.now() - self.start_time
    
    @property
    def is_active(self):
        """
        Check if the tracking session is active.
        """
        return self.status == TRACKING_STATUS_ACTIVE
    
    def end_session(self):
        """
        End the tracking session.
        """
        if not self.end_time:
            self.end_time = timezone.now()
            self.status = 'completed'
            self.save(update_fields=['end_time', 'status'])


class LocationUpdate(TimeStampedModel, UUIDModel, GeoPointModel):
    """
    Model for location updates.
    """
    session = models.ForeignKey(
        'TrackingSession',
        on_delete=models.CASCADE,
        related_name='location_updates',
        verbose_name=_('session'),
    )
    
    timestamp = models.DateTimeField(
        _('timestamp'),
        default=timezone.now,
        db_index=True,
    )
    
    speed = models.FloatField(
        _('speed (m/s)'),
        null=True,
        blank=True,
    )
    
    heading = models.FloatField(
        _('heading (degrees)'),
        null=True,
        blank=True,
    )
    
    altitude = models.FloatField(
        _('altitude (meters)'),
        null=True,
        blank=True,
    )
    
    distance_from_last = models.FloatField(
        _('distance from last update (meters)'),
        null=True,
        blank=True,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('location update')
        verbose_name_plural = _('location updates')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"Location update at {self.timestamp}"
    
    def save(self, *args, **kwargs):
        """
        Override save method to update the tracking session.
        """
        # If this is a new object (no ID yet)
        if not self.pk:
            # Update the session's last_update
            self.session.last_update = self.timestamp
            self.session.save(update_fields=['last_update'])
            
            # Calculate distance from previous update if not provided
            if self.distance_from_last is None:
                previous_update = LocationUpdate.objects.filter(
                    session=self.session
                ).order_by('-timestamp').first()
                
                if previous_update:
                    from utils.geo import calculate_distance
                    self.distance_from_last = calculate_distance(
                        previous_update.coordinates,
                        self.coordinates
                    )
                    
                    # Update session's total distance
                    self.session.total_distance += self.distance_from_last
                    self.session.save(update_fields=['total_distance'])
        
        super().save(*args, **kwargs)


class TrackingLog(BaseModel):
    """
    Model for tracking logs.
    """
    session = models.ForeignKey(
        'TrackingSession',
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name=_('session'),
    )
    
    event_type = models.CharField(
        _('event type'),
        max_length=50,
    )
    
    timestamp = models.DateTimeField(
        _('timestamp'),
        default=timezone.now,
    )
    
    message = models.TextField(
        _('message'),
        blank=True,
    )
    
    data = models.JSONField(
        _('data'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('tracking log')
        verbose_name_plural = _('tracking logs')
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.event_type} at {self.timestamp}"


class OfflineLocationBatch(BaseModel):
    """
    Model for storing batched location updates that were collected offline.
    """
    driver = models.ForeignKey(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name='offline_batches',
        verbose_name=_('driver'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='offline_batches',
        verbose_name=_('bus'),
    )
    
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='offline_batches',
        verbose_name=_('line'),
    )
    
    collected_at = models.DateTimeField(
        _('collected at'),
        default=timezone.now,
    )
    
    processed = models.BooleanField(
        _('processed'),
        default=False,
    )
    
    processed_at = models.DateTimeField(
        _('processed at'),
        null=True,
        blank=True,
    )
    
    data = models.JSONField(
        _('location data'),
        default=list,
    )
    
    class Meta:
        verbose_name = _('offline location batch')
        verbose_name_plural = _('offline location batches')
        ordering = ['-collected_at']
    
    def __str__(self):
        return f"Batch {self.id} - {self.driver} at {self.collected_at}"
    
    def process(self):
        """
        Process the batch by creating location updates.
        """
        from .services import process_offline_batch
        processed = process_offline_batch(self)
        
        if processed:
            self.processed = True
            self.processed_at = timezone.now()
            self.save(update_fields=['processed', 'processed_at'])
        
        return processed