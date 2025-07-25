"""
URL configuration for API v1.
"""
from django.urls import include, path

urlpatterns = [
    # Accounts API
    path('accounts/', include('apps.api.v1.accounts.urls')),

    # Buses API
    path('buses/', include('apps.api.v1.buses.urls')),

    # Drivers API
    path('drivers/', include('apps.api.v1.drivers.urls')),

    # Lines API
    path('lines/', include('apps.api.v1.lines.urls')),

    # Tracking API
    path('tracking/', include('apps.api.v1.tracking.urls')),

    # Notifications API
    path('notifications/', include('apps.api.v1.notifications.urls')),
    
    # Gamification API
    path('gamification/', include('apps.gamification.urls')),
    path('offline/', include('apps.offline_mode.urls')),
]