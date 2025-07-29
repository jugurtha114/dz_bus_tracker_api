"""
Custom middleware for DZ Bus Tracker.
"""
import logging
import time
import uuid
from urllib.parse import parse_qs

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode

logger = logging.getLogger(__name__)
User = get_user_model()


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


class JwtAuthMiddleware(BaseMiddleware):
    """
    JWT authentication middleware for Django Channels WebSocket connections.
    Extracts JWT token from query parameters and authenticates the user.
    """
    
    async def __call__(self, scope, receive, send):
        """
        Process WebSocket connection and authenticate user via JWT token.
        """
        # Only process WebSocket connections
        if scope['type'] != 'websocket':
            return await self.inner(scope, receive, send)
        
        # Extract token from query parameters
        query_string = scope.get('query_string', b'').decode('utf-8')
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]
        
        logger.info(f"JWT Middleware: Query string: {query_string}")
        logger.info(f"JWT Middleware: Token found: {'Yes' if token else 'No'}")
        if token:
            logger.info(f"JWT Middleware: Token starts with: {token[:20]}...")
        
        # Set default user as anonymous
        scope['user'] = AnonymousUser()
        
        if token:
            try:
                # Validate JWT token
                validated_token = UntypedToken(token)
                
                # Get user ID from token
                user_id = validated_token['user_id']
                
                # Fetch user from database
                user = await self.get_user_by_id(user_id)
                if user and user.is_active:
                    scope['user'] = user
                    logger.info(f"JWT authentication successful for user {user.email} (ID: {user_id})")
                else:
                    logger.warning(f"JWT token valid but user not found or inactive: {user_id}")
                    
            except (InvalidToken, TokenError, KeyError) as e:
                logger.warning(f"JWT authentication failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during JWT authentication: {e}")
        
        return await self.inner(scope, receive, send)
    
    @database_sync_to_async
    def get_user_by_id(self, user_id):
        """
        Get user by ID from database.
        
        Args:
            user_id: The user ID from JWT token
            
        Returns:
            User instance or None if not found
        """
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None


def JwtAuthMiddlewareStack(inner):
    """
    Middleware stack that includes JWT authentication for WebSocket connections.
    """
    return JwtAuthMiddleware(inner)
