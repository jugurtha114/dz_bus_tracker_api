"""
Core middleware for the DZ Bus Tracker application.
"""
from .url_normalize import URLNormalizeMiddleware
from .http_debug import DebugRequestLogMiddleware
from .locale import LocaleMiddleware

# JWT middleware depends on channels + simplejwt — import lazily to avoid
# issues when channels is not in the import path (e.g. WSGI-only context).
# Direct import: from apps.core.middleware.jwt_auth import JwtAuthMiddlewareStack
try:
    from .jwt_auth import JwtAuthMiddleware, JwtAuthMiddlewareStack
except ImportError:
    JwtAuthMiddleware = None
    JwtAuthMiddlewareStack = None

__all__ = [
    'URLNormalizeMiddleware',
    'DebugRequestLogMiddleware',
    'LocaleMiddleware',
    'JwtAuthMiddleware',
    'JwtAuthMiddlewareStack',
]
