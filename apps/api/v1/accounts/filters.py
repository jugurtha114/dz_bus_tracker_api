"""
Filters for the accounts API.
"""
from django_filters import rest_framework as filters

from apps.accounts.models import User, Profile
from apps.api.filters import BaseFilterSet, SearchFilterMixin


class UserFilter(BaseFilterSet, SearchFilterMixin):
    """
    Filter for users.
    """
    user_type = filters.CharFilter(field_name='user_type')
    is_active = filters.BooleanFilter(field_name='is_active')
    date_joined_after = filters.DateTimeFilter(field_name='date_joined', lookup_expr='gte')
    date_joined_before = filters.DateTimeFilter(field_name='date_joined', lookup_expr='lte')

    class Meta:
        model = User
        fields = ['user_type', 'is_active', 'date_joined_after', 'date_joined_before']
        search_fields = ['email', 'first_name', 'last_name', 'phone_number']


class ProfileFilter(BaseFilterSet):
    """
    Filter for profiles.
    """
    language = filters.CharFilter(field_name='language')

    class Meta:
        model = Profile
        fields = ['language']