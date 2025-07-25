"""
Models for offline mode data caching.
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField

from apps.core.models import BaseModel, TimeStampedMixin

User = get_user_model()


class CacheConfiguration(TimeStampedMixin, models.Model):
    """
    Configuration for offline cache behavior.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='configuration name'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='is active'
    )
    
    # Cache settings
    cache_duration_hours = models.IntegerField(
        default=24,
        verbose_name='cache duration (hours)',
        help_text='How long cached data remains valid'
    )
    max_cache_size_mb = models.IntegerField(
        default=100,
        verbose_name='max cache size (MB)',
        help_text='Maximum size of offline cache per user'
    )
    
    # Data types to cache
    cache_lines = models.BooleanField(
        default=True,
        verbose_name='cache lines data'
    )
    cache_stops = models.BooleanField(
        default=True,
        verbose_name='cache stops data'
    )
    cache_schedules = models.BooleanField(
        default=True,
        verbose_name='cache schedules data'
    )
    cache_buses = models.BooleanField(
        default=True,
        verbose_name='cache buses data'
    )
    cache_user_favorites = models.BooleanField(
        default=True,
        verbose_name='cache user favorites'
    )
    cache_notifications = models.BooleanField(
        default=True,
        verbose_name='cache notifications'
    )
    
    # Sync settings
    auto_sync_on_connect = models.BooleanField(
        default=True,
        verbose_name='auto sync on connection'
    )
    sync_interval_minutes = models.IntegerField(
        default=30,
        verbose_name='sync interval (minutes)',
        help_text='How often to sync when online'
    )
    
    class Meta:
        verbose_name = 'cache configuration'
        verbose_name_plural = 'cache configurations'
    
    def __str__(self):
        return self.name


class UserCache(BaseModel, TimeStampedMixin):
    """
    Tracks offline cache for each user.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='offline_cache',
        verbose_name='user'
    )
    
    # Cache metadata
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='last sync time'
    )
    cache_size_bytes = models.BigIntegerField(
        default=0,
        verbose_name='cache size (bytes)'
    )
    cache_version = models.CharField(
        max_length=20,
        default='1.0',
        verbose_name='cache version'
    )
    
    # Sync status
    is_syncing = models.BooleanField(
        default=False,
        verbose_name='is syncing'
    )
    sync_progress = models.IntegerField(
        default=0,
        verbose_name='sync progress (%)'
    )
    last_error = models.TextField(
        blank=True,
        verbose_name='last sync error'
    )
    
    # Cache content tracking
    cached_lines_count = models.IntegerField(
        default=0,
        verbose_name='cached lines count'
    )
    cached_stops_count = models.IntegerField(
        default=0,
        verbose_name='cached stops count'
    )
    cached_schedules_count = models.IntegerField(
        default=0,
        verbose_name='cached schedules count'
    )
    
    class Meta:
        verbose_name = 'user cache'
        verbose_name_plural = 'user caches'
    
    def __str__(self):
        return f"Cache for {self.user.email}"
    
    @property
    def cache_size_mb(self):
        """Get cache size in megabytes."""
        return self.cache_size_bytes / (1024 * 1024)
    
    @property
    def is_expired(self):
        """Check if cache is expired."""
        if not self.last_sync_at:
            return True
        
        config = CacheConfiguration.objects.filter(is_active=True).first()
        if not config:
            return False
        
        expiry_time = self.last_sync_at + timezone.timedelta(hours=config.cache_duration_hours)
        return timezone.now() > expiry_time


class CachedData(BaseModel, TimeStampedMixin):
    """
    Stores cached data for offline access.
    """
    DATA_TYPES = [
        ('line', 'Line'),
        ('stop', 'Stop'),
        ('schedule', 'Schedule'),
        ('bus', 'Bus'),
        ('favorite', 'Favorite'),
        ('notification', 'Notification'),
        ('route', 'Route'),
    ]
    
    user_cache = models.ForeignKey(
        UserCache,
        on_delete=models.CASCADE,
        related_name='cached_items',
        verbose_name='user cache'
    )
    data_type = models.CharField(
        max_length=20,
        choices=DATA_TYPES,
        verbose_name='data type'
    )
    data_id = models.CharField(
        max_length=100,
        verbose_name='data ID',
        help_text='ID of the cached object'
    )
    data = models.JSONField(
        verbose_name='cached data'
    )
    
    # Metadata
    size_bytes = models.IntegerField(
        default=0,
        verbose_name='size (bytes)'
    )
    checksum = models.CharField(
        max_length=64,
        blank=True,
        verbose_name='data checksum'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='expires at'
    )
    
    # Related data tracking
    related_ids = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        verbose_name='related data IDs'
    )
    
    class Meta:
        verbose_name = 'cached data'
        verbose_name_plural = 'cached data'
        unique_together = ['user_cache', 'data_type', 'data_id']
        indexes = [
            models.Index(fields=['user_cache', 'data_type']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.data_type} - {self.data_id}"


class SyncQueue(BaseModel, TimeStampedMixin):
    """
    Queue for syncing offline changes when back online.
    """
    ACTION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('syncing', 'Syncing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sync_queue',
        verbose_name='user'
    )
    
    # Action details
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        verbose_name='action type'
    )
    model_name = models.CharField(
        max_length=100,
        verbose_name='model name'
    )
    object_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='object ID'
    )
    data = models.JSONField(
        verbose_name='action data'
    )
    
    # Sync status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='status'
    )
    attempts = models.IntegerField(
        default=0,
        verbose_name='sync attempts'
    )
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='last attempt time'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='completed at'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='error message'
    )
    
    # Priority
    priority = models.IntegerField(
        default=0,
        verbose_name='priority',
        help_text='Higher values are synced first'
    )
    
    class Meta:
        verbose_name = 'sync queue item'
        verbose_name_plural = 'sync queue items'
        ordering = ['-priority', 'created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', '-priority']),
        ]
    
    def __str__(self):
        return f"{self.action_type} {self.model_name} - {self.status}"


class OfflineLog(TimeStampedMixin, models.Model):
    """
    Logs offline mode events and actions.
    """
    LOG_TYPES = [
        ('sync_start', 'Sync Started'),
        ('sync_complete', 'Sync Completed'),
        ('sync_error', 'Sync Error'),
        ('cache_hit', 'Cache Hit'),
        ('cache_miss', 'Cache Miss'),
        ('cache_expired', 'Cache Expired'),
        ('cache_cleared', 'Cache Cleared'),
        ('offline_action', 'Offline Action'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='offline_logs',
        verbose_name='user'
    )
    log_type = models.CharField(
        max_length=30,
        choices=LOG_TYPES,
        verbose_name='log type'
    )
    message = models.TextField(
        verbose_name='message'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='metadata'
    )
    
    class Meta:
        verbose_name = 'offline log'
        verbose_name_plural = 'offline logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['log_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.log_type} - {self.user.email} - {self.created_at}"
