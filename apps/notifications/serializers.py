from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from .models import Notification, NotificationPreference, PushToken, NotificationLog


class NotificationSerializer(BaseModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'type', 'title', 'message', 'data',
            'is_read', 'read_at', 'sent_via_push', 'sent_via_email',
            'sent_via_sms', 'is_action_required', 'action_url',
            'expiration_date', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationListSerializer(BaseModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'title', 'message', 'is_read', 'created_at',
            'is_action_required', 'action_url'
        ]
        read_only_fields = ['id', 'created_at']


class NotificationCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'user', 'type', 'title', 'message', 'data',
            'is_action_required', 'action_url', 'expiration_date'
        ]


class NotificationPreferenceSerializer(BaseModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'notification_type', 'push_enabled',
            'email_enabled', 'sms_enabled', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationPreferenceUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ['push_enabled', 'email_enabled', 'sms_enabled']


class PushTokenSerializer(BaseModelSerializer):
    class Meta:
        model = PushToken
        fields = [
            'id', 'user', 'token', 'device_type', 'device_name',
            'last_used', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_used', 'created_at', 'updated_at']


class PushTokenCreateSerializer(BaseModelSerializer):
    class Meta:
        model = PushToken
        fields = ['token', 'device_type', 'device_name']


class NotificationLogSerializer(BaseModelSerializer):
    notification_title = serializers.CharField(source='notification.title', read_only=True)
    
    class Meta:
        model = NotificationLog
        fields = [
            'id', 'notification', 'method', 'success', 'error_message',
            'provider_response', 'created_at', 'notification_title'
        ]
        read_only_fields = ['id', 'created_at', 'notification_title']


class BulkNotificationSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), required=True)
    type = serializers.CharField(required=True)
    title = serializers.CharField(required=True)
    message = serializers.CharField(required=True)
    data = serializers.JSONField(required=False, default=dict)
    is_action_required = serializers.BooleanField(required=False, default=False)
    action_url = serializers.CharField(required=False, allow_blank=True)
    expiration_date = serializers.DateTimeField(required=False, allow_null=True)
    send_push = serializers.BooleanField(required=False, default=True)
    send_email = serializers.BooleanField(required=False, default=False)
    send_sms = serializers.BooleanField(required=False, default=False)


class MarkAsReadSerializer(serializers.Serializer):
    notification_ids = serializers.ListField(child=serializers.UUIDField(), required=True)
