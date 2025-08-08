"""
URL configuration for the drivers API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DriverRatingViewSet, DriverViewSet
from apps.api.v1.accounts.auth_views import register_driver

# Main router
router = DefaultRouter()
router.register(r'drivers', DriverViewSet, basename='driver')

# Separate router for ratings (temporary fix until nested routers are working)
ratings_router = DefaultRouter()
ratings_router.register(r'ratings', DriverRatingViewSet, basename='driver-ratings')

urlpatterns = [
    # Driver registration
    path('register/', register_driver, name='driver-register'),
    
    # Router URLs
    path('', include(router.urls)),
    path('drivers/<uuid:driver_pk>/', include(ratings_router.urls)),
]