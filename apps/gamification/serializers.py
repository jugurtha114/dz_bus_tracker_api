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
from apps.tracking.models import VirtualCurrency, CurrencyTransaction, ReputationScore


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


class VirtualCurrencySerializer(serializers.ModelSerializer):
    """
    Serializer for VirtualCurrency model.
    """
    user = UserBriefSerializer(read_only=True)
    
    class Meta:
        model = VirtualCurrency
        fields = [
            'id', 'user', 'balance', 'lifetime_earned', 'lifetime_spent',
            'last_transaction', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CurrencyTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for CurrencyTransaction model.
    """
    user = UserBriefSerializer(read_only=True)
    display_amount = serializers.SerializerMethodField()
    transaction_type_display = serializers.SerializerMethodField()
    
    class Meta:
        model = CurrencyTransaction
        fields = [
            'id', 'user', 'amount', 'transaction_type', 'description',
            'balance_after', 'metadata', 'created_at',
            'display_amount', 'transaction_type_display'
        ]
        read_only_fields = ['id', 'user', 'created_at']
    
    @extend_schema_field(str)
    def get_display_amount(self, obj):
        """Get formatted display amount."""
        sign = "+" if obj.amount >= 0 else ""
        return f"{sign}{obj.amount} coins"
    
    @extend_schema_field(str)
    def get_transaction_type_display(self, obj):
        """Get human-readable transaction type."""
        return obj.get_transaction_type_display()


class ReputationScoreSerializer(serializers.ModelSerializer):
    """
    Serializer for ReputationScore model.
    """
    user = UserBriefSerializer(read_only=True)
    accuracy_rate = serializers.ReadOnlyField()
    reputation_level_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ReputationScore
        fields = [
            'id', 'user', 'total_reports', 'correct_reports',
            'reputation_level', 'reputation_level_display', 
            'trust_multiplier', 'accuracy_rate', 'last_updated',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at', 'last_updated'
        ]
    
    @extend_schema_field(str)
    def get_reputation_level_display(self, obj):
        """Get human-readable reputation level."""
        return obj.get_reputation_level_display()


class WaitingListJoinSerializer(serializers.Serializer):
    """
    Serializer for joining a bus waiting list.
    """
    bus_id = serializers.UUIDField(
        help_text=_("ID of the bus to wait for")
    )
    stop_id = serializers.CharField(
        help_text=_("ID of the stop where user is waiting")
    )

    def validate_bus_id(self, value):
        """Validate bus exists."""
        from apps.buses.models import Bus
        try:
            Bus.objects.get(id=value)
        except Bus.DoesNotExist:
            raise serializers.ValidationError(_("Bus not found"))
        return value

    def validate_stop_id(self, value):
        """Validate stop exists."""
        from apps.lines.models import Stop
        try:
            Stop.objects.get(id=value)
        except Stop.DoesNotExist:
            raise serializers.ValidationError(_("Stop not found"))
        return value


class WaitingCountReportSerializer(serializers.Serializer):
    """
    Serializer for reporting waiting passenger count.
    """
    stop_id = serializers.CharField(
        help_text=_("ID of the stop")
    )
    bus_id = serializers.UUIDField(
        help_text=_("ID of the bus"),
        required=False,
        allow_null=True
    )
    reported_count = serializers.IntegerField(
        min_value=0,
        max_value=500,
        help_text=_("Number of people waiting")
    )
    confidence_level = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        default='medium',
        help_text=_("Reporter's confidence in the count")
    )
    reporter_latitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
        allow_null=True,
        help_text=_("Reporter's current latitude")
    )
    reporter_longitude = serializers.DecimalField(
        max_digits=10,
        decimal_places=7,
        required=False,
        allow_null=True,
        help_text=_("Reporter's current longitude")
    )

    def validate_stop_id(self, value):
        """Validate stop exists."""
        from apps.lines.models import Stop
        try:
            Stop.objects.get(id=value)
        except Stop.DoesNotExist:
            raise serializers.ValidationError(_("Stop not found"))
        return value

    def validate_bus_id(self, value):
        """Validate bus exists if provided."""
        if value:
            from apps.buses.models import Bus
            try:
                Bus.objects.get(id=value)
            except Bus.DoesNotExist:
                raise serializers.ValidationError(_("Bus not found"))
        return value

    def validate(self, attrs):
        """Cross-field validation."""
        # Validate location if provided
        lat = attrs.get('reporter_latitude')
        lon = attrs.get('reporter_longitude')
        
        if (lat is not None and lon is None) or (lat is None and lon is not None):
            raise serializers.ValidationError(
                _("Both latitude and longitude must be provided together")
            )
        
        # Validate location bounds if provided
        if lat is not None and lon is not None:
            if not (-90 <= lat <= 90):
                raise serializers.ValidationError(
                    _("Latitude must be between -90 and 90 degrees")
                )
            if not (-180 <= lon <= 180):
                raise serializers.ValidationError(
                    _("Longitude must be between -180 and 180 degrees")
                )
        
        return attrs


class WaitingListResponseSerializer(serializers.Serializer):
    """
    Serializer for waiting list operation responses.
    """
    success = serializers.BooleanField()
    message = serializers.CharField()
    coins_earned = serializers.IntegerField(required=False)
    waiting_list_id = serializers.UUIDField(required=False)
    report_id = serializers.UUIDField(required=False)