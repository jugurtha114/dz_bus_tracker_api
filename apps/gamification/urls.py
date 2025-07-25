"""
URLs for the gamification app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProfileViewSet,
    AchievementViewSet,
    PointTransactionViewSet,
    LeaderboardViewSet,
    ChallengeViewSet,
    RewardViewSet,
)

router = DefaultRouter()
router.register(r'profile', ProfileViewSet, basename='profile')
router.register(r'achievements', AchievementViewSet, basename='achievement')
router.register(r'transactions', PointTransactionViewSet, basename='transaction')
router.register(r'leaderboard', LeaderboardViewSet, basename='leaderboard')
router.register(r'challenges', ChallengeViewSet, basename='challenge')
router.register(r'rewards', RewardViewSet, basename='reward')

app_name = 'gamification'

urlpatterns = [
    path('', include(router.urls)),
]