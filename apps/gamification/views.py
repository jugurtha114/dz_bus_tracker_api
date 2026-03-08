"""
Views for the gamification app.
"""
import logging
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

logger = logging.getLogger(__name__)

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
from apps.tracking.models import VirtualCurrency, CurrencyTransaction, ReputationScore, BusWaitingList, WaitingCountReport
from apps.tracking.services.waiting_service import WaitingListService, WaitingReportService
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
    VirtualCurrencySerializer,
    CurrencyTransactionSerializer,
    ReputationScoreSerializer,
    WaitingListJoinSerializer,
    WaitingCountReportSerializer,
    WaitingListResponseSerializer,
)
from .services import GamificationService, VirtualCurrencyService, ReputationService
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
    
    @action(detail=False, methods=['post'], url_path='refresh')
    def refresh_leaderboards(self, request):
        """Admin-only: recompute all leaderboards."""
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            GamificationService.update_leaderboards()
            return Response({'status': 'leaderboards updated'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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


class ChallengeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for challenges. Read-only for all users; create allowed for staff only.
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

    def create(self, request, *args, **kwargs):
        """Admin-only: create a challenge."""
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)
    
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


class VirtualCurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for virtual currency management.
    """
    serializer_class = VirtualCurrencySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get current user's virtual currency."""
        return VirtualCurrency.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get current user's virtual currency balance."""
        currency = VirtualCurrencyService.get_or_create_currency(str(request.user.id))
        serializer = VirtualCurrencySerializer(currency)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get current user's virtual currency transaction history."""
        limit = int(request.query_params.get('limit', 20))
        transaction_type = request.query_params.get('type')
        
        transactions = CurrencyTransaction.objects.filter(
            user=request.user
        ).order_by('-created_at')
        
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        
        transactions = transactions[:limit]
        
        page = self.paginate_queryset(transactions)
        if page is not None:
            serializer = CurrencyTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CurrencyTransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get virtual currency leaderboard."""
        period = request.query_params.get('period', 'monthly')
        limit = int(request.query_params.get('limit', 10))
        
        leaderboard = VirtualCurrencyService.get_leaderboard(period=period, limit=limit)
        
        return Response({
            'period': period,
            'leaderboard': leaderboard
        })


class ReputationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for reputation score management.
    """
    serializer_class = ReputationScoreSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get current user's reputation score."""
        return ReputationScore.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get current user's reputation statistics."""
        stats = ReputationService.get_reputation_stats(str(request.user.id))
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Get reputation leaderboard."""
        # Get top reputation users
        top_users = ReputationScore.objects.filter(
            total_reports__gte=10  # Minimum 10 reports to be on leaderboard
        ).select_related('user').order_by('-trust_multiplier', '-correct_reports')[:20]
        
        leaderboard = []
        for i, reputation in enumerate(top_users):
            leaderboard.append({
                'rank': i + 1,
                'user_name': reputation.user.get_full_name() or reputation.user.first_name,
                'reputation_level': reputation.reputation_level,
                'accuracy_rate': reputation.accuracy_rate,
                'total_reports': reputation.total_reports,
                'trust_multiplier': float(reputation.trust_multiplier)
            })
        
        return Response(leaderboard)


class WaitingListViewSet(viewsets.GenericViewSet):
    """
    ViewSet for waiting list operations integrated with gamification.
    Provides endpoints for joining waiting lists and reporting passenger counts.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'], url_path='join')
    def join_waiting_list(self, request):
        """
        Join a bus waiting list and earn virtual currency.
        
        This endpoint allows users to join a waiting list for a specific bus at a stop.
        Users earn 10 coins for joining and contribute to crowdsourced data.
        
        Request body:
        {
            "bus_id": "uuid",
            "stop_id": "stop_id"
        }
        
        Returns:
        {
            "success": true,
            "message": "Successfully joined waiting list",
            "coins_earned": 10,
            "waiting_list_id": "uuid"
        }
        """
        serializer = WaitingListJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Join the waiting list
            waiting_list = WaitingListService.join_waiting_list(
                user_id=str(request.user.id),
                bus_id=str(serializer.validated_data['bus_id']),
                stop_id=str(serializer.validated_data['stop_id'])
            )
            
            # Get coins earned (handled by service but we can check)
            coins_earned = 10  # Standard reward for joining
            
            response_data = {
                'success': True,
                'message': _('Successfully joined waiting list'),
                'coins_earned': coins_earned,
                'waiting_list_id': str(waiting_list.id)
            }
            
            return Response(
                WaitingListResponseSerializer(response_data).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Error joining waiting list: {e}")
            return Response(
                {
                    'success': False,
                    'message': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'], url_path='report_count')
    def report_waiting_count(self, request):
        """
        Report the number of people waiting at a stop.
        
        This endpoint allows users to report crowdsourced waiting passenger counts.
        Reports contribute to the user's reputation score and earn virtual currency
        based on accuracy when verified by drivers.
        
        Request body:
        {
            "stop_id": "stop_id",
            "bus_id": "uuid" (optional),
            "reported_count": 24,
            "confidence_level": "high",
            "reporter_latitude": 50.6118085 (optional),
            "reporter_longitude": 3.0743687 (optional)
        }
        
        Returns:
        {
            "success": true,
            "message": "Report submitted successfully",
            "report_id": "uuid"
        }
        """
        serializer = WaitingCountReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Create the report
            report = WaitingReportService.create_report(
                reporter_id=str(request.user.id),
                stop_id=str(serializer.validated_data['stop_id']),
                reported_count=serializer.validated_data['reported_count'],
                bus_id=str(serializer.validated_data.get('bus_id')) if serializer.validated_data.get('bus_id') else None,
                confidence_level=serializer.validated_data.get('confidence_level', 'medium'),
                reporter_latitude=serializer.validated_data.get('reporter_latitude'),
                reporter_longitude=serializer.validated_data.get('reporter_longitude')
            )
            
            response_data = {
                'success': True,
                'message': _('Report submitted successfully. You will earn coins when verified.'),
                'report_id': str(report.id)
            }
            
            return Response(
                WaitingListResponseSerializer(response_data).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Error creating waiting count report: {e}")
            return Response(
                {
                    'success': False,
                    'message': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
