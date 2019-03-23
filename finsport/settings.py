import os
import environ
import socket
import json

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
    'debug_toolbar',
    'bootstrap3',
    'django_extensions',
    'django_countries',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
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

LANGUAGE_CODE = 'es-pe'

TIME_ZONE = 'America/Lima'

MEDIA_ROOT = '%s/media/' % str(root - 1)

MEDIA_URL = '/media/'

STATIC_ROOT = '%s/static/' % str(root - 1)

STATIC_URL = '/static/'

SELENIUM_DATA = env('SELENIUM_DATA')

ENV_FOLDER = env('ENV_FOLDER')

ENVIRONMENTS = json.loads(env('ENVIRONMENTS'))

DB_BACKUP_DIR = os.path.join(BASE_DIR, '../backups/')

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_USE_TLS = True

EMAIL_HOST = 'smtp.gmail.com'

EMAIL_PORT = 587
# TODO: Credentials will be saved on the .env file
EMAIL_HOST_USER = 'luisjarufe@gmail.com'

EMAIL_HOST_PASSWORD = 'Elchocloamarillo7'

INSTANCE_DOMAIN = env('INSTANCE_DOMAIN')

DATE_FORMAT = "%d de %B del %Y, %H:%M"

DEFAULT_FROM_EMAIL = 'luisjarufe@gmail.com'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
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
            'formatter': 'console',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filters': ['require_debug_false'],
            'filename': '../logs/file.log',
        },
    },
    'loggers': {
        'get_matches': {
            'handlers': ['console', 'file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
        },
    },
}
