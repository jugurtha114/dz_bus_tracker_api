"""
ASGI config for DZ Bus Tracker project.
"""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path, re_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from apps.tracking.consumers import TrackingConsumer
# Import from the middleware.py file, not the middleware directory
import importlib.util
import os
middleware_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'apps', 'core', 'middleware.py')
spec = importlib.util.spec_from_file_location("core_middleware", middleware_path)
core_middleware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core_middleware)
JwtAuthMiddlewareStack = core_middleware.JwtAuthMiddlewareStack

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JwtAuthMiddlewareStack(
        URLRouter([
            re_path(r"^ws/?$", TrackingConsumer.as_asgi()),
        ])
    ),
})
