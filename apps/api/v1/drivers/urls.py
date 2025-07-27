"""
URL configuration for the drivers API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter

from .views import DriverRatingViewSet, DriverViewSet
from apps.api.v1.accounts.auth_views import register_driver

# Main router
router = DefaultRouter()
router.register(r'drivers', DriverViewSet, basename='driver')

# Nested routers
driver_router = NestedSimpleRouter(router, r'drivers', lookup='driver')
driver_router.register(r'ratings', DriverRatingViewSet, basename='driver-ratings')

urlpatterns = [
    # Driver registration
    path('register/', register_driver, name='driver-register'),
    
    # Router URLs
    path('', include(router.urls)),
    path('', include(driver_router.urls)),
]