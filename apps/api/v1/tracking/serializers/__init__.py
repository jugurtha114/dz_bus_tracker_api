"""
Serializers for the tracking API.
"""
from rest_framework import serializers

from apps.api.serializers import BaseSerializer
from apps.api.v1.buses.serializers import BusSerializer
from apps.api.v1.drivers.serializers import DriverSerializer
from apps.api.v1.lines.serializers import LineSerializer, StopSerializer
from apps.tracking.models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)


class BusLineSerializer(BaseSerializer):
    """
    Serializer for bus-line assignments.
    """
    bus_details = serializers.SerializerMethodField(read_only=True)
    line_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BusLine
        fields = [
            'id', 'bus', 'bus_details', 'line', 'line_details',
            'is_active', 'tracking_status', 'trip_id', 'start_time',
            'end_time', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_bus_details(self, obj):
        """
        Get bus details if expand_bus is True.
        """
        expand = self.context.get('request').query_params.get('expand_bus', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return BusSerializer(obj.bus).data
        return None

    def get_line_details(self, obj):
        """
        Get line details if expand_line is True.
        """
        expand = self.context.get('request').query_params.get('expand_line', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return LineSerializer(obj.line).data
        return None


class BusLineCreateSerializer(BaseSerializer):
    """
    Serializer for creating bus-line assignments.
    """
    class Meta:
        model = BusLine
        fields = ['bus', 'line']


class LocationUpdateSerializer(BaseSerializer):
    """
    Serializer for location updates.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'id', 'bus', 'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy', 'trip_id', 'nearest_stop',
            'distance_to_stop', 'line', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LocationUpdateCreateSerializer(BaseSerializer):
    """
    Serializer for creating location updates.
    """
    class Meta:
        model = LocationUpdate
        fields = [
            'latitude', 'longitude', 'altitude', 'speed',
            'heading', 'accuracy',
        ]


class PassengerCountSerializer(BaseSerializer):
    """
    Serializer for passenger counts.
    """
    class Meta:
        model = PassengerCount
        fields = [
            'id', 'bus', 'count', 'capacity', 'occupancy_rate',
            'trip_id', 'stop', 'line', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'occupancy_rate']


class PassengerCountCreateSerializer(BaseSerializer):
    """
    Serializer for creating passenger counts.
    """
    class Meta:
        model = PassengerCount
        fields = ['count', 'stop']


class WaitingPassengersSerializer(BaseSerializer):
    """
    Serializer for waiting passengers.
    """
    stop_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = WaitingPassengers
        fields = [
            'id', 'stop', 'stop_details', 'line', 'count',
            'reported_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_stop_details(self, obj):
        """
        Get stop details if expand_stop is True.
        """
        expand = self.context.get('request').query_params.get('expand_stop', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return StopSerializer(obj.stop).data
        return None


class WaitingPassengersCreateSerializer(BaseSerializer):
    """
    Serializer for creating waiting passengers.
    """
    class Meta:
        model = WaitingPassengers
        fields = ['stop', 'line', 'count']


class TripSerializer(BaseSerializer):
    """
    Serializer for trips.
    """
    bus_details = serializers.SerializerMethodField(read_only=True)
    driver_details = serializers.SerializerMethodField(read_only=True)
    line_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'bus', 'bus_details', 'driver', 'driver_details',
            'line', 'line_details', 'start_time', 'end_time',
            'start_stop', 'end_stop', 'is_completed', 'distance',
            'average_speed', 'max_passengers', 'total_stops',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'is_completed', 'distance', 'average_speed',
            'max_passengers', 'total_stops', 'created_at', 'updated_at',
        ]

    def get_bus_details(self, obj):
        """
        Get bus details if expand_bus is True.
        """
        expand = self.context.get('request').query_params.get('expand_bus', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return BusSerializer(obj.bus).data
        return None

    def get_driver_details(self, obj):
        """
        Get driver details if expand_driver is True.
        """
        expand = self.context.get('request').query_params.get('expand_driver', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return DriverSerializer(obj.driver).data
        return None

    def get_line_details(self, obj):
        """
        Get line details if expand_line is True.
        """
        expand = self.context.get('request').query_params.get('expand_line', False)
        if expand and expand.lower() in ['true', '1', 'yes']:
            return LineSerializer(obj.line).data
        return None


class TripCreateSerializer(BaseSerializer):
    """
    Serializer for creating trips.
    """
    class Meta:
        model = Trip
        fields = [
            'bus', 'driver', 'line', 'start_time',
            'start_stop', 'notes',
        ]


class TripUpdateSerializer(BaseSerializer):
    """
    Serializer for updating trips.
    """
    class Meta:
        model = Trip
        fields = [
            'end_time', 'end_stop', 'notes',
        ]


class AnomalySerializer(BaseSerializer):
    """
    Serializer for anomalies.
    """
    class Meta:
        model = Anomaly
        fields = [
            'id', 'bus', 'trip', 'type', 'description', 'severity',
            'location_latitude', 'location_longitude', 'resolved',
            'resolved_at', 'resolution_notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AnomalyCreateSerializer(BaseSerializer):
    """
    Serializer for creating anomalies.
    """
    class Meta:
        model = Anomaly
        fields = [
            'type', 'description', 'severity',
            'location_latitude', 'location_longitude',
        ]


class AnomalyResolveSerializer(serializers.Serializer):
    """
    Serializer for resolving anomalies.
    """
    resolution_notes = serializers.CharField(required=False, allow_blank=True)


class StartTrackingSerializer(serializers.Serializer):
    """
    Serializer for starting tracking.
    """
    line_id = serializers.UUIDField(required=True)


class StopTrackingSerializer(serializers.Serializer):
    """
    Serializer for stopping tracking.
    """
    pass


class EstimateArrivalTimeSerializer(serializers.Serializer):
    """
    Serializer for estimating arrival time.
    """
    stop_id = serializers.UUIDField(required=True)


class TripBriefSerializer(BaseSerializer):
    """
    Brief serializer for trips.
    """
    bus_number = serializers.CharField(source='bus.bus_number', read_only=True)
    line_name = serializers.CharField(source='line.name', read_only=True)
    
    class Meta:
        model = Trip
        fields = ['id', 'bus_number', 'line_name', 'start_time', 'end_time']