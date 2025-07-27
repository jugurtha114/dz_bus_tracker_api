"""
Serializers for the notifications app.
"""
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.api.v1.accounts.serializers import UserBriefSerializer
from apps.api.v1.buses.serializers import BusBriefSerializer
from apps.api.v1.lines.serializers import LineBriefSerializer, StopBriefSerializer
from apps.api.v1.tracking.serializers import TripBriefSerializer
from .models import DeviceToken, Notification, NotificationPreference, NotificationSchedule


class DeviceTokenSerializer(serializers.ModelSerializer):
    """
    Serializer for DeviceToken model.
    """
    class Meta:
        model = DeviceToken
        fields = ['id', 'token', 'device_type', 'is_active', 'last_used', 'created_at']
        read_only_fields = ['id', 'last_used', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model.
    """
    user = UserBriefSerializer(read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'title', 'message',
            'channel', 'is_read', 'read_at', 'data', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating notifications.
    """
    class Meta:
        model = Notification
        fields = ['notification_type', 'title', 'message', 'channel', 'data']


class NotificationMarkReadSerializer(serializers.Serializer):
    """
    Serializer for marking notifications as read.
    """
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text=_("List of notification IDs to mark as read. If empty, marks all as read.")
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationPreference model.
    """
    favorite_stops = StopBriefSerializer(many=True, read_only=True)
    favorite_lines = LineBriefSerializer(many=True, read_only=True)
    favorite_stop_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    favorite_line_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'notification_type', 'channels', 'enabled',
            'minutes_before_arrival', 'quiet_hours_start', 'quiet_hours_end',
            'favorite_stops', 'favorite_lines',
            'favorite_stop_ids', 'favorite_line_ids',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_channels(self, value):
        """Validate notification channels."""
        from apps.core.constants import NOTIFICATION_CHANNEL_CHOICES
        valid_channels = [choice[0] for choice in NOTIFICATION_CHANNEL_CHOICES]
        
        for channel in value:
            if channel not in valid_channels:
                raise serializers.ValidationError(
                    f"Invalid channel: {channel}. Valid choices are: {', '.join(valid_channels)}"
                )
        
        return value
    
    def validate_quiet_hours_start(self, value):
        """Validate quiet hours start time."""
        if value and self.initial_data.get('quiet_hours_end'):
            # Validation will be done in validate() method
            pass
        return value
    
    def validate(self, attrs):
        """Validate the preference data."""
        quiet_start = attrs.get('quiet_hours_start')
        quiet_end = attrs.get('quiet_hours_end')
        
        if quiet_start and quiet_end:
            # Allow overnight quiet hours (e.g., 22:00 to 07:00)
            pass  # No validation needed, handled in service
        elif quiet_start or quiet_end:
            raise serializers.ValidationError(
                "Both quiet_hours_start and quiet_hours_end must be provided together."
            )
        
        return attrs


class NotificationScheduleSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationSchedule model.
    """
    user = UserBriefSerializer(read_only=True)
    bus = BusBriefSerializer(read_only=True)
    stop = StopBriefSerializer(read_only=True)
    line = LineBriefSerializer(read_only=True)
    trip = TripBriefSerializer(read_only=True)
    
    class Meta:
        model = NotificationSchedule
        fields = [
            'id', 'user', 'notification_type', 'scheduled_for',
            'title', 'message', 'channels', 'data',
            'bus', 'stop', 'line', 'trip',
            'is_sent', 'sent_at', 'error',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'bus', 'stop', 'line', 'trip',
            'is_sent', 'sent_at', 'error',
            'created_at', 'updated_at'
        ]


class DeviceTokenCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating device tokens.
    """
    device_info = serializers.JSONField(required=False)
    app_version = serializers.CharField(required=False)
    
    class Meta:
        model = DeviceToken
        fields = ['token', 'device_type', 'device_info', 'app_version']


class DeviceTokenTestSerializer(serializers.Serializer):
    """
    Serializer for testing device tokens.
    """
    message = serializers.CharField(default="Test notification")


class NotificationSendSerializer(serializers.Serializer):
    """
    Serializer for sending notifications.
    """
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text=_("List of user IDs to send notification to")
    )
    template_type = serializers.CharField(help_text=_("Template type"))
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text=_("Notification channels")
    )
    template_data = serializers.JSONField(
        required=False,
        help_text=_("Data for template rendering")
    )


class BulkNotificationSerializer(serializers.Serializer):
    """
    Serializer for bulk notifications.
    """
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text=_("List of user IDs")
    )
    template_type = serializers.CharField(help_text=_("Template type"))
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text=_("Notification channels")
    )
    template_data = serializers.JSONField(
        required=False,
        help_text=_("Template data")
    )


class ArrivalNotificationSerializer(serializers.Serializer):
    """
    Serializer for scheduling arrival notifications.
    """
    bus_id = serializers.UUIDField(help_text=_("ID of the bus"))
    stop_id = serializers.UUIDField(help_text=_("ID of the stop"))
    estimated_arrival = serializers.DateTimeField(help_text=_("Estimated arrival time"))
    trip_id = serializers.UUIDField(required=False, help_text=_("ID of the trip"))


class DelayNotificationSerializer(serializers.Serializer):
    """
    Serializer for sending delay notifications.
    """
    bus_id = serializers.UUIDField(help_text=_("ID of the bus"))
    line_id = serializers.UUIDField(help_text=_("ID of the line"))
    delay_minutes = serializers.IntegerField(
        min_value=1,
        help_text=_("Delay in minutes")
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=_("Reason for the delay")
    )