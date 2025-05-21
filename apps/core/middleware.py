"""
Custom middleware for DZ Bus Tracker.
"""
import logging
import time
import uuid

from django.conf import settings
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RequestLogMiddleware(MiddlewareMixin):
    """
    Middleware to log requests and their processing time.
    """

    def process_request(self, request):
        """
        Process the request.
        """
        request.id = str(uuid.uuid4())
        request.start_time = time.time()

    def process_response(self, request, response):
        """
        Process the response.
        """
        if hasattr(request, "start_time"):
            processing_time = time.time() - request.start_time
            status_code = response.status_code
            method = request.method
            path = request.path
            user = getattr(request, "user", None)
            user_id = getattr(user, "id", "anonymous")

            if processing_time > 1.0:  # Log slow requests (> 1 second)
                logger.warning(
                    f"Request {request.id}: {method} {path} by {user_id} "
                    f"took {processing_time:.2f}s (status: {status_code})"
                )
            elif not settings.DEBUG and status_code >= 400:  # Log errors in non-debug mode
                logger.warning(
                    f"Request {request.id}: {method} {path} by {user_id} "
                    f"returned {status_code} in {processing_time:.2f}s"
                )
            elif settings.DEBUG and processing_time > 0.1:  # Log normal requests in debug mode
                logger.debug(
                    f"Request {request.id}: {method} {path} by {user_id} "
                    f"took {processing_time:.2f}s (status: {status_code})"
                )

        return response


class LocaleMiddleware(MiddlewareMixin):
    """
    Custom locale middleware that sets the language based on user preferences.
    """

    def process_request(self, request):
        """
        Process the request.
        """
        user = getattr(request, "user", None)

        if user and user.is_authenticated and hasattr(user, "profile"):
            # Use user's preferred language if available
            user_language = getattr(user.profile, "language", None)
            if user_language:
                translation.activate(user_language)
                request.LANGUAGE_CODE = user_language
        else:
            # Check if language is in session or use Accept-Language header
            language = request.session.get("django_language", None)
            if language:
                translation.activate(language)
                request.LANGUAGE_CODE = language
