"""
Service functions for the gamification app.
"""
import logging
import random
import string
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.accounts.selectors import get_user_by_id
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object
from apps.notifications.services import NotificationService
from apps.tracking.models import Trip

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

logger = logging.getLogger(__name__)


class GamificationService(BaseService):
    """
    Service for gamification-related operations.
    """
    
    @classmethod
    @transaction.atomic
    def get_or_create_profile(cls, user_id: str) -> UserProfile:
        """
        Get or create user's gamification profile.
        
        Args:
            user_id: ID of the user
            
        Returns:
            UserProfile instance
        """
        user = get_user_by_id(user_id)
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        if created:
            logger.info(f"Created gamification profile for user {user.email}")
            
            # Award welcome bonus
            cls.award_points(
                user_id=user_id,
                points=50,
                transaction_type='special_event',
                description='Welcome to DZ Bus Tracker!'
            )
        
        return profile
    
    @classmethod
    @transaction.atomic
    def award_points(
        cls,
        user_id: str,
        points: int,
        transaction_type: str,
        description: str,
        trip_id: Optional[str] = None,
        achievement_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Tuple[PointTransaction, Optional[int]]:
        """
        Award points to a user.
        
        Args:
            user_id: ID of the user
            points: Number of points to award
            transaction_type: Type of transaction
            description: Description of the transaction
            trip_id: Optional trip ID
            achievement_id: Optional achievement ID
            metadata: Optional metadata
            
        Returns:
            Tuple of (PointTransaction, new_level or None)
        """
        try:
            user = get_user_by_id(user_id)
            profile = cls.get_or_create_profile(user_id)
            
            # Create transaction
            transaction_data = {
                'user': user,
                'transaction_type': transaction_type,
                'points': points,
                'description': description,
                'metadata': metadata or {}
            }
            
            if trip_id:
                from apps.tracking.selectors import get_trip_by_id
                transaction_data['trip'] = get_trip_by_id(trip_id)
            
            if achievement_id:
                transaction_data['achievement'] = Achievement.objects.get(id=achievement_id)
            
            transaction = create_object(PointTransaction, transaction_data)
            
            # Update profile
            old_level = profile.current_level
            new_level = profile.add_points(points)
            
            logger.info(f"Awarded {points} points to user {user.email}")
            
            # Check for level up
            level_up = new_level if new_level > old_level else None
            
            if level_up:
                # Notify user of level up
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type='achievement',
                    title=f'Level Up! You reached Level {new_level}',
                    message=f'Congratulations! You are now level {new_level}.',
                    data={'new_level': new_level, 'old_level': old_level}
                )
                
                # Check for level-based achievements
                cls.check_achievements(user_id, 'level')
            
            return transaction, level_up
            
        except Exception as e:
            logger.error(f"Error awarding points: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    @transaction.atomic
    def complete_trip(cls, user_id: str, trip_id: str, distance: float = 0):
        """
        Process trip completion and award points.
        
        Args:
            user_id: ID of the user
            trip_id: ID of the completed trip
            distance: Distance traveled in km
        """
        try:
            profile = cls.get_or_create_profile(user_id)
            
            # Base points for trip completion
            base_points = 10
            
            # Distance bonus (1 point per km)
            distance_points = int(distance)
            
            # Total points
            total_points = base_points + distance_points
            
            # Award points
            cls.award_points(
                user_id=user_id,
                points=total_points,
                transaction_type='trip_complete',
                description=f'Completed trip ({distance:.1f} km)',
                trip_id=trip_id,
                metadata={'distance': distance}
            )
            
            # Update statistics
            profile.total_trips += 1
            profile.total_distance = float(profile.total_distance) + distance
            profile.carbon_saved = float(profile.carbon_saved) + (distance * 0.15)  # 0.15 kg CO2 per km
            
            # Update streak
            today = timezone.now().date()
            if profile.last_trip_date:
                days_diff = (today - profile.last_trip_date).days
                
                if days_diff == 1:
                    # Continue streak
                    profile.current_streak += 1
                    
                    # Streak bonus every 7 days
                    if profile.current_streak % 7 == 0:
                        cls.award_points(
                            user_id=user_id,
                            points=50,
                            transaction_type='streak_bonus',
                            description=f'{profile.current_streak} day streak bonus!'
                        )
                elif days_diff > 1:
                    # Reset streak
                    profile.current_streak = 1
            else:
                profile.current_streak = 1
            
            profile.last_trip_date = today
            
            # Update longest streak
            if profile.current_streak > profile.longest_streak:
                profile.longest_streak = profile.current_streak
            
            profile.save()
            
            # Check achievements
            cls.check_achievements(user_id, 'trips')
            cls.check_achievements(user_id, 'distance')
            cls.check_achievements(user_id, 'streak')
            cls.check_achievements(user_id, 'eco')
            
            # Update challenges
            cls.update_user_challenges(user_id, 'trip', 1)
            
            logger.info(f"Processed trip completion for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error completing trip: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def check_achievements(cls, user_id: str, achievement_type: str):
        """
        Check and award achievements for a user.
        
        Args:
            user_id: ID of the user
            achievement_type: Type of achievement to check
        """
        try:
            user = get_user_by_id(user_id)
            profile = cls.get_or_create_profile(user_id)
            
            # Get relevant achievements
            achievements = Achievement.objects.filter(
                achievement_type=achievement_type,
                is_active=True
            )
            
            for achievement in achievements:
                # Check if already earned
                if UserAchievement.objects.filter(
                    user=user,
                    achievement=achievement
                ).exists():
                    continue
                
                # Check if criteria met
                criteria_met = False
                current_value = 0
                
                if achievement_type == 'trips':
                    current_value = profile.total_trips
                    criteria_met = current_value >= achievement.threshold_value
                
                elif achievement_type == 'distance':
                    current_value = float(profile.total_distance)
                    criteria_met = current_value >= achievement.threshold_value
                
                elif achievement_type == 'streak':
                    current_value = profile.longest_streak
                    criteria_met = current_value >= achievement.threshold_value
                
                elif achievement_type == 'eco':
                    current_value = float(profile.carbon_saved)
                    criteria_met = current_value >= achievement.threshold_value
                
                elif achievement_type == 'level':
                    current_value = profile.current_level
                    criteria_met = current_value >= achievement.threshold_value
                
                if criteria_met:
                    # Award achievement
                    user_achievement = UserAchievement.objects.create(
                        user=user,
                        achievement=achievement,
                        progress=current_value
                    )
                    
                    # Award points
                    cls.award_points(
                        user_id=user_id,
                        points=achievement.points_reward,
                        transaction_type='achievement',
                        description=f'Unlocked: {achievement.name}',
                        achievement_id=str(achievement.id)
                    )
                    
                    # Send notification
                    if profile.receive_achievement_notifications:
                        NotificationService.create_notification(
                            user_id=user_id,
                            notification_type='achievement',
                            title='Achievement Unlocked!',
                            message=f'You unlocked "{achievement.name}" - {achievement.description}',
                            data={
                                'achievement_id': str(achievement.id),
                                'achievement_name': achievement.name,
                                'points_earned': achievement.points_reward
                            }
                        )
                    
                    user_achievement.is_notified = True
                    user_achievement.save()
                    
                    logger.info(f"User {user.email} unlocked achievement: {achievement.name}")
                else:
                    # Update progress
                    user_achievement, created = UserAchievement.objects.get_or_create(
                        user=user,
                        achievement=achievement,
                        defaults={'progress': current_value}
                    )
                    
                    if not created and user_achievement.progress < current_value:
                        user_achievement.progress = current_value
                        user_achievement.save()
        
        except Exception as e:
            logger.error(f"Error checking achievements: {e}")
    
    @classmethod
    def get_leaderboard(
        cls,
        period_type: str = 'weekly',
        limit: int = 10
    ) -> List[Dict]:
        """
        Get leaderboard for a specific period.
        
        Args:
            period_type: Period type (daily, weekly, monthly, all_time)
            limit: Number of entries to return
            
        Returns:
            List of leaderboard entries
        """
        try:
            now = timezone.now()
            
            # Determine period start
            if period_type == 'daily':
                period_start = now.date()
            elif period_type == 'weekly':
                period_start = now.date() - timedelta(days=now.weekday())
            elif period_type == 'monthly':
                period_start = now.date().replace(day=1)
            else:  # all_time
                period_start = date(2000, 1, 1)
            
            # Get or create leaderboard entries
            entries = Leaderboard.objects.filter(
                period_type=period_type,
                period_start=period_start
            ).select_related(
                'user', 'user__gamification_profile'
            ).order_by('-points')[:limit]
            
            # Format response
            leaderboard = []
            for i, entry in enumerate(entries):
                leaderboard.append({
                    'rank': i + 1,
                    'user_id': str(entry.user.id),
                    'user_name': entry.user.get_full_name() or entry.user.email,
                    'points': entry.points,
                    'trips': entry.trips,
                    'distance': float(entry.distance),
                    'level': entry.user.gamification_profile.current_level,
                    'movement': (entry.previous_rank - (i + 1)) if entry.previous_rank else 0
                })
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []
    
    @classmethod
    @transaction.atomic
    def join_challenge(cls, user_id: str, challenge_id: str) -> UserChallenge:
        """
        Join a challenge.
        
        Args:
            user_id: ID of the user
            challenge_id: ID of the challenge
            
        Returns:
            UserChallenge instance
        """
        try:
            user = get_user_by_id(user_id)
            challenge = Challenge.objects.get(id=challenge_id)
            
            # Check if challenge is active
            if not challenge.is_active:
                raise ValidationError("Challenge is not active")
            
            # Check if already joined
            user_challenge, created = UserChallenge.objects.get_or_create(
                user=user,
                challenge=challenge
            )
            
            if created:
                logger.info(f"User {user.email} joined challenge: {challenge.name}")
            
            return user_challenge
            
        except Challenge.DoesNotExist:
            raise ValidationError("Challenge not found")
        except Exception as e:
            logger.error(f"Error joining challenge: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def update_user_challenges(cls, user_id: str, update_type: str, value: int = 1):
        """
        Update user's challenge progress.
        
        Args:
            user_id: ID of the user
            update_type: Type of update (trip, distance, etc.)
            value: Value to add to progress
        """
        try:
            user = get_user_by_id(user_id)
            now = timezone.now()
            
            # Get active challenges for user
            user_challenges = UserChallenge.objects.filter(
                user=user,
                challenge__is_active=True,
                challenge__start_date__lte=now,
                challenge__end_date__gte=now,
                is_completed=False
            ).select_related('challenge')
            
            for user_challenge in user_challenges:
                challenge = user_challenge.challenge
                
                # Update progress based on challenge type
                if update_type == 'trip' and challenge.challenge_type in ['individual', 'route']:
                    user_challenge.progress += value
                    
                    # Check completion
                    if user_challenge.progress >= challenge.target_value:
                        user_challenge.is_completed = True
                        user_challenge.completed_at = now
                        
                        # Award points
                        cls.award_points(
                            user_id=user_id,
                            points=challenge.points_reward,
                            transaction_type='special_event',
                            description=f'Completed challenge: {challenge.name}'
                        )
                        
                        user_challenge.points_earned = challenge.points_reward
                        user_challenge.is_rewarded = True
                        
                        # Award achievement if linked
                        if challenge.achievement:
                            UserAchievement.objects.get_or_create(
                                user=user,
                                achievement=challenge.achievement
                            )
                    
                    user_challenge.save()
            
        except Exception as e:
            logger.error(f"Error updating challenges: {e}")
    
    @classmethod
    @transaction.atomic
    def redeem_reward(cls, user_id: str, reward_id: str) -> UserReward:
        """
        Redeem a reward using points.
        
        Args:
            user_id: ID of the user
            reward_id: ID of the reward
            
        Returns:
            UserReward instance
        """
        try:
            user = get_user_by_id(user_id)
            profile = cls.get_or_create_profile(user_id)
            reward = Reward.objects.get(id=reward_id)
            
            # Check if reward is available
            if not reward.is_available:
                raise ValidationError("Reward is not available")
            
            # Check if user has enough points
            if profile.total_points < reward.points_cost:
                raise ValidationError("Insufficient points")
            
            # Generate redemption code
            redemption_code = cls._generate_redemption_code()
            
            # Create user reward
            user_reward = UserReward.objects.create(
                user=user,
                reward=reward,
                points_spent=reward.points_cost,
                redemption_code=redemption_code,
                expires_at=timezone.now() + timedelta(days=30)
            )
            
            # Deduct points
            cls.award_points(
                user_id=user_id,
                points=-reward.points_cost,
                transaction_type='penalty',
                description=f'Redeemed: {reward.name}',
                metadata={'reward_id': str(reward.id)}
            )
            
            # Update reward quantities
            if reward.quantity_available != -1:
                reward.quantity_redeemed += 1
                reward.save()
            
            # Send notification
            NotificationService.create_notification(
                user_id=user_id,
                notification_type='reward',
                title='Reward Redeemed!',
                message=f'Your redemption code for {reward.name} is: {redemption_code}',
                data={
                    'reward_id': str(reward.id),
                    'redemption_code': redemption_code,
                    'expires_at': user_reward.expires_at.isoformat()
                }
            )
            
            logger.info(f"User {user.email} redeemed reward: {reward.name}")
            return user_reward
            
        except Reward.DoesNotExist:
            raise ValidationError("Reward not found")
        except Exception as e:
            logger.error(f"Error redeeming reward: {e}")
            raise ValidationError(str(e))
    
    @classmethod
    def _generate_redemption_code(cls) -> str:
        """Generate a unique redemption code."""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not UserReward.objects.filter(redemption_code=code).exists():
                return code
    
    @classmethod
    def update_leaderboards(cls):
        """
        Update all leaderboards. Should be called periodically.
        """
        try:
            now = timezone.now()
            today = now.date()
            
            # Get all users with profiles
            profiles = UserProfile.objects.filter(
                display_on_leaderboard=True
            ).select_related('user')
            
            for period_type, period_start in [
                ('daily', today),
                ('weekly', today - timedelta(days=today.weekday())),
                ('monthly', today.replace(day=1)),
                ('all_time', date(2000, 1, 1))
            ]:
                # Calculate period end
                if period_type == 'daily':
                    period_end = today
                elif period_type == 'weekly':
                    period_end = period_start + timedelta(days=6)
                elif period_type == 'monthly':
                    next_month = period_start.replace(day=28) + timedelta(days=4)
                    period_end = next_month - timedelta(days=next_month.day)
                else:
                    period_end = None
                
                # Get existing entries
                existing_entries = {
                    entry.user_id: entry
                    for entry in Leaderboard.objects.filter(
                        period_type=period_type,
                        period_start=period_start
                    )
                }
                
                # Calculate scores for each user
                for profile in profiles:
                    # Get points for period
                    points_query = PointTransaction.objects.filter(
                        user=profile.user,
                        created_at__date__gte=period_start
                    )
                    
                    if period_end:
                        points_query = points_query.filter(
                            created_at__date__lte=period_end
                        )
                    
                    period_points = points_query.aggregate(
                        total=Sum('points')
                    )['total'] or 0
                    
                    # Get trips for period
                    trips_query = Trip.objects.filter(
                        Q(bus__driver__user=profile.user) | 
                        Q(point_transactions__user=profile.user),
                        start_time__date__gte=period_start
                    )
                    
                    if period_end:
                        trips_query = trips_query.filter(
                            start_time__date__lte=period_end
                        )
                    
                    period_trips = trips_query.distinct().count()
                    
                    # Update or create entry
                    if profile.user.id in existing_entries:
                        entry = existing_entries[profile.user.id]
                        entry.points = period_points
                        entry.trips = period_trips
                        entry.distance = profile.total_distance  # Could calculate period distance
                        entry.save()
                    else:
                        Leaderboard.objects.create(
                            user=profile.user,
                            period_type=period_type,
                            period_start=period_start,
                            period_end=period_end,
                            points=period_points,
                            trips=period_trips,
                            distance=profile.total_distance
                        )
                
                # Update rankings
                entries = Leaderboard.objects.filter(
                    period_type=period_type,
                    period_start=period_start
                ).order_by('-points', '-trips')
                
                for i, entry in enumerate(entries):
                    new_rank = i + 1
                    if entry.rank != new_rank:
                        entry.previous_rank = entry.rank
                        entry.rank = new_rank
                        entry.save()
            
            logger.info("Updated leaderboards successfully")
            
        except Exception as e:
            logger.error(f"Error updating leaderboards: {e}")