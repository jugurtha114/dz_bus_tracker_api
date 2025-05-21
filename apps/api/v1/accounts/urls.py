"""
URL configuration for the accounts API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProfileViewSet, UserViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'profiles', ProfileViewSet)

urlpatterns = [
    path('', include(router.urls)),
]