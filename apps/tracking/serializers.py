from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.base.serializers import BaseModelSerializer, BaseGeoSerializer
from apps.drivers.serializers import DriverSerializer
from apps.buses.serializers import BusSerializer
from apps.lines.serializers import LineSerializer
from .models import TrackingSession, LocationUpdate, TrackingLog, OfflineLocationBatch


class TrackingSessionSerializer(BaseModelSerializer):
    """
    Serializer for TrackingSession model.
    """
    driver_details = DriverSerializer(source='driver', read_only=True)
    bus_details = BusSerializer(source='bus', read_only=True)
    line_details = LineSerializer(source='line', read_only=True)
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = TrackingSession
        fields = [
            'id', 'driver', 'bus', 'line', 'schedule', 'start_time', 'end_time',
            'status', 'last_update', 'total_distance', 'metadata', 'created_at',
            'updated_at', 'duration', 'driver_details', 'bus_details', 'line_details',
        ]
        read_only_fields = [
            'id', 'start_time', 'end_time', 'last_update', 'total_distance',
            'created_at', 'updated_at', 'duration', 'driver_details', 'bus_details', 
            'line_details',
        ]
    
    def get_duration(self, obj):
        """
        Get the duration of the tracking session in seconds.
        """
        if obj.end_time:
            duration = obj.end_time - obj.start_time
        else:
            duration = timezone.now() - obj.start_time
        
        return duration.total_seconds()


class TrackingSessionCreateSerializer(BaseModelSerializer):
    """
    Serializer for creating a TrackingSession.
    """
    class Meta:
        model = TrackingSession
        fields = ['id', 'driver', 'bus', 'line', 'schedule']
        read_only_fields = ['id']
    
    def validate(self, attrs):
        """
        Validate that the driver and bus are active and verified.
        """
        driver = attrs.get('driver')
        bus = attrs.get('bus')
        
        if not driver.is_active or not driver.is_verified:
            raise serializers.ValidationError({'driver': _('Driver is not active or verified.')})
        
        if not bus.is_active or not bus.is_verified:
            raise serializers.ValidationError({'bus': _('Bus is not active or verified.')})
        
        # Check if the driver owns the bus
        if bus.driver != driver:
            raise serializers.ValidationError({'bus': _('Bus does not belong to the driver.')})
        
        # Check for active tracking sessions for this bus
        active_sessions = TrackingSession.objects.filter(
            bus=bus,
            status='active',
        ).exclude(id=self.instance.id if self.instance else None)
        
        if active_sessions.exists():
            raise serializers.ValidationError({
                'bus': _('Bus is already being tracked in another session.')
            })
        
        return attrs


class LocationUpdateSerializer(BaseGeoSerializer):
    """
    Serializer for LocationUpdate model.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'id', 'session', 'timestamp', 'latitude', 'longitude', 'accuracy',
            'speed', 'heading', 'altitude', 'distance_from_last', 'metadata',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'distance_from_last', 'created_at', 'updated_at',
        ]


class LocationUpdateCreateSerializer(BaseGeoSerializer):
    """
    Serializer for creating a LocationUpdate.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'session', 'timestamp', 'latitude', 'longitude', 'accuracy',
            'speed', 'heading', 'altitude', 'metadata',
        ]
    
    def validate(self, attrs):
        """
        Validate that the session is active.
        """
        session = attrs.get('session')
        
        if not session.is_active:
            raise serializers.ValidationError({'session': _('Tracking session is not active.')})
        
        return attrs


class BatchLocationUpdateSerializer(serializers.Serializer):
    """
    Serializer for batch location updates.
    """
    session_id = serializers.UUIDField(required=True)
    locations = serializers.ListField(
        child=serializers.DictField(),
        required=True,
    )
    
    def validate_session_id(self, value):
        """
        Validate that the session exists and is active.
        """
        try:
            session = TrackingSession.objects.get(id=value)
        except TrackingSession.DoesNotExist:
            raise serializers.ValidationError(_('Tracking session not found.'))
        
        if not session.is_active:
            raise serializers.ValidationError(_('Tracking session is not active.'))
        
        return value
    
    def validate_locations(self, value):
        """
        Validate the location data.
        """
        if not value:
            raise serializers.ValidationError(_('At least one location is required.'))
        
        required_fields = ['latitude', 'longitude', 'timestamp']
        
        for location in value:
            for field in required_fields:
                if field not in location:
                    raise serializers.ValidationError(
                        _('Each location must include {}.').format(field)
                    )
        
        return value


class OfflineLocationBatchSerializer(BaseModelSerializer):
    """
    Serializer for OfflineLocationBatch model.
    """
    class Meta:
        model = OfflineLocationBatch
        fields = [
            'id', 'driver', 'bus', 'line', 'collected_at', 'processed',
            'processed_at', 'data', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'processed', 'processed_at', 'created_at', 'updated_at',
        ]


class OfflineLocationBatchCreateSerializer(BaseModelSerializer):
    """
    Serializer for creating an OfflineLocationBatch.
    """
    class Meta:
        model = OfflineLocationBatch
        fields = ['id', 'driver', 'bus', 'line', 'data']
        read_only_fields = ['id']
    
    def validate(self, attrs):
        """
        Validate the driver, bus, and location data.
        """
        driver = attrs.get('driver')
        bus = attrs.get('bus')
        data = attrs.get('data')
        
        if not driver.is_active or not driver.is_verified:
            raise serializers.ValidationError({'driver': _('Driver is not active or verified.')})
        
        if not bus.is_active or not bus.is_verified:
            raise serializers.ValidationError({'bus': _('Bus is not active or verified.')})
        
        # Check if the driver owns the bus
        if bus.driver != driver:
            raise serializers.ValidationError({'bus': _('Bus does not belong to the driver.')})
        
        # Validate location data
        if not data or not isinstance(data, list):
            raise serializers.ValidationError({'data': _('Invalid location data format.')})
        
        required_fields = ['latitude', 'longitude', 'timestamp']
        
        for location in data:
            for field in required_fields:
                if field not in location:
                    raise serializers.ValidationError(
                        {'data': _('Each location must include {}.').format(field)}
                    )
        
        return attrs


class TrackingLogSerializer(BaseModelSerializer):
    """
    Serializer for TrackingLog model.
    """
    class Meta:
        model = TrackingLog
        fields = [
            'id', 'session', 'event_type', 'timestamp', 'message',
            'data', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CurrentLocationSerializer(serializers.Serializer):
    """
    Serializer for representing the current location of a bus.
    """
    bus_id = serializers.UUIDField()
    bus_matricule = serializers.CharField()
    driver_id = serializers.UUIDField()
    driver_name = serializers.CharField()
    line_id = serializers.UUIDField()
    line_name = serializers.CharField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    accuracy = serializers.FloatField(allow_null=True)
    speed = serializers.FloatField(allow_null=True)
    heading = serializers.FloatField(allow_null=True)
    timestamp = serializers.DateTimeField()
    session_id = serializers.UUIDField()
    session_status = serializers.CharField()
