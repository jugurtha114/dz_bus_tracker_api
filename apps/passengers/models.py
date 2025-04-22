from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel


class Passenger(BaseModel):
    user = models.OneToOneField(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='passenger_profile',
        verbose_name=_('user'),
    )
    
    # Additional passenger specific fields can be added here
    journey_count = models.PositiveIntegerField(
        _('journey count'),
        default=0,
    )
    
    notification_preferences = models.JSONField(
        _('notification preferences'),
        default=dict,
        blank=True,
    )
    
    home_location = models.JSONField(
        _('home location'),
        default=dict,
        blank=True,
    )
    
    work_location = models.JSONField(
        _('work location'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('passenger')
        verbose_name_plural = _('passengers')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Passenger: {self.user.email}"
    
    def save(self, *args, **kwargs):
        if not self.notification_preferences:
            self.notification_preferences = {
                'push_enabled': True,
                'email_enabled': True,
                'sms_enabled': self.user.is_phone_verified,
                'eta_threshold': 5  # notify 5 minutes before arrival
            }
        super().save(*args, **kwargs)


class SavedLocation(BaseModel):
    passenger = models.ForeignKey(
        'Passenger',
        on_delete=models.CASCADE,
        related_name='saved_locations',
        verbose_name=_('passenger'),
    )
    
    name = models.CharField(
        _('name'),
        max_length=100,
    )
    
    latitude = models.DecimalField(
        _('latitude'),
        max_digits=9,
        decimal_places=6,
    )
    
    longitude = models.DecimalField(
        _('longitude'),
        max_digits=9,
        decimal_places=6,
    )
    
    address = models.CharField(
        _('address'),
        max_length=255,
        blank=True,
    )
    
    is_favorite = models.BooleanField(
        _('favorite'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('saved location')
        verbose_name_plural = _('saved locations')
        ordering = ['-is_favorite', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.passenger.user.email})"


class TripHistory(BaseModel):
    passenger = models.ForeignKey(
        'Passenger',
        on_delete=models.CASCADE,
        related_name='trip_history',
        verbose_name=_('passenger'),
    )
    
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='passenger_trips',
        verbose_name=_('line'),
    )
    
    start_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='trip_starts',
        verbose_name=_('start stop'),
    )
    
    end_stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='trip_ends',
        verbose_name=_('end stop'),
    )
    
    start_time = models.DateTimeField(
        _('start time'),
    )
    
    end_time = models.DateTimeField(
        _('end time'),
        null=True,
        blank=True,
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=(
            ('started', _('Started')),
            ('completed', _('Completed')),
            ('cancelled', _('Cancelled')),
        ),
        default='started',
    )
    
    class Meta:
        verbose_name = _('trip history')
        verbose_name_plural = _('trip histories')
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Trip from {self.start_stop.name} to {self.end_stop.name} by {self.passenger.user.email}"


class FeedbackRequest(BaseModel):
    passenger = models.ForeignKey(
        'Passenger',
        on_delete=models.CASCADE,
        related_name='feedback_requests',
        verbose_name=_('passenger'),
    )
    
    trip = models.ForeignKey(
        'TripHistory',
        on_delete=models.CASCADE,
        related_name='feedback_requests',
        verbose_name=_('trip'),
        null=True,
        blank=True,
    )
    
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='feedback_requests',
        verbose_name=_('line'),
    )
    
    sent_at = models.DateTimeField(
        _('sent at'),
        auto_now_add=True,
    )
    
    expires_at = models.DateTimeField(
        _('expires at'),
    )
    
    is_completed = models.BooleanField(
        _('completed'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('feedback request')
        verbose_name_plural = _('feedback requests')
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Feedback request for {self.passenger.user.email} on {self.line.name}"
