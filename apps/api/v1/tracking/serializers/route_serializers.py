"""
Serializers for route and tracking visualization.
"""
from rest_framework import serializers
from apps.tracking.models import RouteSegment
from apps.lines.models import Stop
from apps.buses.models import Bus


class StopLocationSerializer(serializers.Serializer):
    """Serializer for stop location data."""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    location = serializers.DictField(read_only=True)
    order = serializers.IntegerField(read_only=True)
    estimated_arrival = serializers.DateTimeField(read_only=True, allow_null=True)
    distance_km = serializers.FloatField(read_only=True, allow_null=True)
    travel_time_minutes = serializers.IntegerField(read_only=True, allow_null=True)


class CurrentLocationSerializer(serializers.Serializer):
    """Serializer for current location data."""
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    speed = serializers.FloatField(allow_null=True)
    heading = serializers.FloatField(allow_null=True)
    timestamp = serializers.DateTimeField()
    accuracy = serializers.FloatField(allow_null=True)


class TripInfoSerializer(serializers.Serializer):
    """Serializer for trip information."""
    id = serializers.UUIDField()
    line = serializers.CharField()
    started_at = serializers.DateTimeField()
    progress = serializers.FloatField()


class PathSegmentSerializer(serializers.Serializer):
    """Serializer for path segments."""
    from_location = serializers.DictField()
    to = serializers.DictField()
    distance = serializers.FloatField()
    estimated_duration = serializers.IntegerField()
    estimated_arrival = serializers.DateTimeField()


class TrafficConditionSerializer(serializers.Serializer):
    """Serializer for traffic conditions."""
    level = serializers.CharField()
    factor = serializers.FloatField()
    description = serializers.CharField()


class BusRouteSerializer(serializers.Serializer):
    """Main serializer for bus route estimation."""
    bus_id = serializers.UUIDField()
    bus_number = serializers.CharField()
    driver = serializers.DictField(allow_null=True)
    current_location = CurrentLocationSerializer()
    trip = TripInfoSerializer(allow_null=True)
    estimated_path = PathSegmentSerializer(many=True)
    remaining_stops = StopLocationSerializer(many=True)
    historical_data = serializers.DictField()
    traffic_conditions = TrafficConditionSerializer()
    status = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


class BusArrivalEstimateSerializer(serializers.Serializer):
    """Serializer for bus arrival estimates."""
    bus = serializers.DictField()
    driver = serializers.DictField(allow_null=True)
    line = serializers.DictField()
    current_location = serializers.DictField()
    eta = serializers.DateTimeField()
    eta_minutes = serializers.IntegerField()
    reliability = serializers.FloatField()
    last_update = serializers.DateTimeField()


class RouteVisualizationSerializer(serializers.Serializer):
    """Serializer for route visualization data."""
    line = serializers.DictField()
    route = serializers.DictField()
    markers = serializers.ListField()
    active_buses = serializers.ListField()
    bounds = serializers.DictField(allow_null=True)
    last_updated = serializers.DateTimeField()


class RouteSegmentSerializer(serializers.ModelSerializer):
    """Serializer for route segments."""
    from_stop_name = serializers.CharField(source='from_stop.name', read_only=True)
    to_stop_name = serializers.CharField(source='to_stop.name', read_only=True)
    
    class Meta:
        model = RouteSegment
        fields = [
            'id', 'from_stop', 'from_stop_name', 'to_stop', 
            'to_stop_name', 'polyline', 'distance', 'duration'
        ]


class EstimateArrivalRequestSerializer(serializers.Serializer):
    """Request serializer for arrival estimation."""
    stop_id = serializers.UUIDField()
    line_id = serializers.UUIDField(required=False, allow_null=True)