"""
URL configuration for the notifications API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import (
    DeviceTokenViewSet,
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationScheduleViewSet,
    SystemNotificationViewSet,
)

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'device-tokens', DeviceTokenViewSet, basename='devicetoken')
router.register(r'preferences', NotificationPreferenceViewSet, basename='notificationpreference')
router.register(r'schedules', NotificationScheduleViewSet, basename='notificationschedule')
router.register(r'system', SystemNotificationViewSet, basename='systemnotification')

urlpatterns = [
    path('', include(router.urls)),
]