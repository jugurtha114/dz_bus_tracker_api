"""
Serializers for offline mode API.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from drf_spectacular.utils import extend_schema_field

from .models import (
    CacheConfiguration,
    UserCache,
    CachedData,
    SyncQueue,
    OfflineLog,
)

User = get_user_model()


class CacheConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for cache configuration."""
    
    class Meta:
        model = CacheConfiguration
        fields = [
            'id', 'name', 'is_active',
            'cache_duration_hours', 'max_cache_size_mb',
            'cache_lines', 'cache_stops', 'cache_schedules',
            'cache_buses', 'cache_user_favorites', 'cache_notifications',
            'auto_sync_on_connect', 'sync_interval_minutes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserCacheSerializer(serializers.ModelSerializer):
    """Serializer for user cache."""
    
    cache_size_mb = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = UserCache
        fields = [
            'id', 'last_sync_at', 'cache_size_bytes', 'cache_size_mb',
            'cache_version', 'is_syncing', 'sync_progress', 'last_error',
            'cached_lines_count', 'cached_stops_count', 'cached_schedules_count',
            'is_expired', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'cache_size_bytes', 'cache_size_mb', 'is_expired',
            'created_at', 'updated_at'
        ]


class CachedDataSerializer(serializers.ModelSerializer):
    """Serializer for cached data."""
    
    class Meta:
        model = CachedData
        fields = [
            'id', 'data_type', 'data_id', 'data',
            'size_bytes', 'checksum', 'expires_at',
            'related_ids', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SyncQueueSerializer(serializers.ModelSerializer):
    """Serializer for sync queue items."""
    
    class Meta:
        model = SyncQueue
        fields = [
            'id', 'action_type', 'model_name', 'object_id',
            'data', 'status', 'attempts', 'last_attempt_at',
            'completed_at', 'error_message', 'priority',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'attempts', 'last_attempt_at', 'completed_at',
            'error_message', 'created_at', 'updated_at'
        ]


class OfflineLogSerializer(serializers.ModelSerializer):
    """Serializer for offline logs."""
    
    class Meta:
        model = OfflineLog
        fields = [
            'id', 'log_type', 'message', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SyncRequestSerializer(serializers.Serializer):
    """Serializer for sync request."""
    
    force = serializers.BooleanField(
        default=False,
        help_text='Force sync even if cache is not expired'
    )


class QueueActionSerializer(serializers.Serializer):
    """Serializer for queuing offline actions."""
    
    action_type = serializers.ChoiceField(
        choices=['create', 'update', 'delete']
    )
    model_name = serializers.CharField(max_length=100)
    object_id = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True
    )
    data = serializers.JSONField()
    priority = serializers.IntegerField(default=0)


class CacheStatisticsSerializer(serializers.Serializer):
    """Serializer for cache statistics."""
    
    cache_size_mb = serializers.FloatField()
    last_sync = serializers.DateTimeField(allow_null=True)
    is_expired = serializers.BooleanField()
    item_counts = serializers.DictField()
    total_items = serializers.IntegerField()
    sync_queue = serializers.DictField()


class DataRequestSerializer(serializers.Serializer):
    """Serializer for cached data request."""
    
    data_type = serializers.ChoiceField(
        choices=['line', 'stop', 'schedule', 'bus', 
                 'favorite', 'notification', 'route']
    )
    data_id = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True
    )