import os
import socket
import mimetypes

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

CORS_ORIGIN_WHITELIST = env.list("CORS_ORIGIN_WHITELIST", default=[])

CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # local apps
    "football",
    "bet",
    "accounts",
    # third parties
    "django_extensions",
    "django_countries",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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

SELENIUM_URL = "http://selenium:4444/wd/hub"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_USE_TLS = True

EMAIL_HOST = env("EMAIL_HOST", default="localhost")

EMAIL_PORT = env("EMAIL_PORT", default=25)

EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")

EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

INSTANCE_DOMAIN = env("INSTANCE_DOMAIN")

DATE_FORMAT = "%d de %B del %Y, %H:%M"

DEFAULT_FROM_EMAIL = "luisjarufe@gmail.com"

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
    "formatters": {
        "all": {
            "format": "%(levelname)s %(asctime).16s: %(message)s",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["require_debug_true"],
            "formatter": "all",
        },
        "get_matches_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/get_matches.log"),
            "formatter": "all",
        },
        "fill_tables_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/fill_tables.log"),
            "formatter": "all",
        },
        "make_bets_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/make_bets.log"),
            "formatter": "all",
        },
        "inkabet_results_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/inkabet_results.log"),
            "formatter": "all",
        },
        "leagues_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/leagues.log"),
            "formatter": "all",
        },
        "scrapy_extra_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filters": ["require_debug_false"],
            "filename": os.path.join(BASE_DIR, "logs/scrapy.log"),
            "formatter": "all",
        },
    },
    "loggers": {
        "get_matches": {
            "handlers": ["console", "get_matches_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "fill_tables": {
            "handlers": ["console", "fill_tables_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "make_bets": {
            "handlers": ["console", "make_bets_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "inkabet_results": {
            "handlers": ["console", "inkabet_results_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "leagues": {
            "handlers": ["console", "leagues_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "scrapy_extra": {
            "handlers": ["console", "scrapy_extra_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
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

if DEBUG:
    CRAWLER_OPTIONS = {
        "USER_AGENT": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)",
        "LOG_ENABLED": True,
        "LOG_FORMAT": "%(levelname)s [%(name)s] %(asctime).16s: %(message)s",
        "LOG_LEVEL": "WARNING",
    }
else:
    CRAWLER_OPTIONS = {
        "USER_AGENT": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)",
        "LOG_ENABLED": True,
        "LOG_FILE": os.path.join(BASE_DIR, "logs/scrapy.log"),
        "LOG_FORMAT": "%(levelname)s [%(name)s] %(asctime).16s: %(message)s",
        "LOG_LEVEL": "ERROR",
    }

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Celery configuration
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "redis://redis:6379/1"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_WORKER_CONCURRENCY = 2
if DEBUG:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
