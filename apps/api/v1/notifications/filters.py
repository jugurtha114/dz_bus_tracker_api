"""
Filters for the notifications API.
"""
from django_filters import rest_framework as filters

from apps.api.filters import BaseFilterSet, SearchFilterMixin
from apps.notifications.models import DeviceToken, Notification


class NotificationFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for notifications.
    """
    user_id = filters.UUIDFilter(field_name='user__id')
    notification_type = filters.CharFilter(field_name='notification_type')
    channel = filters.CharFilter(field_name='channel')
    is_read = filters.BooleanFilter(field_name='is_read')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')
    read_after = filters.IsoDateTimeFilter(field_name='read_at', lookup_expr='gte')
    read_before = filters.IsoDateTimeFilter(field_name='read_at', lookup_expr='lte')

    class Meta:
        model = Notification
        fields = [
            'user_id', 'notification_type', 'channel', 'is_read',
            'created_after', 'created_before', 'read_after', 'read_before',
        ]
        search_fields = ['title', 'message']


class DeviceTokenFilter(BaseFilterSet):
    """
    Filter for device tokens.
    """
    user_id = filters.UUIDFilter(field_name='user__id')
    device_type = filters.CharFilter(field_name='device_type')
    is_active = filters.BooleanFilter(field_name='is_active')
    created_after = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = DeviceToken
        fields = [
            'user_id', 'device_type', 'is_active',
            'created_after', 'created_before',
        ]