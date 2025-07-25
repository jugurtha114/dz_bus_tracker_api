"""
Filters for the gamification app.
"""
import django_filters
from django.utils.translation import gettext_lazy as _

from .models import Achievement, Challenge, Reward


class AchievementFilter(django_filters.FilterSet):
    """
    Filter for achievements.
    """
    achievement_type = django_filters.MultipleChoiceFilter(
        choices=Achievement._meta.get_field('achievement_type').choices,
        help_text=_("Filter by achievement type")
    )
    
    rarity = django_filters.MultipleChoiceFilter(
        choices=Achievement._meta.get_field('rarity').choices,
        help_text=_("Filter by rarity")
    )
    
    min_points = django_filters.NumberFilter(
        field_name='points_reward',
        lookup_expr='gte',
        help_text=_("Minimum points reward")
    )
    
    max_points = django_filters.NumberFilter(
        field_name='points_reward',
        lookup_expr='lte',
        help_text=_("Maximum points reward")
    )
    
    class Meta:
        model = Achievement
        fields = ['achievement_type', 'rarity']


class ChallengeFilter(django_filters.FilterSet):
    """
    Filter for challenges.
    """
    challenge_type = django_filters.MultipleChoiceFilter(
        choices=Challenge._meta.get_field('challenge_type').choices,
        help_text=_("Filter by challenge type")
    )
    
    is_completed = django_filters.BooleanFilter(
        help_text=_("Filter by completion status")
    )
    
    min_reward = django_filters.NumberFilter(
        field_name='points_reward',
        lookup_expr='gte',
        help_text=_("Minimum points reward")
    )
    
    starts_after = django_filters.DateTimeFilter(
        field_name='start_date',
        lookup_expr='gte',
        help_text=_("Challenges starting after this date")
    )
    
    ends_before = django_filters.DateTimeFilter(
        field_name='end_date',
        lookup_expr='lte',
        help_text=_("Challenges ending before this date")
    )
    
    class Meta:
        model = Challenge
        fields = ['challenge_type', 'is_completed', 'target_line']


class RewardFilter(django_filters.FilterSet):
    """
    Filter for rewards.
    """
    reward_type = django_filters.MultipleChoiceFilter(
        choices=Reward._meta.get_field('reward_type').choices,
        help_text=_("Filter by reward type")
    )
    
    min_cost = django_filters.NumberFilter(
        field_name='points_cost',
        lookup_expr='gte',
        help_text=_("Minimum points cost")
    )
    
    max_cost = django_filters.NumberFilter(
        field_name='points_cost',
        lookup_expr='lte',
        help_text=_("Maximum points cost")
    )
    
    partner = django_filters.CharFilter(
        field_name='partner_name',
        lookup_expr='icontains',
        help_text=_("Filter by partner name")
    )
    
    class Meta:
        model = Reward
        fields = ['reward_type', 'partner_name']