"""
Filters for the lines API.
"""
from django_filters import rest_framework as filters

from apps.api.filters import BaseFilterSet, GeoLocationFilterMixin, SearchFilterMixin
from apps.lines.models import Line, Schedule, Stop


class StopFilter(BaseFilterSet, SearchFilterMixin, GeoLocationFilterMixin):
    """
    Filter for stops.
    """
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    is_active = filters.BooleanFilter(field_name='is_active')
    line_id = filters.UUIDFilter(field_name='lines__id')

    class Meta:
        model = Stop
        fields = ['name', 'is_active', 'line_id']
        search_fields = ['name', 'address', 'description']


class LineFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for lines.
    """
    code = filters.CharFilter(field_name='code', lookup_expr='icontains')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    is_active = filters.BooleanFilter(field_name='is_active')
    stop_id = filters.UUIDFilter(field_name='stops__id')
    min_frequency = filters.NumberFilter(field_name='frequency', lookup_expr='gte')
    max_frequency = filters.NumberFilter(field_name='frequency', lookup_expr='lte')

    class Meta:
        model = Line
        fields = ['code', 'name', 'is_active', 'stop_id', 'min_frequency', 'max_frequency']
        search_fields = ['code', 'name', 'description']


class ScheduleFilter(BaseFilterSet):
    """
    Filter for schedules.
    """
    line_id = filters.UUIDFilter(field_name='line__id')
    day_of_week = filters.NumberFilter(field_name='day_of_week')
    is_active = filters.BooleanFilter(field_name='is_active')
    min_frequency = filters.NumberFilter(field_name='frequency_minutes', lookup_expr='gte')
    max_frequency = filters.NumberFilter(field_name='frequency_minutes', lookup_expr='lte')

    class Meta:
        model = Schedule
        fields = ['line_id', 'day_of_week', 'is_active', 'min_frequency', 'max_frequency']