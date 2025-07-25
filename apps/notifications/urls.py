"""
URLs for the notifications app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    DeviceTokenViewSet,
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationScheduleViewSet,
    SystemNotificationViewSet,
)

router = DefaultRouter()
router.register(r'device-tokens', DeviceTokenViewSet, basename='devicetoken')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'preferences', NotificationPreferenceViewSet, basename='notificationpreference')
router.register(r'schedules', NotificationScheduleViewSet, basename='notificationschedule')
router.register(r'system', SystemNotificationViewSet, basename='systemnotification')

app_name = 'notifications'

urlpatterns = [
    path('', include(router.urls)),
]