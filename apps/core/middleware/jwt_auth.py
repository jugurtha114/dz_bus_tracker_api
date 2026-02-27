"""
JWT authentication middleware for Django Channels WebSocket connections.
"""
import logging
from urllib.parse import parse_qs

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)
User = get_user_model()


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
