from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.authentication.api import UserViewSet, LoginAPIView, TokenRefreshAPIView
from apps.drivers.api import DriverViewSet, DriverApplicationViewSet, DriverRatingViewSet
from apps.buses.api import BusViewSet, BusPhotoViewSet, BusVerificationViewSet, BusMaintenanceViewSet
from apps.lines.api import LineViewSet, StopViewSet, LineStopViewSet, LineBusViewSet, FavoriteViewSet
from apps.tracking.api import TrackingSessionViewSet, LocationUpdateViewSet, BatchLocationUpdateAPIView, OfflineLocationBatchViewSet, TrackingLogViewSet
from apps.eta.api import ETAViewSet, ETANotificationViewSet, StopArrivalViewSet
# from apps.notifications.api import NotificationViewSet, NotificationPreferenceViewSet
# from apps.analytics.api import TripLogViewSet, DelayReportViewSet, AnalyticsSummaryViewSet
from apps.feedback.api import FeedbackViewSet, AbuseReportViewSet

# API router
router = DefaultRouter()

# Authentication routes
router.register('users', UserViewSet, basename='user')

# Driver routes
router.register('drivers', DriverViewSet, basename='driver')
router.register('driver-applications', DriverApplicationViewSet, basename='driver-application')
router.register('driver-ratings', DriverRatingViewSet, basename='driver-rating')

# Bus routes
router.register('buses', BusViewSet, basename='bus')
router.register('bus-photos', BusPhotoViewSet, basename='bus-photo')
router.register('bus-verifications', BusVerificationViewSet, basename='bus-verification')
router.register('bus-maintenances', BusMaintenanceViewSet, basename='bus-maintenance')

# Line routes
router.register('lines', LineViewSet, basename='line')
router.register('stops', StopViewSet, basename='stop')
router.register('line-stops', LineStopViewSet, basename='line-stop')
router.register('line-buses', LineBusViewSet, basename='line-bus')
router.register('favorites', FavoriteViewSet, basename='favorite')

# Tracking routes
router.register('tracking-sessions', TrackingSessionViewSet, basename='tracking-session')
router.register('location-updates', LocationUpdateViewSet, basename='location-update')
router.register('offline-batches', OfflineLocationBatchViewSet, basename='offline-batch')
router.register('tracking-logs', TrackingLogViewSet, basename='tracking-log')

# ETA routes
router.register('etas', ETAViewSet, basename='eta')
router.register('eta-notifications', ETANotificationViewSet, basename='eta-notification')
router.register('stop-arrivals', StopArrivalViewSet, basename='stop-arrival')

# # Notification routes
# router.register('notifications', NotificationViewSet, basename='notification')
# router.register('notification-preferences', NotificationPreferenceViewSet, basename='notification-preference')
#
# # Analytics routes
# router.register('trip-logs', TripLogViewSet, basename='trip-log')
# router.register('delay-reports', DelayReportViewSet, basename='delay-report')
# router.register('analytics-summaries', AnalyticsSummaryViewSet, basename='analytics-summary')

# Feedback routes
router.register('feedback', FeedbackViewSet, basename='feedback')
router.register('abuse-reports', AbuseReportViewSet, basename='abuse-report')

# API patterns
api_patterns = [
    path('', include(router.urls)),
    path('login/', LoginAPIView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshAPIView.as_view(), name='token-refresh'),
    path('batch-location-update/', BatchLocationUpdateAPIView.as_view(), name='batch-location-update'),
    
    # API Schema and documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Health check
    # path('health/', include('health_check.urls')),
]

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),
    
    # API URLs
    path('api/v1/', include(api_patterns)),
]

# Add static and media URLs for development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Add debug toolbar
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
