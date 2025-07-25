"""
Test settings for DZ Bus Tracker.
"""
from .base import *  # noqa

# Remove GIS app for testing
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'django.contrib.gis']

# GENERAL
DEBUG = False
SECRET_KEY = "test-secret-key-for-testing-only"
ALLOWED_HOSTS = ["*"]

# DATABASES
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="dz_bus_tracker_db"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default="postgres"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
    }
}

# CACHES
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    }
}

# EMAIL
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# MEDIA
MEDIA_ROOT = str(ROOT_DIR / "test_media")

# STATIC FILES
STATIC_ROOT = str(ROOT_DIR / "test_static")
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# CELERY
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# PASSWORDS
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",  # Fast for testing
]

# TEMPLATES
TEMPLATES[0]["OPTIONS"]["debug"] = True  # noqa F405

# TESTING
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

if env.bool("DISABLE_MIGRATIONS", default=False):
    MIGRATION_MODULES = DisableMigrations()