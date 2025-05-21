"""
URL configuration for the tracking API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnomalyViewSet,
    BusLineViewSet,
    LocationUpdateViewSet,
    PassengerCountViewSet,
    TripViewSet,
    WaitingPassengersViewSet,
)

router = DefaultRouter()
router.register(r'bus-lines', BusLineViewSet)
router.register(r'locations', LocationUpdateViewSet)
router.register(r'passenger-counts', PassengerCountViewSet)
router.register(r'waiting-passengers', WaitingPassengersViewSet)
router.register(r'trips', TripViewSet)
router.register(r'anomalies', AnomalyViewSet)

urlpatterns = [
    path('', include(router.urls)),
]