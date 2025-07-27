"""
Serializers for the gamification app.
"""
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from drf_spectacular.utils import extend_schema_field

from apps.api.v1.accounts.serializers import UserBriefSerializer
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


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for UserProfile model.
    """
    user = UserBriefSerializer(read_only=True)
    next_level_points = serializers.SerializerMethodField()
    level_progress = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'total_points', 'current_level', 'experience_points',
            'next_level_points', 'level_progress',
            'total_trips', 'total_distance', 'carbon_saved',
            'current_streak', 'longest_streak', 'last_trip_date',
            'receive_achievement_notifications', 'display_on_leaderboard',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'total_points', 'current_level', 'experience_points',
            'total_trips', 'total_distance', 'carbon_saved',
            'current_streak', 'longest_streak', 'last_trip_date',
            'created_at', 'updated_at'
        ]
    
    @extend_schema_field(int)
    def get_next_level_points(self, obj):
        """Points needed for next level."""
        return obj.current_level * 100
    
    @extend_schema_field(int)
    def get_level_progress(self, obj):
        """Progress percentage to next level."""
        next_level_points = obj.current_level * 100
        if next_level_points == 0:
            return 100
        return int((obj.experience_points / next_level_points) * 100)


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating profile preferences.
    """
    class Meta:
        model = UserProfile
        fields = [
            'receive_achievement_notifications',
            'display_on_leaderboard'
        ]


class AchievementSerializer(serializers.ModelSerializer):
    """
    Serializer for Achievement model.
    """
    is_unlocked = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Achievement
        fields = [
            'id', 'name', 'description', 'icon',
            'achievement_type', 'threshold_value', 'points_reward',
            'rarity', 'is_unlocked', 'progress', 'progress_percentage'
        ]
    
    @extend_schema_field(bool)
    def get_is_unlocked(self, obj):
        """Check if user has unlocked this achievement."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserAchievement.objects.filter(
                user=request.user,
                achievement=obj
            ).exists()
        return False
    
    @extend_schema_field(int)
    def get_progress(self, obj):
        """Get user's progress towards this achievement."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user_achievement = UserAchievement.objects.filter(
                user=request.user,
                achievement=obj
            ).first()
            
            if user_achievement:
                return user_achievement.progress
            
            # Calculate current progress
            profile = UserProfile.objects.filter(user=request.user).first()
            if profile:
                if obj.achievement_type == 'trips':
                    return profile.total_trips
                elif obj.achievement_type == 'distance':
                    return float(profile.total_distance)
                elif obj.achievement_type == 'streak':
                    return profile.longest_streak
                elif obj.achievement_type == 'eco':
                    return float(profile.carbon_saved)
                elif obj.achievement_type == 'level':
                    return profile.current_level
        
        return 0
    
    @extend_schema_field(float)
    def get_progress_percentage(self, obj):
        """Get progress percentage."""
        progress = self.get_progress(obj)
        if obj.threshold_value == 0:
            return 100
        return min(100, int((progress / obj.threshold_value) * 100))


class UserAchievementSerializer(serializers.ModelSerializer):
    """
    Serializer for UserAchievement model.
    """
    achievement = AchievementSerializer(read_only=True)
    
    class Meta:
        model = UserAchievement
        fields = [
            'id', 'achievement', 'unlocked_at', 'progress', 'is_notified'
        ]


class PointTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for PointTransaction model.
    """
    class Meta:
        model = PointTransaction
        fields = [
            'id', 'transaction_type', 'points', 'description',
            'created_at'
        ]


class LeaderboardEntrySerializer(serializers.Serializer):
    """
    Serializer for leaderboard entries.
    """
    rank = serializers.IntegerField()
    user_id = serializers.CharField()
    user_name = serializers.CharField()
    points = serializers.IntegerField()
    trips = serializers.IntegerField()
    distance = serializers.FloatField()
    level = serializers.IntegerField()
    movement = serializers.IntegerField()


class ChallengeSerializer(serializers.ModelSerializer):
    """
    Serializer for Challenge model.
    """
    progress_percentage = serializers.ReadOnlyField()
    is_joined = serializers.SerializerMethodField()
    user_progress = serializers.SerializerMethodField()
    participants_count = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Challenge
        fields = [
            'id', 'name', 'description', 'challenge_type',
            'start_date', 'end_date', 'target_value', 'current_value',
            'progress_percentage', 'points_reward',
            'is_active', 'is_completed', 'is_joined',
            'user_progress', 'participants_count', 'time_remaining'
        ]
    
    @extend_schema_field(bool)
    def get_is_joined(self, obj):
        """Check if user has joined this challenge."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return UserChallenge.objects.filter(
                user=request.user,
                challenge=obj
            ).exists()
        return False
    
    @extend_schema_field(dict)
    def get_user_progress(self, obj):
        """Get user's progress in this challenge."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user_challenge = UserChallenge.objects.filter(
                user=request.user,
                challenge=obj
            ).first()
            
            if user_challenge:
                return {
                    'progress': user_challenge.progress,
                    'is_completed': user_challenge.is_completed,
                    'points_earned': user_challenge.points_earned
                }
        return None
    
    @extend_schema_field(int)
    def get_participants_count(self, obj):
        """Get number of participants."""
        return obj.participants.count()
    
    @extend_schema_field(str)
    def get_time_remaining(self, obj):
        """Get time remaining in seconds."""
        from django.utils import timezone
        if obj.end_date > timezone.now():
            return int((obj.end_date - timezone.now()).total_seconds())
        return 0


class UserChallengeSerializer(serializers.ModelSerializer):
    """
    Serializer for UserChallenge model.
    """
    challenge = ChallengeSerializer(read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = UserChallenge
        fields = [
            'id', 'challenge', 'progress', 'progress_percentage',
            'is_completed', 'completed_at', 'points_earned', 'is_rewarded'
        ]
    
    @extend_schema_field(float)
    def get_progress_percentage(self, obj):
        """Get progress percentage."""
        if obj.challenge.target_value == 0:
            return 100
        return min(100, int((obj.progress / obj.challenge.target_value) * 100))


class RewardSerializer(serializers.ModelSerializer):
    """
    Serializer for Reward model.
    """
    is_available = serializers.ReadOnlyField()
    can_afford = serializers.SerializerMethodField()
    
    class Meta:
        model = Reward
        fields = [
            'id', 'name', 'description', 'reward_type',
            'points_cost', 'quantity_available', 'quantity_redeemed',
            'valid_from', 'valid_until', 'image', 'partner_name',
            'is_available', 'can_afford'
        ]
    
    @extend_schema_field(bool)
    def get_can_afford(self, obj):
        """Check if user can afford this reward."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            profile = UserProfile.objects.filter(user=request.user).first()
            if profile:
                return profile.total_points >= obj.points_cost
        return False


class UserRewardSerializer(serializers.ModelSerializer):
    """
    Serializer for UserReward model.
    """
    reward = RewardSerializer(read_only=True)
    
    class Meta:
        model = UserReward
        fields = [
            'id', 'reward', 'points_spent', 'redemption_code',
            'is_used', 'used_at', 'expires_at', 'created_at'
        ]


class RedeemRewardSerializer(serializers.Serializer):
    """
    Serializer for redeeming rewards.
    """
    reward_id = serializers.UUIDField(help_text=_("ID of the reward to redeem"))


class CompleteTriSerializer(serializers.Serializer):
    """
    Serializer for completing a trip.
    """
    trip_id = serializers.UUIDField(help_text=_("ID of the completed trip"))
    distance = serializers.FloatField(
        min_value=0,
        help_text=_("Distance traveled in km")
    )