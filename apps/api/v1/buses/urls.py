"""
URL configuration for the buses API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BusViewSet, BusLocationViewSet

router = DefaultRouter()
router.register(r'buses', BusViewSet)
router.register(r'locations', BusLocationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]