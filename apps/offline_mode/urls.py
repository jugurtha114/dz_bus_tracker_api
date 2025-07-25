"""
URL configuration for offline mode API.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CacheConfigurationViewSet,
    UserCacheViewSet,
    CachedDataViewSet,
    SyncQueueViewSet,
    OfflineLogViewSet,
)

router = DefaultRouter()
router.register(r'config', CacheConfigurationViewSet, basename='cache-config')
router.register(r'cache', UserCacheViewSet, basename='user-cache')
router.register(r'data', CachedDataViewSet, basename='cached-data')
router.register(r'sync-queue', SyncQueueViewSet, basename='sync-queue')
router.register(r'logs', OfflineLogViewSet, basename='offline-logs')

app_name = 'offline_mode'

urlpatterns = [
    path('', include(router.urls)),
]