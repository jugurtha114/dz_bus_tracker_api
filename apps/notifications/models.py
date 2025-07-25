"""
Models for the notifications app.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from django.contrib.postgres.fields import ArrayField

from apps.accounts.models import User
from apps.core.constants import (
    NOTIFICATION_CHANNEL_CHOICES,
    NOTIFICATION_CHANNEL_IN_APP,
    NOTIFICATION_TYPE_CHOICES,
)
from apps.core.models import BaseModel
from apps.buses.models import Bus
from apps.lines.models import Line, Stop
from apps.tracking.models import Trip


class DeviceToken(BaseModel):
    """
    Model for device tokens for push notifications.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_tokens",
        verbose_name=_("user"),
    )
    token = models.TextField(_("token"))
    device_type = models.CharField(
        _("device type"),
        max_length=20,
        choices=[
            ("ios", "iOS"),
            ("android", "Android"),
            ("web", "Web"),
        ],
    )
    is_active = models.BooleanField(_("active"), default=True)
    last_used = models.DateTimeField(
        _("last used"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("device token")
        verbose_name_plural = _("device tokens")
        ordering = ["-created_at"]
        unique_together = [["user", "token"]]

    def __str__(self):
        return f"{self.user} - {self.device_type} token"


class Notification(BaseModel):
    """
    Model for notifications.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("user"),
    )
    notification_type = models.CharField(
        _("notification type"),
        max_length=50,
        choices=NOTIFICATION_TYPE_CHOICES,
    )
    title = models.CharField(_("title"), max_length=255)
    message = models.TextField(_("message"))
    channel = models.CharField(
        _("channel"),
        max_length=20,
        choices=NOTIFICATION_CHANNEL_CHOICES,
        default=NOTIFICATION_CHANNEL_IN_APP,
    )
    is_read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    data = models.JSONField(
        _("data"),
        default=dict,
        blank=True,
        help_text=_("Additional data for the notification"),
    )

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.title} ({self.created_at})"


class NotificationPreference(BaseModel):
    """
    User preferences for notifications.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name=_("user")
    )
    notification_type = models.CharField(
        _('notification type'),
        max_length=50,
        choices=NOTIFICATION_TYPE_CHOICES
    )
    channels = ArrayField(
        models.CharField(max_length=20, choices=NOTIFICATION_CHANNEL_CHOICES),
        default=list,
        help_text=_('Preferred notification channels')
    )
    enabled = models.BooleanField(_('enabled'), default=True)
    
    # Timing preferences
    minutes_before_arrival = models.IntegerField(
        _('minutes before arrival'),
        default=10,
        help_text=_('For arrival notifications')
    )
    quiet_hours_start = models.TimeField(
        _('quiet hours start'),
        null=True,
        blank=True,
        help_text=_('Do not send notifications after this time')
    )
    quiet_hours_end = models.TimeField(
        _('quiet hours end'),
        null=True,
        blank=True,
        help_text=_('Resume notifications after this time')
    )
    
    # Location preferences
    favorite_stops = models.ManyToManyField(
        Stop,
        blank=True,
        related_name='notification_preferences',
        help_text=_('Get notifications for these stops')
    )
    favorite_lines = models.ManyToManyField(
        Line,
        blank=True,
        related_name='notification_preferences',
        help_text=_('Get notifications for these lines')
    )
    
    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")
        unique_together = ['user', 'notification_type']
        
    def __str__(self):
        return f"{self.user.email} - {self.notification_type}"


class NotificationSchedule(BaseModel):
    """
    Scheduled notifications for future delivery.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scheduled_notifications',
        verbose_name=_("user")
    )
    notification_type = models.CharField(
        _('type'),
        max_length=50,
        choices=NOTIFICATION_TYPE_CHOICES
    )
    scheduled_for = models.DateTimeField(_('scheduled for'))
    
    # Notification content
    title = models.CharField(_('title'), max_length=255)
    message = models.TextField(_('message'))
    channels = ArrayField(
        models.CharField(max_length=20, choices=NOTIFICATION_CHANNEL_CHOICES),
        default=list,
        help_text=_('Channels to send through')
    )
    data = models.JSONField(_('data'), default=dict)
    
    # Related objects
    bus = models.ForeignKey(
        Bus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    stop = models.ForeignKey(
        Stop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    line = models.ForeignKey(
        Line,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    trip = models.ForeignKey(
        Trip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Status
    is_sent = models.BooleanField(_('is sent'), default=False)
    sent_at = models.DateTimeField(_('sent at'), null=True, blank=True)
    error = models.TextField(_('error'), blank=True)
    
    class Meta:
        verbose_name = _("notification schedule")
        verbose_name_plural = _("notification schedules")
        ordering = ['scheduled_for']
        indexes = [
            models.Index(fields=['is_sent', 'scheduled_for']),
            models.Index(fields=['user', 'scheduled_for']),
        ]
        
    def __str__(self):
        return f"{self.title} - {self.scheduled_for}"