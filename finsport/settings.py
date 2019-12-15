import os
import environ
import socket

from django.utils.translation import ugettext_lazy as _

root = environ.Path(__file__) - 2
env = environ.Env()
environ.Env.read_env('%s/.env' % str(root - 1))

SITE_ROOT = root()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = env('SECRET_KEY')

DEBUG = env('DEBUG', default=False)

try:
    HOSTNAME = socket.gethostname()
except ValueError:
    HOSTNAME = 'localhost:8000'

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

DATABASES = {'default': env.db()}

CORS_ORIGIN_WHITELIST = env.list('CORS_ORIGIN_WHITELIST', default=[])

CORS_ALLOW_CREDENTIALS = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    # local apps
    'football',
    'bet',
    'accounts',
    # third parties
    'django_extensions',
    'django_countries',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.locale.LocaleMiddleware',
]

ROOT_URLCONF = 'finsport.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'finsport.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGES = (
    ('en-us', 'English'),
    ('es-pe', 'Spanish'),
)

LANGUAGE_CODE = 'en-us'

LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)

TIME_ZONE = 'America/Lima'

MEDIA_ROOT = '%s/media/' % str(root - 1)

MEDIA_URL = '/media/'

STATIC_ROOT = '%s/static/' % str(root - 1)

STATIC_URL = '/static/'

SELENIUM_DATA = env('SELENIUM_DATA')

ENV_FOLDER = env('ENV_FOLDER')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_USE_TLS = True

EMAIL_HOST = env('EMAIL_HOST')

EMAIL_PORT = 587

EMAIL_HOST_USER = env('EMAIL_HOST_USER')

EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')

INSTANCE_DOMAIN = env('INSTANCE_DOMAIN')

DATE_FORMAT = "%d de %B del %Y, %H:%M"

DEFAULT_FROM_EMAIL = 'luisjarufe@gmail.com'

COUNTRIES_OVERRIDE = {
    'EN': _('England'),
    'CT': _('Scotland'),
    'WA': _('Wales'),
    'ND': _('Northern Ireland'),
    'US': _('USA'),
    'CZ': _('Czech Rep.'),
    'KR': _('Korea'),
    'BA': _('Bosnia-Herzegovina'),
    'SA': _('Saudi Arabia'),
    'CY': _('Cyprus'),
    'NL': _('Netherlands'),
    'MK': _('Macedonia'),
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'all': {
            'format': '%(levelname)s %(asctime).16s: %(message)s',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['require_debug_true'],
            'formatter': 'all',
        },
        'get_matches_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': os.path.join(BASE_DIR, '../logs/get_matches.log'),
            'formatter': 'all',
        },
        'fill_tables_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': os.path.join(BASE_DIR, '../logs/fill_tables.log'),
            'formatter': 'all',
        },
        'make_bets_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': os.path.join(BASE_DIR, '../logs/make_bets.log'),
            'formatter': 'all',
        },
        'inkabet_results_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': os.path.join(BASE_DIR, '../logs/inkabet_results.log'),
            'formatter': 'all',
        },
        'leagues_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': os.path.join(BASE_DIR, '../logs/leagues.log'),
            'formatter': 'all',
        },
    },
    'loggers': {
        'get_matches': {
            'handlers': ['console', 'get_matches_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'fill_tables': {
            'handlers': ['console', 'fill_tables_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'make_bets': {
            'handlers': ['console', 'make_bets_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'inkabet_results': {
            'handlers': ['console', 'inkabet_results_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
        'leagues': {
            'handlers': ['console', 'leagues_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
    },
}

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS':
        'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,
}

if DEBUG:
    CRAWLER_OPTIONS = {
        'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
        'LOG_ENABLED': True,
        'LOG_FORMAT': '%(levelname)s [%(name)s] %(asctime).16s: %(message)s',
        'LOG_LEVEL': 'WARNING',
    }
else:
    CRAWLER_OPTIONS = {
        'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)',
        'LOG_ENABLED': True,
        'LOG_FILE': os.path.join(BASE_DIR, '../logs/scrapy.log'),
        'LOG_FORMAT': '%(levelname)s [%(name)s] %(asctime).16s: %(message)s',
        'LOG_LEVEL': 'ERROR',
    }
