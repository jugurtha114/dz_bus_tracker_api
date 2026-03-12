"""
URL configuration for Admin analytics API (R22).
"""
from django.urls import path

from .views import BusiestStopsView, LineStatsView, RidershipStatsView

urlpatterns = [
    path('stats/ridership/', RidershipStatsView.as_view(), name='admin-stats-ridership'),
    path('stats/lines/', LineStatsView.as_view(), name='admin-stats-lines'),
    path('stats/stops/busiest/', BusiestStopsView.as_view(), name='admin-stats-stops-busiest'),
]
