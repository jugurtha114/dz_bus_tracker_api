from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.base.models import BaseModel
from apps.core.constants import NOTIFICATION_TYPES, NOTIFICATION_TYPE_SYSTEM


class Notification(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('user'),
    )
    
    type = models.CharField(
        _('type'),
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default=NOTIFICATION_TYPE_SYSTEM,
    )
    
    title = models.CharField(
        _('title'),
        max_length=255,
    )
    
    message = models.TextField(
        _('message'),
    )
    
    data = models.JSONField(
        _('data'),
        default=dict,
        blank=True,
    )
    
    is_read = models.BooleanField(
        _('read'),
        default=False,
    )
    
    read_at = models.DateTimeField(
        _('read at'),
        null=True,
        blank=True,
    )
    
    sent_via_push = models.BooleanField(
        _('sent via push'),
        default=False,
    )
    
    sent_via_email = models.BooleanField(
        _('sent via email'),
        default=False,
    )
    
    sent_via_sms = models.BooleanField(
        _('sent via SMS'),
        default=False,
    )
    
    is_action_required = models.BooleanField(
        _('action required'),
        default=False,
    )
    
    action_url = models.CharField(
        _('action URL'),
        max_length=255,
        blank=True,
    )
    
    expiration_date = models.DateTimeField(
        _('expiration date'),
        null=True,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['type']),
            models.Index(fields=['is_read']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} for {self.user.email}"


class NotificationPreference(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name=_('user'),
    )
    
    notification_type = models.CharField(
        _('notification type'),
        max_length=50,
        choices=NOTIFICATION_TYPES,
    )
    
    push_enabled = models.BooleanField(
        _('push enabled'),
        default=True,
    )
    
    email_enabled = models.BooleanField(
        _('email enabled'),
        default=True,
    )
    
    sms_enabled = models.BooleanField(
        _('SMS enabled'),
        default=False,
    )
    
    class Meta:
        verbose_name = _('notification preference')
        verbose_name_plural = _('notification preferences')
        ordering = ['user', 'notification_type']
        unique_together = [['user', 'notification_type']]
    
    def __str__(self):
        return f"{self.notification_type} preferences for {self.user.email}"


class PushToken(BaseModel):
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='push_tokens',
        verbose_name=_('user'),
    )
    
    token = models.TextField(
        _('token'),
    )
    
    device_type = models.CharField(
        _('device type'),
        max_length=50,
        choices=(
            ('ios', _('iOS')),
            ('android', _('Android')),
            ('web', _('Web')),
        ),
    )
    
    device_name = models.CharField(
        _('device name'),
        max_length=255,
        blank=True,
    )
    
    last_used = models.DateTimeField(
        _('last used'),
        auto_now=True,
    )
    
    class Meta:
        verbose_name = _('push token')
        verbose_name_plural = _('push tokens')
        ordering = ['-last_used']
        unique_together = [['user', 'token']]
    
    def __str__(self):
        return f"{self.device_type} token for {self.user.email}"


class NotificationLog(BaseModel):
    notification = models.ForeignKey(
        'Notification',
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name=_('notification'),
    )
    
    method = models.CharField(
        _('method'),
        max_length=50,
        choices=(
            ('push', _('Push')),
            ('email', _('Email')),
            ('sms', _('SMS')),
        ),
    )
    
    success = models.BooleanField(
        _('success'),
        default=False,
    )
    
    error_message = models.TextField(
        _('error message'),
        blank=True,
    )
    
    provider_response = models.JSONField(
        _('provider response'),
        default=dict,
        blank=True,
    )
    
    class Meta:
        verbose_name = _('notification log')
        verbose_name_plural = _('notification logs')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.method} notification for {self.notification.user.email}"
