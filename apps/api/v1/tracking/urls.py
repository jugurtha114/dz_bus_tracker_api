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
from .views.route_views import RouteTrackingViewSet, RouteSegmentViewSet
from .active_buses_view import active_buses

router = DefaultRouter()
router.register(r'bus-lines', BusLineViewSet)
router.register(r'locations', LocationUpdateViewSet)
router.register(r'passenger-counts', PassengerCountViewSet)
router.register(r'waiting-passengers', WaitingPassengersViewSet)
router.register(r'trips', TripViewSet)
router.register(r'anomalies', AnomalyViewSet)
router.register(r'routes', RouteTrackingViewSet, basename='route-tracking')
router.register(r'route-segments', RouteSegmentViewSet)

urlpatterns = [
    # Active buses endpoint
    path('active-buses/', active_buses, name='active-buses'),
    
    # Router URLs
    path('', include(router.urls)),
]