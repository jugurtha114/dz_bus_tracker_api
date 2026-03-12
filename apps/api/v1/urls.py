"""
URL configuration for API v1.
"""
from django.urls import include, path
from django.views.generic import RedirectView

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

    # Offline mode API
    path('offline/', include('apps.offline_mode.urls')),

    # Admin analytics API (R22)
    path('admin/', include('apps.api.v1.admin.urls')),

    # Trip history shortcut - redirects to the tracking trips history endpoint
    path('trips/history/', RedirectView.as_view(
        url='/api/v1/tracking/trips/history/',
        permanent=False,
        query_string=True
    ), name='trips-history-redirect'),
]
