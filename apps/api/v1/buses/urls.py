"""
URL configuration for the buses API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BusLocationViewSet, BusViewSet

router = DefaultRouter()
router.register(r'buses', BusViewSet)
router.register(r'locations', BusLocationViewSet, basename='bus-location')

urlpatterns = [
    path('', include(router.urls)),
]
