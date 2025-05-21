"""
Base filters for DZ Bus Tracker API.
"""
from django.db.models import Q
from django_filters import rest_framework as filters
from django_filters.filters import BaseInFilter, CharFilter, NumberFilter, DateTimeFilter


class NumberInFilter(BaseInFilter, NumberFilter):
    """
    Filter for multiple numeric values (comma-separated).
    """
    pass


class CharInFilter(BaseInFilter, CharFilter):
    """
    Filter for multiple string values (comma-separated).
    """
    pass


class BaseFilterSet(filters.FilterSet):
    """
    Base filter set with common functionality.
    """
    order_by = filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('updated_at', 'updated_at'),
        ),
    )


class SearchFilterMixin:
    """
    Mixin for adding search functionality to a filter set.
    """
    search = CharFilter(method='filter_search')

    def filter_search(self, queryset, name, value):
        """
        Filter by search term across multiple fields.
        """
        if not value:
            return queryset

        search_fields = getattr(self.Meta, 'search_fields', [])
        if not search_fields:
            return queryset

        q_objects = Q()
        for field in search_fields:
            q_objects |= Q(**{f"{field}__icontains": value})

        return queryset.filter(q_objects)


class GeoLocationFilterMixin:
    """
    Mixin for filtering by geographic proximity.
    """
    latitude = filters.NumberFilter(method='filter_location')
    longitude = filters.NumberFilter(method='filter_location')
    radius = filters.NumberFilter(method='filter_location')

    def filter_location(self, queryset, name, value):
        """
        Filter by geographic location within a radius.
        """
        # Only apply filter if all parameters are present
        if not all([
            self.data.get('latitude'),
            self.data.get('longitude'),
            self.data.get('radius')
        ]):
            return queryset

        # Get parameters
        latitude = float(self.data.get('latitude'))
        longitude = float(self.data.get('longitude'))
        radius = float(self.data.get('radius'))  # in kilometers

        # Use raw SQL for performance with standard DB
        # In production, you would use PostGIS's functions
        # This is a simplification that works with non-geo databases
        from django.db.models import F, Func

        # Haversine formula parameters
        earth_radius = 6371  # kilometers

        # Convert lat/lon to radians
        lat_rad = latitude * 3.14159 / 180
        lon_rad = longitude * 3.14159 / 180

        # Calculate distance using the Haversine formula
        queryset = queryset.annotate(
            distance=Func(
                earth_radius * 2 * Func(
                    Func(
                        Func(
                            (F('latitude') * 3.14159 / 180 - lat_rad) / 2,
                            function='SIN'
                        ) * Func(
                            (F('latitude') * 3.14159 / 180 - lat_rad) / 2,
                            function='SIN'
                        ) +
                        Func(lat_rad, function='COS') *
                        Func(F('latitude') * 3.14159 / 180, function='COS') *
                        Func(
                            (F('longitude') * 3.14159 / 180 - lon_rad) / 2,
                            function='SIN'
                        ) * Func(
                            (F('longitude') * 3.14159 / 180 - lon_rad) / 2,
                            function='SIN'
                        ),
                        function='SQRT'
                    ),
                    function='ASIN'
                ),
                function='*'
            )
        ).filter(distance__lte=radius)

        return queryset


class DateRangeFilterMixin:
    """
    Mixin for filtering by date range.
    """
    created_after = DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = DateTimeFilter(field_name='created_at', lookup_expr='lte')
    updated_after = DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_before = DateTimeFilter(field_name='updated_at', lookup_expr='lte')


class StatusFilterMixin:
    """
    Mixin for filtering by status field.
    """
    status = CharInFilter(field_name='status', lookup_expr='in')
    is_active = filters.BooleanFilter(field_name='is_active')