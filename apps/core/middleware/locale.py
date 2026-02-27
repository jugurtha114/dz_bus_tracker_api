"""
Custom locale middleware that sets the language based on user preferences.
"""
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


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
