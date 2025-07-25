"""
Views for the gamification app.
"""
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.api.pagination import StandardResultsSetPagination
from .models import (
    UserProfile,
    Achievement,
    UserAchievement,
    PointTransaction,
    Challenge,
    UserChallenge,
    Reward,
    UserReward,
)
from .serializers import (
    UserProfileSerializer,
    ProfileUpdateSerializer,
    AchievementSerializer,
    UserAchievementSerializer,
    PointTransactionSerializer,
    LeaderboardEntrySerializer,
    ChallengeSerializer,
    UserChallengeSerializer,
    RewardSerializer,
    UserRewardSerializer,
    RedeemRewardSerializer,
    CompleteTriSerializer,
)
from .services import GamificationService
from .filters import AchievementFilter, ChallengeFilter, RewardFilter


class ProfileViewSet(viewsets.GenericViewSet):
    """
    ViewSet for managing user gamification profile.
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'update':
            return ProfileUpdateSerializer
        return UserProfileSerializer
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's gamification profile."""
        profile = GamificationService.get_or_create_profile(str(request.user.id))
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_preferences(self, request):
        """Update profile preferences."""
        profile = GamificationService.get_or_create_profile(str(request.user.id))
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(UserProfileSerializer(profile).data)
    
    @action(detail=False, methods=['post'])
    def complete_trip(self, request):
        """Complete a trip and earn points."""
        serializer = CompleteTriSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        GamificationService.complete_trip(
            user_id=str(request.user.id),
            trip_id=str(serializer.validated_data['trip_id']),
            distance=serializer.validated_data['distance']
        )
        
        # Return updated profile
        profile = GamificationService.get_or_create_profile(str(request.user.id))
        return Response(
            UserProfileSerializer(profile).data,
            status=status.HTTP_200_OK
        )


class AchievementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing achievements.
    """
    queryset = Achievement.objects.filter(is_active=True)
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_class = AchievementFilter
    
    def get_queryset(self):
        """Get achievements ordered by type and order."""
        return super().get_queryset().order_by('achievement_type', 'order', 'name')
    
    @action(detail=False, methods=['get'])
    def unlocked(self, request):
        """Get user's unlocked achievements."""
        user_achievements = UserAchievement.objects.filter(
            user=request.user
        ).select_related('achievement').order_by('-unlocked_at')
        
        page = self.paginate_queryset(user_achievements)
        if page is not None:
            serializer = UserAchievementSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = UserAchievementSerializer(user_achievements, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def progress(self, request):
        """Get achievement progress summary."""
        total = Achievement.objects.filter(is_active=True).count()
        unlocked = UserAchievement.objects.filter(user=request.user).count()
        
        # Get progress by type
        progress_by_type = {}
        for achievement_type, _ in Achievement._meta.get_field('achievement_type').choices:
            type_total = Achievement.objects.filter(
                is_active=True,
                achievement_type=achievement_type
            ).count()
            
            type_unlocked = UserAchievement.objects.filter(
                user=request.user,
                achievement__achievement_type=achievement_type
            ).count()
            
            progress_by_type[achievement_type] = {
                'total': type_total,
                'unlocked': type_unlocked,
                'percentage': int((type_unlocked / type_total * 100) if type_total > 0 else 0)
            }
        
        return Response({
            'total': total,
            'unlocked': unlocked,
            'percentage': int((unlocked / total * 100) if total > 0 else 0),
            'by_type': progress_by_type
        })


class PointTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing point transactions.
    """
    serializer_class = PointTransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get transactions for current user."""
        return PointTransaction.objects.filter(
            user=self.request.user
        ).order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get points summary."""
        from django.db.models import Sum
        
        transactions = self.get_queryset()
        
        # Calculate totals by type
        summary = {}
        for transaction_type, label in PointTransaction._meta.get_field('transaction_type').choices:
            type_sum = transactions.filter(
                transaction_type=transaction_type
            ).aggregate(total=Sum('points'))['total'] or 0
            
            summary[transaction_type] = {
                'label': str(label),
                'total': type_sum
            }
        
        # Get current balance
        profile = GamificationService.get_or_create_profile(str(request.user.id))
        
        return Response({
            'current_balance': profile.total_points,
            'total_earned': transactions.filter(points__gt=0).aggregate(
                total=Sum('points')
            )['total'] or 0,
            'total_spent': abs(transactions.filter(points__lt=0).aggregate(
                total=Sum('points')
            )['total'] or 0),
            'by_type': summary
        })


class LeaderboardViewSet(viewsets.GenericViewSet):
    """
    ViewSet for leaderboards.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LeaderboardEntrySerializer
    
    @action(detail=False, methods=['get'])
    def daily(self, request):
        """Get daily leaderboard."""
        leaderboard = GamificationService.get_leaderboard('daily', limit=50)
        return Response(leaderboard)
    
    @action(detail=False, methods=['get'])
    def weekly(self, request):
        """Get weekly leaderboard."""
        leaderboard = GamificationService.get_leaderboard('weekly', limit=50)
        return Response(leaderboard)
    
    @action(detail=False, methods=['get'])
    def monthly(self, request):
        """Get monthly leaderboard."""
        leaderboard = GamificationService.get_leaderboard('monthly', limit=50)
        return Response(leaderboard)
    
    @action(detail=False, methods=['get'])
    def all_time(self, request):
        """Get all-time leaderboard."""
        leaderboard = GamificationService.get_leaderboard('all_time', limit=100)
        return Response(leaderboard)
    
    @action(detail=False, methods=['get'])
    def my_rank(self, request):
        """Get current user's rank in all leaderboards."""
        from .models import Leaderboard
        from django.utils import timezone
        
        user = request.user
        now = timezone.now()
        today = now.date()
        
        ranks = {}
        
        # Get ranks for each period
        for period_type in ['daily', 'weekly', 'monthly', 'all_time']:
            entry = Leaderboard.objects.filter(
                user=user,
                period_type=period_type
            ).order_by('-period_start').first()
            
            if entry:
                ranks[period_type] = {
                    'rank': entry.rank,
                    'points': entry.points,
                    'trips': entry.trips,
                    'movement': (entry.previous_rank - entry.rank) if entry.previous_rank else 0
                }
            else:
                ranks[period_type] = None
        
        return Response(ranks)


class ChallengeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for challenges.
    """
    queryset = Challenge.objects.filter(is_active=True)
    serializer_class = ChallengeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_class = ChallengeFilter
    
    def get_queryset(self):
        """Get active challenges."""
        from django.utils import timezone
        return super().get_queryset().filter(
            end_date__gte=timezone.now()
        ).order_by('-start_date')
    
    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        """Join a challenge."""
        challenge = self.get_object()
        
        user_challenge = GamificationService.join_challenge(
            user_id=str(request.user.id),
            challenge_id=str(challenge.id)
        )
        
        serializer = UserChallengeSerializer(user_challenge)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def my_challenges(self, request):
        """Get user's challenges."""
        user_challenges = UserChallenge.objects.filter(
            user=request.user
        ).select_related('challenge').order_by('-challenge__start_date')
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter == 'active':
            user_challenges = user_challenges.filter(
                is_completed=False,
                challenge__is_active=True
            )
        elif status_filter == 'completed':
            user_challenges = user_challenges.filter(is_completed=True)
        
        page = self.paginate_queryset(user_challenges)
        if page is not None:
            serializer = UserChallengeSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = UserChallengeSerializer(user_challenges, many=True)
        return Response(serializer.data)


class RewardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for rewards.
    """
    serializer_class = RewardSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_class = RewardFilter
    
    def get_queryset(self):
        """Get available rewards."""
        from django.utils import timezone
        now = timezone.now()
        
        return Reward.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now
        ).order_by('points_cost')
    
    @action(detail=True, methods=['post'])
    def redeem(self, request, pk=None):
        """Redeem a reward."""
        reward = self.get_object()
        
        user_reward = GamificationService.redeem_reward(
            user_id=str(request.user.id),
            reward_id=str(reward.id)
        )
        
        serializer = UserRewardSerializer(user_reward)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def my_rewards(self, request):
        """Get user's redeemed rewards."""
        user_rewards = UserReward.objects.filter(
            user=request.user
        ).select_related('reward').order_by('-created_at')
        
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter == 'unused':
            user_rewards = user_rewards.filter(is_used=False)
        elif status_filter == 'used':
            user_rewards = user_rewards.filter(is_used=True)
        
        page = self.paginate_queryset(user_rewards)
        if page is not None:
            serializer = UserRewardSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = UserRewardSerializer(user_rewards, many=True)
        return Response(serializer.data)
