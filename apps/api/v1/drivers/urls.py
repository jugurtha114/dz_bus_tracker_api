"""
URL configuration for the drivers API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DriverViewSet
from apps.api.v1.accounts.auth_views import register_driver

# Main router — ratings are handled by @action on DriverViewSet (GET/POST /drivers/{pk}/ratings/)
router = DefaultRouter()
router.register(r'drivers', DriverViewSet, basename='driver')

urlpatterns = [
    # Driver registration
    path('register/', register_driver, name='driver-register'),

    # Router URLs
    path('', include(router.urls)),
]