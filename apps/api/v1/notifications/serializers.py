"""
Serializers for the notifications API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.notifications.models import DeviceToken, Notification


class NotificationSerializer(BaseSerializer):
    """
    Serializer for notifications.
    """
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'title', 'message',
            'channel', 'is_read', 'read_at', 'data',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationCreateSerializer(BaseSerializer):
    """
    Serializer for creating notifications.
    """
    class Meta:
        model = Notification
        fields = [
            'user', 'notification_type', 'title', 'message',
            'channel', 'data',
        ]


class DeviceTokenSerializer(BaseSerializer):
    """
    Serializer for device tokens.
    """
    class Meta:
        model = DeviceToken
        fields = [
            'id', 'user', 'token', 'device_type', 'is_active',
            'last_used', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'last_used', 'created_at', 'updated_at']


class DeviceTokenCreateSerializer(BaseSerializer):
    """
    Serializer for creating device tokens.
    """
    class Meta:
        model = DeviceToken
        fields = ['token', 'device_type']


class MarkAsReadSerializer(serializers.Serializer):
    """
    Serializer for marking notifications as read.
    """
    pass


class MarkAllAsReadSerializer(serializers.Serializer):
    """
    Serializer for marking all notifications as read.
    """
    pass