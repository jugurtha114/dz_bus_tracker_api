"""
URL configuration for the drivers API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter

from .views import DriverRatingViewSet, DriverViewSet

# Main router
router = DefaultRouter()
router.register(r'drivers', DriverViewSet)

# Nested routers
driver_router = NestedSimpleRouter(router, r'drivers', lookup='driver')
driver_router.register(r'ratings', DriverRatingViewSet, basename='driver-ratings')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(driver_router.urls)),
]