"""
Celery tasks for the gamification app.
"""
import logging
from celery import shared_task
from django.utils import timezone

from .services import GamificationService
from .models import Achievement, Challenge

logger = logging.getLogger(__name__)


@shared_task(name='gamification.update_leaderboards')
def update_leaderboards():
    """
    Update all leaderboards.
    This task should run every hour.
    """
    try:
        GamificationService.update_leaderboards()
        logger.info("Successfully updated leaderboards")
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"Error updating leaderboards: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='gamification.check_challenge_completion')
def check_challenge_completion():
    """
    Check and update challenge completion status.
    This task should run daily.
    """
    try:
        now = timezone.now()
        
        # Get challenges that have ended but not marked as completed
        ended_challenges = Challenge.objects.filter(
            is_active=True,
            is_completed=False,
            end_date__lt=now
        )
        
        for challenge in ended_challenges:
            challenge.is_completed = True
            challenge.save()
            
            logger.info(f"Marked challenge '{challenge.name}' as completed")
        
        logger.info(f"Checked {ended_challenges.count()} challenges for completion")
        return {'status': 'success', 'completed': ended_challenges.count()}
        
    except Exception as e:
        logger.error(f"Error checking challenge completion: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='gamification.award_daily_bonus')
def award_daily_bonus():
    """
    Award daily login bonus to active users.
    This task should run daily.
    """
    try:
        from apps.accounts.models import User
        from datetime import timedelta
        
        # Get users who logged in today
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        
        active_users = User.objects.filter(
            last_login__date=yesterday
        )
        
        awarded_count = 0
        for user in active_users:
            try:
                # Award daily bonus
                GamificationService.award_points(
                    user_id=str(user.id),
                    points=5,
                    transaction_type='daily_bonus',
                    description='Daily login bonus'
                )
                awarded_count += 1
            except Exception as e:
                logger.error(f"Error awarding daily bonus to user {user.id}: {e}")
        
        logger.info(f"Awarded daily bonus to {awarded_count} users")
        return {'status': 'success', 'awarded': awarded_count}
        
    except Exception as e:
        logger.error(f"Error awarding daily bonus: {e}")
        return {'status': 'error', 'message': str(e)}


@shared_task(name='gamification.create_default_achievements')
def create_default_achievements():
    """
    Create default achievements if they don't exist.
    This is a one-time task.
    """
    try:
        achievements_data = [
            # Trip achievements
            {'name': 'First Step', 'description': 'Complete your first bus trip', 
             'icon': '🚌', 'achievement_type': 'trips', 'threshold_value': 1,
             'points_reward': 10, 'rarity': 'common', 'order': 1},
            
            {'name': 'Regular Commuter', 'description': 'Complete 10 bus trips',
             'icon': '🎫', 'achievement_type': 'trips', 'threshold_value': 10,
             'points_reward': 50, 'rarity': 'common', 'order': 2},
            
            {'name': 'Frequent Rider', 'description': 'Complete 50 bus trips',
             'icon': '🏃', 'achievement_type': 'trips', 'threshold_value': 50,
             'points_reward': 100, 'rarity': 'uncommon', 'order': 3},
            
            {'name': 'Bus Master', 'description': 'Complete 100 bus trips',
             'icon': '👑', 'achievement_type': 'trips', 'threshold_value': 100,
             'points_reward': 200, 'rarity': 'rare', 'order': 4},
            
            # Distance achievements
            {'name': 'Short Distance', 'description': 'Travel 10 km by bus',
             'icon': '📍', 'achievement_type': 'distance', 'threshold_value': 10,
             'points_reward': 20, 'rarity': 'common', 'order': 10},
            
            {'name': 'City Explorer', 'description': 'Travel 50 km by bus',
             'icon': '🗺️', 'achievement_type': 'distance', 'threshold_value': 50,
             'points_reward': 75, 'rarity': 'uncommon', 'order': 11},
            
            {'name': 'Long Hauler', 'description': 'Travel 200 km by bus',
             'icon': '🛣️', 'achievement_type': 'distance', 'threshold_value': 200,
             'points_reward': 150, 'rarity': 'rare', 'order': 12},
            
            # Streak achievements
            {'name': 'Getting Started', 'description': 'Maintain a 3-day streak',
             'icon': '🔥', 'achievement_type': 'streak', 'threshold_value': 3,
             'points_reward': 30, 'rarity': 'common', 'order': 20},
            
            {'name': 'Week Warrior', 'description': 'Maintain a 7-day streak',
             'icon': '💪', 'achievement_type': 'streak', 'threshold_value': 7,
             'points_reward': 70, 'rarity': 'uncommon', 'order': 21},
            
            {'name': 'Unstoppable', 'description': 'Maintain a 30-day streak',
             'icon': '🚀', 'achievement_type': 'streak', 'threshold_value': 30,
             'points_reward': 300, 'rarity': 'epic', 'order': 22},
            
            # Eco achievements
            {'name': 'Eco Starter', 'description': 'Save 5 kg of CO2',
             'icon': '🌱', 'achievement_type': 'eco', 'threshold_value': 5,
             'points_reward': 25, 'rarity': 'common', 'order': 30},
            
            {'name': 'Green Commuter', 'description': 'Save 25 kg of CO2',
             'icon': '🌳', 'achievement_type': 'eco', 'threshold_value': 25,
             'points_reward': 80, 'rarity': 'uncommon', 'order': 31},
            
            {'name': 'Planet Protector', 'description': 'Save 100 kg of CO2',
             'icon': '🌍', 'achievement_type': 'eco', 'threshold_value': 100,
             'points_reward': 200, 'rarity': 'rare', 'order': 32},
            
            # Level achievements
            {'name': 'Level 5', 'description': 'Reach level 5',
             'icon': '⭐', 'achievement_type': 'level', 'threshold_value': 5,
             'points_reward': 50, 'rarity': 'common', 'order': 40},
            
            {'name': 'Level 10', 'description': 'Reach level 10',
             'icon': '🌟', 'achievement_type': 'level', 'threshold_value': 10,
             'points_reward': 100, 'rarity': 'uncommon', 'order': 41},
            
            {'name': 'Level 25', 'description': 'Reach level 25',
             'icon': '💫', 'achievement_type': 'level', 'threshold_value': 25,
             'points_reward': 250, 'rarity': 'rare', 'order': 42},
            
            {'name': 'Level 50', 'description': 'Reach level 50',
             'icon': '🏆', 'achievement_type': 'level', 'threshold_value': 50,
             'points_reward': 500, 'rarity': 'epic', 'order': 43},
        ]
        
        created_count = 0
        for data in achievements_data:
            achievement, created = Achievement.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
            if created:
                created_count += 1
                logger.info(f"Created achievement: {achievement.name}")
        
        logger.info(f"Created {created_count} new achievements")
        return {'status': 'success', 'created': created_count}
        
    except Exception as e:
        logger.error(f"Error creating default achievements: {e}")
        return {'status': 'error', 'message': str(e)}