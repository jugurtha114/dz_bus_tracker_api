"""
URL configuration for the lines API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LineViewSet, ScheduleViewSet, StopViewSet

router = DefaultRouter()
router.register(r'lines', LineViewSet)
router.register(r'stops', StopViewSet)
router.register(r'schedules', ScheduleViewSet)

urlpatterns = [
    path('', include(router.urls)),
]