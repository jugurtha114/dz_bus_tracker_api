"""
Admin configuration for offline mode models.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    CacheConfiguration,
    UserCache,
    CachedData,
    SyncQueue,
    OfflineLog,
)


@admin.register(CacheConfiguration)
class CacheConfigurationAdmin(admin.ModelAdmin):
    """Admin for cache configurations."""
    
    list_display = [
        'name', 'is_active', 'cache_duration_hours',
        'max_cache_size_mb', 'sync_interval_minutes',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'is_active')
        }),
        ('Cache Settings', {
            'fields': (
                'cache_duration_hours',
                'max_cache_size_mb'
            )
        }),
        ('Data Types', {
            'fields': (
                'cache_lines',
                'cache_stops',
                'cache_schedules',
                'cache_buses',
                'cache_user_favorites',
                'cache_notifications'
            )
        }),
        ('Sync Settings', {
            'fields': (
                'auto_sync_on_connect',
                'sync_interval_minutes'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserCache)
class UserCacheAdmin(admin.ModelAdmin):
    """Admin for user caches."""
    
    list_display = [
        'user_email', 'cache_size_display', 'last_sync_at',
        'is_syncing', 'sync_progress_display', 'is_expired_display',
        'created_at'
    ]
    list_filter = ['is_syncing', 'cache_version', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    raw_id_fields = ['user']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Cache Metadata', {
            'fields': (
                'last_sync_at',
                'cache_size_bytes',
                'cache_version'
            )
        }),
        ('Sync Status', {
            'fields': (
                'is_syncing',
                'sync_progress',
                'last_error'
            )
        }),
        ('Cache Content', {
            'fields': (
                'cached_lines_count',
                'cached_stops_count',
                'cached_schedules_count'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def user_email(self, obj):
        """Get user email."""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def cache_size_display(self, obj):
        """Display cache size in MB."""
        return f"{obj.cache_size_mb:.2f} MB"
    cache_size_display.short_description = 'Cache Size'
    cache_size_display.admin_order_field = 'cache_size_bytes'
    
    def sync_progress_display(self, obj):
        """Display sync progress with color."""
        color = 'green' if obj.sync_progress == 100 else 'orange'
        return format_html(
            '<span style="color: {};">{} %</span>',
            color,
            obj.sync_progress
        )
    sync_progress_display.short_description = 'Sync Progress'
    
    def is_expired_display(self, obj):
        """Display expiration status."""
        if obj.is_expired:
            return format_html('<span style="color: red;">✗ Expired</span>')
        return format_html('<span style="color: green;">✓ Valid</span>')
    is_expired_display.short_description = 'Cache Status'


@admin.register(CachedData)
class CachedDataAdmin(admin.ModelAdmin):
    """Admin for cached data."""
    
    list_display = [
        'user_email', 'data_type', 'data_id',
        'size_display', 'expires_at', 'created_at'
    ]
    list_filter = ['data_type', 'created_at', 'expires_at']
    search_fields = [
        'user_cache__user__email',
        'data_id',
        'data_type'
    ]
    raw_id_fields = ['user_cache']
    
    fieldsets = (
        ('Cache Information', {
            'fields': ('user_cache', 'data_type', 'data_id')
        }),
        ('Data', {
            'fields': ('data',),
            'classes': ('wide',)
        }),
        ('Metadata', {
            'fields': (
                'size_bytes',
                'checksum',
                'expires_at',
                'related_ids'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at', 'checksum']
    
    def user_email(self, obj):
        """Get user email."""
        return obj.user_cache.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user_cache__user__email'
    
    def size_display(self, obj):
        """Display size in KB."""
        return f"{obj.size_bytes / 1024:.2f} KB"
    size_display.short_description = 'Size'
    size_display.admin_order_field = 'size_bytes'


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    """Admin for sync queue."""
    
    list_display = [
        'user_email', 'action_type', 'model_name',
        'status_display', 'priority', 'attempts',
        'created_at'
    ]
    list_filter = [
        'status', 'action_type', 'model_name',
        'priority', 'created_at'
    ]
    search_fields = [
        'user__email',
        'model_name',
        'object_id'
    ]
    raw_id_fields = ['user']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Action Details', {
            'fields': (
                'action_type',
                'model_name',
                'object_id',
                'data'
            )
        }),
        ('Sync Status', {
            'fields': (
                'status',
                'attempts',
                'last_attempt_at',
                'completed_at',
                'error_message'
            )
        }),
        ('Priority', {
            'fields': ('priority',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = [
        'created_at', 'updated_at',
        'last_attempt_at', 'completed_at'
    ]
    
    def user_email(self, obj):
        """Get user email."""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def status_display(self, obj):
        """Display status with color."""
        colors = {
            'pending': 'orange',
            'syncing': 'blue',
            'completed': 'green',
            'failed': 'red'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    actions = ['mark_as_pending', 'mark_as_completed']
    
    def mark_as_pending(self, request, queryset):
        """Mark selected items as pending."""
        updated = queryset.update(
            status='pending',
            error_message=''
        )
        self.message_user(
            request,
            f"{updated} items marked as pending."
        )
    mark_as_pending.short_description = "Mark selected as pending"
    
    def mark_as_completed(self, request, queryset):
        """Mark selected items as completed."""
        updated = queryset.update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(
            request,
            f"{updated} items marked as completed."
        )
    mark_as_completed.short_description = "Mark selected as completed"


@admin.register(OfflineLog)
class OfflineLogAdmin(admin.ModelAdmin):
    """Admin for offline logs."""
    
    list_display = [
        'user_email', 'log_type_display', 'message_preview',
        'created_at'
    ]
    list_filter = ['log_type', 'created_at']
    search_fields = ['user__email', 'message']
    raw_id_fields = ['user']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Log Details', {
            'fields': (
                'log_type',
                'message',
                'metadata'
            )
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        })
    )
    
    readonly_fields = ['created_at']
    
    def user_email(self, obj):
        """Get user email."""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def log_type_display(self, obj):
        """Display log type with icon."""
        icons = {
            'sync_start': '🔄',
            'sync_complete': '✅',
            'sync_error': '❌',
            'cache_hit': '✓',
            'cache_miss': '✗',
            'cache_expired': '⏰',
            'cache_cleared': '🗑️',
            'offline_action': '📱'
        }
        icon = icons.get(obj.log_type, '•')
        return format_html(
            '{} {}',
            icon,
            obj.get_log_type_display()
        )
    log_type_display.short_description = 'Type'
    
    def message_preview(self, obj):
        """Preview of message."""
        if len(obj.message) > 100:
            return obj.message[:100] + '...'
        return obj.message
    message_preview.short_description = 'Message'
