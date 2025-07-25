"""
Admin configuration for the gamification app.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    UserProfile,
    Achievement,
    UserAchievement,
    PointTransaction,
    Leaderboard,
    Challenge,
    UserChallenge,
    Reward,
    UserReward,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'total_points', 'current_level', 'total_trips',
        'current_streak', 'display_on_leaderboard', 'created_at'
    ]
    list_filter = ['current_level', 'display_on_leaderboard', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('User'), {
            'fields': ('user',)
        }),
        (_('Points & Level'), {
            'fields': ('total_points', 'current_level', 'experience_points')
        }),
        (_('Statistics'), {
            'fields': ('total_trips', 'total_distance', 'carbon_saved')
        }),
        (_('Streaks'), {
            'fields': ('current_streak', 'longest_streak', 'last_trip_date')
        }),
        (_('Preferences'), {
            'fields': ('receive_achievement_notifications', 'display_on_leaderboard')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'achievement_type', 'threshold_value', 'points_reward',
        'rarity', 'is_active', 'order'
    ]
    list_filter = ['achievement_type', 'rarity', 'is_active']
    search_fields = ['name', 'description']
    ordering = ['order', 'name']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'icon')
        }),
        (_('Requirements'), {
            'fields': ('achievement_type', 'threshold_value')
        }),
        (_('Rewards'), {
            'fields': ('points_reward', 'rarity')
        }),
        (_('Display'), {
            'fields': ('is_active', 'order')
        }),
    )


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'achievement', 'progress', 'unlocked_at', 'is_notified'
    ]
    list_filter = ['is_notified', 'unlocked_at']
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'achievement__name'
    ]
    readonly_fields = ['unlocked_at']
    date_hierarchy = 'unlocked_at'


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'transaction_type', 'points', 'description', 'created_at'
    ]
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__email', 'description']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (_('Transaction'), {
            'fields': ('user', 'transaction_type', 'points', 'description')
        }),
        (_('Related Objects'), {
            'fields': ('trip', 'achievement'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        (_('Timestamp'), {
            'fields': ('created_at',)
        }),
    )


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'period_type', 'period_start', 'points', 'trips',
        'rank', 'previous_rank'
    ]
    list_filter = ['period_type', 'period_start']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    ordering = ['period_type', '-points']
    
    fieldsets = (
        (_('User'), {
            'fields': ('user',)
        }),
        (_('Period'), {
            'fields': ('period_type', 'period_start', 'period_end')
        }),
        (_('Scores'), {
            'fields': ('points', 'trips', 'distance')
        }),
        (_('Ranking'), {
            'fields': ('rank', 'previous_rank')
        }),
    )


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'challenge_type', 'start_date', 'end_date',
        'progress_percentage', 'is_active', 'is_completed'
    ]
    list_filter = ['challenge_type', 'is_active', 'is_completed']
    search_fields = ['name', 'description']
    date_hierarchy = 'start_date'
    filter_horizontal = ['target_stops']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'challenge_type')
        }),
        (_('Duration'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Requirements'), {
            'fields': ('target_value', 'current_value')
        }),
        (_('Rewards'), {
            'fields': ('points_reward', 'achievement')
        }),
        (_('Targets'), {
            'fields': ('target_line', 'target_stops'),
            'classes': ('collapse',)
        }),
        (_('Status'), {
            'fields': ('is_active', 'is_completed')
        }),
    )
    
    def progress_percentage(self, obj):
        return f"{obj.progress_percentage}%"
    progress_percentage.short_description = _("Progress")


@admin.register(UserChallenge)
class UserChallengeAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'challenge', 'progress', 'is_completed',
        'points_earned', 'is_rewarded'
    ]
    list_filter = ['is_completed', 'is_rewarded', 'completed_at']
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'challenge__name'
    ]
    readonly_fields = ['completed_at']


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'reward_type', 'points_cost', 'quantity_available',
        'quantity_redeemed', 'is_available', 'is_active'
    ]
    list_filter = ['reward_type', 'is_active', 'valid_from', 'valid_until']
    search_fields = ['name', 'description', 'partner_name']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'reward_type')
        }),
        (_('Cost'), {
            'fields': ('points_cost',)
        }),
        (_('Availability'), {
            'fields': ('quantity_available', 'quantity_redeemed')
        }),
        (_('Validity'), {
            'fields': ('valid_from', 'valid_until')
        }),
        (_('Display'), {
            'fields': ('image', 'is_active')
        }),
        (_('Partner'), {
            'fields': ('partner_name',),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserReward)
class UserRewardAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'reward', 'points_spent', 'redemption_code',
        'is_used', 'used_at', 'expires_at'
    ]
    list_filter = ['is_used', 'created_at', 'used_at', 'expires_at']
    search_fields = [
        'user__email', 'reward__name', 'redemption_code'
    ]
    readonly_fields = ['redemption_code', 'created_at']
    
    fieldsets = (
        (_('User & Reward'), {
            'fields': ('user', 'reward')
        }),
        (_('Redemption'), {
            'fields': ('points_spent', 'redemption_code')
        }),
        (_('Status'), {
            'fields': ('is_used', 'used_at')
        }),
        (_('Validity'), {
            'fields': ('expires_at',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
