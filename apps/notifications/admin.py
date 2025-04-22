from django.contrib import admin
from .models import Notification, NotificationPreference, PushToken, NotificationLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'title', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'is_active', 'created_at')
    search_fields = ('title', 'message', 'user__email')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'notification_type', 'push_enabled', 'email_enabled', 'sms_enabled')
    list_filter = ('notification_type', 'push_enabled', 'email_enabled', 'sms_enabled')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)


@admin.register(PushToken)
class PushTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'device_type', 'device_name', 'is_active', 'last_used')
    list_filter = ('device_type', 'is_active')
    search_fields = ('user__email', 'device_name')
    raw_id_fields = ('user',)
    date_hierarchy = 'last_used'


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'notification', 'method', 'success', 'created_at')
    list_filter = ('method', 'success', 'created_at')
    search_fields = ('notification__title', 'error_message')
    raw_id_fields = ('notification',)
    date_hierarchy = 'created_at'
