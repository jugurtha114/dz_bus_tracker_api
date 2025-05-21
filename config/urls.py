"""
URL configuration for DZ Bus Tracker project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),

    # API URLs
    path("api/", include("apps.api.urls")),

    # User account management
    # path("accounts/", include("apps.accounts.urls")),
]

# API documentation
urlpatterns += [
    path("api/docs/", include("rest_framework.urls")),
]

# Serve static/media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug toolbar
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns

# Set admin site headers
admin.site.site_header = _("DZ Bus Tracker Administration")
admin.site.site_title = _("DZ Bus Tracker Admin")
admin.site.index_title = _("Welcome to DZ Bus Tracker Admin")
