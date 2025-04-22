from .base import *  # noqa

# DEBUG
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY", "django-insecure-development-key-for-local-use-only")

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

# DATABASES
# ------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env.str("POSTGRES_DB", "dz_bus_tracker"),
        "USER": env.str("POSTGRES_USER", "postgres"),
        "PASSWORD": env.str("POSTGRES_PASSWORD", "postgres"),
        "HOST": env.str("DATABASE_HOST", "db"),
        "PORT": env.str("DATABASE_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
    }
}

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env.str("REDIS_URL", "redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# EMAIL
# ------------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# django-debug-toolbar
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["debug_toolbar"]  # noqa F405
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa F405
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": ["debug_toolbar.panels.redirects.RedirectsPanel"],
    "SHOW_TEMPLATE_CONTEXT": True,
}
INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]

# Additional local-only apps
INSTALLED_APPS += ["django_extensions"]  # noqa F405

# CELERY
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True

# LOGGING
# ------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "django.db.backends": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "apps": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
    },
}