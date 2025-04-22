from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel
from apps.core.constants import ETA_STATUSES, ETA_STATUS_SCHEDULED


class ETA(BaseModel):
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='etas',
        verbose_name=_('line'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='etas',
        verbose_name=_('bus'),
    )
    
    stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='etas',
        verbose_name=_('stop'),
    )
    
    tracking_session = models.ForeignKey(
        'tracking.TrackingSession',
        on_delete=models.CASCADE,
        related_name='etas',
        verbose_name=_('tracking session'),
    )
    
    estimated_arrival_time = models.DateTimeField(
        _('estimated arrival time'),
    )
    
    actual_arrival_time = models.DateTimeField(
        _('actual arrival time'),
        null=True,
        blank=True,
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=ETA_STATUSES,
        default=ETA_STATUS_SCHEDULED,
    )
    
    delay_minutes = models.IntegerField(
        _('delay minutes'),
        default=0,
    )
    
    accuracy = models.IntegerField(
        _('accuracy (seconds)'),
        default=60,
    )
    
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('ETA')
        verbose_name_plural = _('ETAs')
        ordering = ['estimated_arrival_time']
        indexes = [
            models.Index(fields=['line', 'stop']),
            models.Index(fields=['bus']),
            models.Index(fields=['tracking_session']),
            models.Index(fields=['estimated_arrival_time']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.bus} at {self.stop} - {self.estimated_arrival_time}"


class ETANotification(BaseModel):
    eta = models.ForeignKey(
        'ETA',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('ETA'),
    )
    
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='eta_notifications',
        verbose_name=_('user'),
    )
    
    notification_threshold = models.PositiveIntegerField(
        _('notification threshold (minutes)'),
        default=5,
    )
    
    sent_at = models.DateTimeField(
        _('sent at'),
        null=True,
        blank=True,
    )
    
    is_sent = models.BooleanField(
        _('sent'),
        default=False,
    )
    
    notification_type = models.CharField(
        _('notification type'),
        max_length=20,
        choices=(
            ('push', _('Push')),
            ('sms', _('SMS')),
            ('email', _('Email')),
        ),
        default='push',
    )
    
    notification_id = models.CharField(
        _('notification ID'),
        max_length=255,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('ETA notification')
        verbose_name_plural = _('ETA notifications')
        ordering = ['-created_at']
        unique_together = [['eta', 'user', 'notification_type']]
    
    def __str__(self):
        return f"Notification for {self.user} about {self.eta}"


class StopArrival(BaseModel):
    tracking_session = models.ForeignKey(
        'tracking.TrackingSession',
        on_delete=models.CASCADE,
        related_name='stop_arrivals',
        verbose_name=_('tracking session'),
    )
    
    line = models.ForeignKey(
        'lines.Line',
        on_delete=models.CASCADE,
        related_name='stop_arrivals',
        verbose_name=_('line'),
    )
    
    stop = models.ForeignKey(
        'lines.Stop',
        on_delete=models.CASCADE,
        related_name='arrivals',
        verbose_name=_('stop'),
    )
    
    bus = models.ForeignKey(
        'buses.Bus',
        on_delete=models.CASCADE,
        related_name='stop_arrivals',
        verbose_name=_('bus'),
    )
    
    arrival_time = models.DateTimeField(
        _('arrival time'),
    )
    
    departure_time = models.DateTimeField(
        _('departure time'),
        null=True,
        blank=True,
    )
    
    scheduled_arrival_time = models.DateTimeField(
        _('scheduled arrival time'),
        null=True,
        blank=True,
    )
    
    delay_minutes = models.IntegerField(
        _('delay minutes'),
        default=0,
    )
    
    class Meta:
        verbose_name = _('stop arrival')
        verbose_name_plural = _('stop arrivals')
        ordering = ['-arrival_time']
        indexes = [
            models.Index(fields=['tracking_session']),
            models.Index(fields=['line', 'stop']),
            models.Index(fields=['bus']),
            models.Index(fields=['arrival_time']),
        ]
    
    def __str__(self):
        return f"{self.bus} at {self.stop} - {self.arrival_time}"
