from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer
from .models import ETA, ETANotification, StopArrival


class ETASerializer(BaseModelSerializer):
    line_name = serializers.CharField(source='line.name', read_only=True)
    bus_matricule = serializers.CharField(source='bus.matricule', read_only=True)
    stop_name = serializers.CharField(source='stop.name', read_only=True)
    minutes_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = ETA
        fields = [
            'id', 'line', 'bus', 'stop', 'tracking_session',
            'estimated_arrival_time', 'actual_arrival_time', 'status',
            'delay_minutes', 'accuracy', 'metadata', 'is_active',
            'created_at', 'updated_at', 'line_name', 'bus_matricule',
            'stop_name', 'minutes_remaining'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'line_name', 'bus_matricule',
            'stop_name', 'minutes_remaining'
        ]
    
    def get_minutes_remaining(self, obj):
        from django.utils import timezone
        import math
        
        if obj.actual_arrival_time:
            return 0
        
        now = timezone.now()
        
        if now > obj.estimated_arrival_time:
            return 0
        
        delta = obj.estimated_arrival_time - now
        return math.ceil(delta.total_seconds() / 60)


class ETACreateSerializer(BaseModelSerializer):
    class Meta:
        model = ETA
        fields = [
            'line', 'bus', 'stop', 'tracking_session',
            'estimated_arrival_time', 'status', 'accuracy', 'metadata'
        ]


class ETAUpdateSerializer(BaseModelSerializer):
    class Meta:
        model = ETA
        fields = [
            'estimated_arrival_time', 'actual_arrival_time', 'status',
            'delay_minutes', 'accuracy', 'metadata'
        ]


class ETANotificationSerializer(BaseModelSerializer):
    eta_details = ETASerializer(source='eta', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = ETANotification
        fields = [
            'id', 'eta', 'user', 'notification_threshold', 'sent_at',
            'is_sent', 'notification_type', 'notification_id', 'is_active',
            'created_at', 'updated_at', 'eta_details', 'user_email'
        ]
        read_only_fields = [
            'id', 'sent_at', 'is_sent', 'notification_id', 'created_at',
            'updated_at', 'eta_details', 'user_email'
        ]


class ETANotificationCreateSerializer(BaseModelSerializer):
    class Meta:
        model = ETANotification
        fields = [
            'eta', 'user', 'notification_threshold', 'notification_type'
        ]


class StopArrivalSerializer(BaseModelSerializer):
    line_name = serializers.CharField(source='line.name', read_only=True)
    bus_matricule = serializers.CharField(source='bus.matricule', read_only=True)
    stop_name = serializers.CharField(source='stop.name', read_only=True)
    
    class Meta:
        model = StopArrival
        fields = [
            'id', 'tracking_session', 'line', 'stop', 'bus',
            'arrival_time', 'departure_time', 'scheduled_arrival_time',
            'delay_minutes', 'is_active', 'created_at', 'updated_at',
            'line_name', 'bus_matricule', 'stop_name'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'line_name', 'bus_matricule',
            'stop_name'
        ]


class StopArrivalCreateSerializer(BaseModelSerializer):
    class Meta:
        model = StopArrival
        fields = [
            'tracking_session', 'line', 'stop', 'bus',
            'arrival_time', 'departure_time', 'scheduled_arrival_time',
            'delay_minutes'
        ]


class NextArrivalSerializer(serializers.Serializer):
    eta_id = serializers.UUIDField()
    line_id = serializers.UUIDField()
    line_name = serializers.CharField()
    bus_id = serializers.UUIDField()
    bus_matricule = serializers.CharField()
    stop_id = serializers.UUIDField()
    stop_name = serializers.CharField()
    estimated_arrival_time = serializers.DateTimeField()
    minutes_remaining = serializers.IntegerField()
    status = serializers.CharField()
    delay_minutes = serializers.IntegerField()
    tracking_session_id = serializers.UUIDField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, allow_null=True)
    last_update = serializers.DateTimeField(allow_null=True)