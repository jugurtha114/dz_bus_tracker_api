"""
Filters for the drivers API.
"""
from django_filters import rest_framework as filters

from apps.api.filters import BaseFilterSet, SearchFilterMixin
from apps.drivers.models import Driver, DriverRating


class DriverFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for drivers.
    """
    user_id = filters.UUIDFilter(field_name='user__id')
    status = filters.CharFilter(field_name='status')
    is_active = filters.BooleanFilter(field_name='is_active')
    is_available = filters.BooleanFilter(field_name='is_available')
    min_rating = filters.NumberFilter(field_name='rating', lookup_expr='gte')
    max_rating = filters.NumberFilter(field_name='rating', lookup_expr='lte')
    min_experience = filters.NumberFilter(field_name='years_of_experience', lookup_expr='gte')

    class Meta:
        model = Driver
        fields = [
            'user_id', 'status', 'is_active', 'is_available',
            'min_rating', 'max_rating', 'min_experience',
        ]
        search_fields = [
            'user__email', 'user__first_name', 'user__last_name',
            'phone_number', 'id_card_number', 'driver_license_number',
        ]


class DriverRatingFilter(BaseFilterSet):
    """
    Filter for driver ratings.
    """
    driver_id = filters.UUIDFilter(field_name='driver__id')
    user_id = filters.UUIDFilter(field_name='user__id')
    min_rating = filters.NumberFilter(field_name='rating', lookup_expr='gte')
    max_rating = filters.NumberFilter(field_name='rating', lookup_expr='lte')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = DriverRating
        fields = [
            'driver_id', 'user_id', 'min_rating', 'max_rating',
            'created_after', 'created_before',
        ]