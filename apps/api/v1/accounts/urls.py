"""
URL configuration for the accounts API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProfileViewSet, UserViewSet
from .auth_views import register, login, register_driver

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'profiles', ProfileViewSet)

urlpatterns = [
    # Authentication endpoints
    path('register/', register, name='register'),
    path('login/', login, name='login'),
    path('register-driver/', register_driver, name='register_driver'),
    
    # Add a simple profile endpoint
    path('profile/', ProfileViewSet.as_view({'get': 'me'}), name='profile'),
    
    # Router URLs
    path('', include(router.urls)),
]