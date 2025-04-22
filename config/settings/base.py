import os
from datetime import timedelta
from pathlib import Path

import environ

# Build paths inside the project
ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
APPS_DIR = ROOT_DIR / "apps"

# Environment variables
env = environ.Env()
if os.path.exists(ROOT_DIR / ".env"):
    env.read_env(str(ROOT_DIR / ".env"))


# GENERAL
DEBUG = env.bool("DJANGO_DEBUG", False)
TIME_ZONE = "Africa/Algiers"
LANGUAGE_CODE = "fr-fr"
LANGUAGES = [
    ("fr", "French"),
    ("ar", "Arabic"),
    ("en", "English"),
]
LANGUAGE_COOKIE_NAME = "dz_bus_tracker_language"
SITE_ID = 1
USE_I18N = True
USE_L10N = True
USE_TZ = True
LOCALE_PATHS = [ROOT_DIR / "locale"]

# DATABASES
DATABASES = {
    "default": env.db(
        "DATABASE_URL", 
        default="postgres://postgres:postgres@0.0.0.0:5432/dz_bus_tracker_db"
    ),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# APPS
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.gis",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "modeltranslation",
]

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.authentication.apps.AuthenticationConfig",
    "apps.drivers.apps.DriversConfig",
    "apps.buses.apps.BusesConfig",
    "apps.lines.apps.LinesConfig",
    "apps.schedules.apps.SchedulesConfig",
    "apps.tracking.apps.TrackingConfig",
    "apps.passengers.apps.PassengersConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.eta.apps.ETAConfig",
    "apps.analytics.apps.AnalyticsConfig",
    "apps.feedback.apps.FeedbackConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# AUTHENTICATION
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_USER_MODEL = "authentication.User"

# PASSWORDS
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# STATIC
STATIC_ROOT = str(ROOT_DIR / "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [str(APPS_DIR / "static")]
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
MEDIA_ROOT = str(APPS_DIR / "media")
MEDIA_URL = "/media/"

# TEMPLATES
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# SECURITY
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# EMAIL
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_TIMEOUT = 5

# CACHING
REDIS_URL = env.str("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
        },
    }
}

# CELERY
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json", "msgpack"]
CELERY_TASK_SERIALIZER = "msgpack"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 5 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True

# REST FRAMEWORK
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "100/hour", "user": "1000/hour"},
    "DEFAULT_RENDERER_CLASSES": [
        "utils.serialization.ORJSONRenderer",
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "utils.serialization.ORJSONParser",
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

DEBUG_TOOLBAR_PANELS =[]

# SPECTACULAR SETTINGS
SPECTACULAR_SETTINGS = {
    "TITLE": "DZ Bus Tracker API",
    "DESCRIPTION": "API documentation for DZ Bus Tracker",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    "COMPONENT_SPLIT_REQUEST": True,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# JWT SETTINGS
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=env.int("ACCESS_TOKEN_LIFETIME", default=3600)),  # 1 hour
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=env.int("REFRESH_TOKEN_LIFETIME", default=604800)),  # 7 days
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env.str("JWT_SECRET_KEY", default=None),
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
}

# CORS SETTINGS
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:8000", "http://localhost:3000"]
)
CORS_ALLOW_CREDENTIALS = True

# FIREBASE
FIREBASE_CREDENTIALS = env.str("FIREBASE_CREDENTIALS", default=None)

# TWILIO
TWILIO_ACCOUNT_SID = env.str("TWILIO_ACCOUNT_SID", default=None)
TWILIO_AUTH_TOKEN = env.str("TWILIO_AUTH_TOKEN", default=None)
TWILIO_FROM_NUMBER = env.str("TWILIO_FROM_NUMBER", default=None)

# GOOGLE MAPS
GOOGLE_MAPS_API_KEY = env.str("GOOGLE_MAPS_API_KEY", default=None)

# SENTRY
# SENTRY
SENTRY_DSN = env.str("SENTRY_DSN", default=None)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=True,
    )

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
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        "apps": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
    },
}



DEFAULT_FROM_EMAIL = "noreply@dzbustracker.com" # todo configure it later
FRONTEND_URL = env.str("FRONTEND_URL", default="http://localhost:3000")