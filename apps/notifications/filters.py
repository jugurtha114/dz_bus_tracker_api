"""
Filters for the notifications app.
"""
import django_filters
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from apps.core.constants import NOTIFICATION_TYPE_CHOICES, NOTIFICATION_CHANNEL_CHOICES
from .models import Notification, NotificationPreference, NotificationSchedule


class NotificationFilter(django_filters.FilterSet):
    """
    Filter for notifications.
    """
    notification_type = django_filters.MultipleChoiceFilter(
        choices=NOTIFICATION_TYPE_CHOICES,
        help_text=_("Filter by notification type")
    )
    
    channel = django_filters.MultipleChoiceFilter(
        choices=NOTIFICATION_CHANNEL_CHOICES,
        help_text=_("Filter by notification channel")
    )
    
    is_read = django_filters.BooleanFilter(
        help_text=_("Filter by read status")
    )
    
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text=_("Filter notifications created after this date")
    )
    
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text=_("Filter notifications created before this date")
    )
    
    search = django_filters.CharFilter(
        method='search_filter',
        help_text=_("Search in title and message")
    )
    
    def search_filter(self, queryset, name, value):
        """Search in title and message."""
        return queryset.filter(
            Q(title__icontains=value) |
            Q(message__icontains=value)
        )
    
    class Meta:
        model = Notification
        fields = ['notification_type', 'channel', 'is_read']