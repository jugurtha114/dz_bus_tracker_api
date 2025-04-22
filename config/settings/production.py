from .base import *  # noqa

# SECURITY
DEBUG = False
SECRET_KEY = env.str("SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["dzbustracker.com", "www.dzbustracker.com"])

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# STATIC FILES
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# MIDDLEWARE
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # Insert after security middleware

# DATABASES
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env.str("POSTGRES_DB"),
        "USER": env.str("POSTGRES_USER"),
        "PASSWORD": env.str("POSTGRES_PASSWORD"),
        "HOST": env.str("DATABASE_HOST", "db"),
        "PORT": env.str("DATABASE_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 60,  # 1 minute connection persistence
    }
}

# CACHES
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env.str("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "PASSWORD": env.str("REDIS_PASSWORD", ""),
        },
    }
}

# EMAIL
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env.str("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL")

# LOGGING
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "propagate": True,
        },
        "django.db.backends": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        "apps": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
}

# Sentry
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=True,
        environment="production",
    )

# CELERY
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BROKER_USE_SSL = True
CELERY_REDIS_BACKEND_USE_SSL = True
