"""
View mixins for reuse across the application.
"""
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
import logging

logger = logging.getLogger(__name__)


class CacheMixin:
    """
    Mixin to add caching to Django views.
    """
    cache_timeout = 60 * 15  # 15 minutes

    def get_cache_timeout(self):
        """
        Return the cache timeout for this view.
        """
        return self.cache_timeout

    @method_decorator(cache_page(cache_timeout))
    @method_decorator(vary_on_cookie)
    @method_decorator(vary_on_headers("Accept-Language"))
    def dispatch(self, *args, **kwargs):
        """
        Cache the response.
        """
        return super().dispatch(*args, **kwargs)


class APILogMixin:
    """
    Mixin to log API requests and responses.
    """
    def initial(self, request, *args, **kwargs):
        """
        Log request details.
        """
        if not settings.DEBUG:
            logger.info(
                f"API request: {request.method} {request.path} by {request.user}"
            )
        return super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        """
        Log response details.
        """
        response = super().finalize_response(request, response, *args, **kwargs)
        if not settings.DEBUG and response.status_code >= 400:
            logger.warning(
                f"API error: {request.method} {request.path} "
                f"returned {response.status_code} for {request.user}"
            )
        return response


class MultiSerializerMixin:
    """
    Mixin to use different serializers for different actions.
    """
    serializer_classes = {}

    def get_serializer_class(self):
        """
        Return the serializer class for this view.
        """
        if self.action in self.serializer_classes:
            return self.serializer_classes[self.action]
        return super().get_serializer_class()


class PermissionsMixin:
    """
    Mixin to use different permissions for different actions.
    """
    permission_classes_by_action = {}

    def get_permissions(self):
        """
        Return the permissions for this view based on the action.
        """
        if self.action in self.permission_classes_by_action:
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        return super().get_permissions()


class QuerySetMixin:
    """
    Mixin to use different querysets for different actions.
    """
    queryset_by_action = {}

    def get_queryset(self):
        """
        Return the queryset for this view based on the action.
        """
        if self.action in self.queryset_by_action:
            return self.queryset_by_action[self.action]()
        return super().get_queryset()
