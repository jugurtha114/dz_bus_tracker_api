"""
URL configuration for the notifications API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DeviceTokenViewSet, NotificationViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet)
router.register(r'device-tokens', DeviceTokenViewSet)

urlpatterns = [
    path('', include(router.urls)),
]