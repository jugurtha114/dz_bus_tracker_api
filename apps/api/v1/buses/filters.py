"""
Filters for the buses API.
"""
from django_filters import rest_framework as filters

from apps.api.filters import BaseFilterSet, SearchFilterMixin
from apps.buses.models import Bus


class BusFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for buses.
    """
    driver_id = filters.UUIDFilter(field_name='driver__id')
    license_plate = filters.CharFilter(field_name='license_plate', lookup_expr='icontains')
    manufacturer = filters.CharFilter(field_name='manufacturer', lookup_expr='icontains')
    model = filters.CharFilter(field_name='model', lookup_expr='icontains')
    status = filters.CharFilter(field_name='status')
    is_active = filters.BooleanFilter(field_name='is_active')
    is_approved = filters.BooleanFilter(field_name='is_approved')
    is_air_conditioned = filters.BooleanFilter(field_name='is_air_conditioned')
    min_capacity = filters.NumberFilter(field_name='capacity', lookup_expr='gte')
    max_capacity = filters.NumberFilter(field_name='capacity', lookup_expr='lte')
    year = filters.NumberFilter(field_name='year')
    min_year = filters.NumberFilter(field_name='year', lookup_expr='gte')
    max_year = filters.NumberFilter(field_name='year', lookup_expr='lte')

    class Meta:
        model = Bus
        fields = [
            'driver_id', 'license_plate', 'manufacturer', 'model',
            'status', 'is_active', 'is_approved', 'is_air_conditioned',
            'min_capacity', 'max_capacity', 'year', 'min_year', 'max_year',
        ]
        search_fields = ['license_plate', 'manufacturer', 'model', 'description']
