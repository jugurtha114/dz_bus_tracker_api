"""
Filters for the tracking API.
"""
from django_filters import rest_framework as filters

from apps.api.filters import BaseFilterSet, GeoLocationFilterMixin, SearchFilterMixin
from apps.tracking.models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)


class BusLineFilter(BaseFilterSet):
    """
    Filter for bus-line assignments.
    """
    bus_id = filters.UUIDFilter(field_name='bus__id')
    line_id = filters.UUIDFilter(field_name='line__id')
    tracking_status = filters.CharFilter(field_name='tracking_status')
    is_active = filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = BusLine
        fields = ['bus_id', 'line_id', 'tracking_status', 'is_active']


class LocationUpdateFilter(BaseFilterSet, GeoLocationFilterMixin):
    """
    Filter for location updates.
    """
    bus_id = filters.UUIDFilter(field_name='bus__id')
    line_id = filters.UUIDFilter(field_name='line__id')
    trip_id = filters.UUIDFilter(field_name='trip_id')
    nearest_stop_id = filters.UUIDFilter(field_name='nearest_stop__id')
    min_speed = filters.NumberFilter(field_name='speed', lookup_expr='gte')
    max_speed = filters.NumberFilter(field_name='speed', lookup_expr='lte')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = LocationUpdate
        fields = [
            'bus_id', 'line_id', 'trip_id', 'nearest_stop_id',
            'min_speed', 'max_speed', 'created_after', 'created_before',
        ]


class PassengerCountFilter(BaseFilterSet):
    """
    Filter for passenger counts.
    """
    bus_id = filters.UUIDFilter(field_name='bus__id')
    line_id = filters.UUIDFilter(field_name='line__id')
    trip_id = filters.UUIDFilter(field_name='trip_id')
    stop_id = filters.UUIDFilter(field_name='stop__id')
    min_count = filters.NumberFilter(field_name='count', lookup_expr='gte')
    max_count = filters.NumberFilter(field_name='count', lookup_expr='lte')
    min_occupancy = filters.NumberFilter(field_name='occupancy_rate', lookup_expr='gte')
    max_occupancy = filters.NumberFilter(field_name='occupancy_rate', lookup_expr='lte')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = PassengerCount
        fields = [
            'bus_id', 'line_id', 'trip_id', 'stop_id',
            'min_count', 'max_count', 'min_occupancy', 'max_occupancy',
            'created_after', 'created_before',
        ]


class WaitingPassengersFilter(BaseFilterSet):
    """
    Filter for waiting passengers.
    """
    stop_id = filters.UUIDFilter(field_name='stop__id')
    line_id = filters.UUIDFilter(field_name='line__id')
    reported_by_id = filters.UUIDFilter(field_name='reported_by__id')
    min_count = filters.NumberFilter(field_name='count', lookup_expr='gte')
    max_count = filters.NumberFilter(field_name='count', lookup_expr='lte')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = WaitingPassengers
        fields = [
            'stop_id', 'line_id', 'reported_by_id',
            'min_count', 'max_count',
            'created_after', 'created_before',
        ]


class TripFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for trips.
    """
    bus_id = filters.UUIDFilter(field_name='bus__id')
    driver_id = filters.UUIDFilter(field_name='driver__id')
    line_id = filters.UUIDFilter(field_name='line__id')
    start_stop_id = filters.UUIDFilter(field_name='start_stop__id')
    end_stop_id = filters.UUIDFilter(field_name='end_stop__id')
    is_completed = filters.BooleanFilter(field_name='is_completed')
    start_time_after = filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='gte')
    start_time_before = filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='lte')
    end_time_after = filters.IsoDateTimeFilter(field_name='end_time', lookup_expr='gte')
    end_time_before = filters.IsoDateTimeFilter(field_name='end_time', lookup_expr='lte')
    min_distance = filters.NumberFilter(field_name='distance', lookup_expr='gte')
    max_distance = filters.NumberFilter(field_name='distance', lookup_expr='lte')

    class Meta:
        model = Trip
        fields = [
            'bus_id', 'driver_id', 'line_id', 'start_stop_id', 'end_stop_id',
            'is_completed', 'start_time_after', 'start_time_before',
            'end_time_after', 'end_time_before', 'min_distance', 'max_distance',
        ]
        search_fields = ['notes']


class AnomalyFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for anomalies.
    """
    bus_id = filters.UUIDFilter(field_name='bus__id')
    trip_id = filters.UUIDFilter(field_name='trip__id')
    type = filters.CharFilter(field_name='type')
    severity = filters.CharFilter(field_name='severity')
    resolved = filters.BooleanFilter(field_name='resolved')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')
    resolved_after = filters.IsoDateTimeFilter(field_name='resolved_at', lookup_expr='gte')
    resolved_before = filters.IsoDateTimeFilter(field_name='resolved_at', lookup_expr='lte')

    class Meta:
        model = Anomaly
        fields = [
            'bus_id', 'trip_id', 'type', 'severity', 'resolved',
            'created_after', 'created_before',
            'resolved_after', 'resolved_before',
        ]
        search_fields = ['description', 'resolution_notes']