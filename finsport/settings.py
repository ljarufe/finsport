import mimetypes
import os
import socket

import environ
from django.utils.translation import gettext_lazy as _

env = environ.Env(DEBUG=(bool, False))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

DEBUG = env("DEBUG")

SECRET_KEY = env("SECRET_KEY")

try:
    HOSTNAME = socket.gethostname()
except ValueError:
    HOSTNAME = "localhost:8000"

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

DATABASES = {
    "default": {
        "ENGINE": env(
            "DATABASE_ENGINE", default="django.db.backends.postgresql_psycopg2"
        ),
        "NAME": env("DATABASE_NAME", default="finsport"),
        "USER": env("DATABASE_USER", default="finsport"),
        "PASSWORD": env("DATABASE_PASSWORD"),
        "HOST": env("DATABASE_HOST", default="localhost"),
        "PORT": env("DATABASE_PORT", default="5432"),
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    # local apps
    "football",
    "bet",
    # third parties
    "django_countries",
    "django_extensions",
    "rest_framework",
    "rest_framework.authtoken",
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "finsport.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "finsport.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGES = (
    ("en-us", "English"),
    ("es-pe", "Spanish"),
)

LANGUAGE_CODE = "en-us"

LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"),)

TIME_ZONE = "America/Lima"

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

mimetypes.add_type("text/css", ".css", True)

DATE_FORMAT = "%d de %B del %Y, %H:%M"

# Keep the historic domestic-football distinctions that are not represented by
# ISO 3166 country codes but are meaningful to provider reconciliation.
COUNTRIES_OVERRIDE = {
    "EN": _("England"),
    "CT": _("Scotland"),
    "WA": _("Wales"),
    "ND": _("Northern Ireland"),
    "US": _("USA"),
    "CZ": _("Czech Rep."),
    "KR": _("Korea"),
    "BA": _("Bosnia-Herzegovina"),
    "SA": _("Saudi Arabia"),
    "CY": _("Cyprus"),
    "NL": _("Netherlands"),
    "MK": _("Macedonia"),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 10,
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Read-only API-Football boundary. The key is never logged or persisted.
API_FOOTBALL_KEY = env("API_FOOTBALL_KEY", default="")
API_FOOTBALL_BASE_URL = env(
    "API_FOOTBALL_BASE_URL", default="https://v3.football.api-sports.io/"
)
API_FOOTBALL_TIMEOUT = env.int("API_FOOTBALL_TIMEOUT", default=15)
API_FOOTBALL_DAILY_RESERVE = env.int("API_FOOTBALL_DAILY_RESERVE", default=0)
API_FOOTBALL_MAX_PAGES = env.int("API_FOOTBALL_MAX_PAGES", default=25)
API_FOOTBALL_MAX_RETRIES = env.int("API_FOOTBALL_MAX_RETRIES", default=2)
API_FOOTBALL_MINIMUM_INTERVAL = env.float("API_FOOTBALL_MINIMUM_INTERVAL", default=6.0)

# Read-only Inkabet JSON boundary. These values are local configuration, not
# browser/session credentials, and are never logged or persisted.
INKABET_BASE_URL = env(
    "INKABET_BASE_URL",
    default="https://d-cf.inkabetplayground.net/api/sb/v1/",
)
INKABET_BRAND_ID = env("INKABET_BRAND_ID", default="")
INKABET_MARKET_CODE = env("INKABET_MARKET_CODE", default="")
INKABET_TIMEOUT = env.int("INKABET_TIMEOUT", default=15)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://redis:6379/13",
    }
}

# Celery configuration
#
# The historical worker used Redis DB 0. Keep the local development worker on
# a dedicated broker database and queue so it cannot consume unknown legacy
# messages retained in the persistent Redis volume.
CELERY_BROKER_URL = "redis://redis:6379/14"
CELERY_RESULT_BACKEND = "redis://redis:6379/15"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_DEFAULT_QUEUE = "finsport.local.safe"
CELERY_WORKER_CONCURRENCY = 2
if DEBUG:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# Beat is intentionally available with no automatic jobs during the demo-only
# stage. The local Beat service uses Celery's file scheduler rather than the
# database scheduler, so persisted django-celery-beat rows cannot dispatch the
# historical betting cycle.
CELERY_BEAT_SCHEDULE = {}
