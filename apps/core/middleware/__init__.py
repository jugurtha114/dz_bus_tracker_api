"""
Core middleware for the DZ Bus Tracker application.
"""

from .url_normalize import URLNormalizeMiddleware

__all__ = ['URLNormalizeMiddleware']