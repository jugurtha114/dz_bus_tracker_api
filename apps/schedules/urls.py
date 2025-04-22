# apps/schedules/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import ScheduleViewSet, ScheduleExceptionViewSet

router = DefaultRouter()
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'schedule-exceptions', ScheduleExceptionViewSet, basename='schedule-exception')

urlpatterns = [
    path('', include(router.urls)),
]

