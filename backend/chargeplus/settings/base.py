import os
from datetime import timedelta
from pathlib import Path
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost').split(',')
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'django_celery_beat',
    # Local apps
    'apps.config',
    'apps.users',
    'apps.stations',
    'apps.authorization',
    'apps.transactions',
    'apps.reservations',
    'apps.smart_charging',
    'apps.ocpp16',
    'apps.mobile_api',
    'apps.portal',
    'apps.payment',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'chargeplus.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'chargeplus.wsgi.application'

# Database - PostgreSQL
_database_url = os.environ.get('DATABASE_URL', 'postgresql://chargeplus:chargeplus@db:5432/chargeplus')

def _parse_db_url(url: str) -> dict:
    """Simple DATABASE_URL parser."""
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username,
        'PASSWORD': parsed.password,
        'HOST': parsed.hostname,
        'PORT': str(parsed.port or 5432),
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }

DATABASES = {
    'default': _parse_db_url(_database_url)
}

# Redis Cache
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'RETRY_ON_TIMEOUT': True,
        },
        'TIMEOUT': 300,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Custom user model
AUTH_USER_MODEL = 'users.User'

# Internationalization
LANGUAGE_CODE = 'ko'

LANGUAGES = [
    ('ko', _('한국어')),
    ('en', _('English')),
    ('vi', _('Tiếng Việt')),
]

TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Portal session auth
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# --- Django REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# --- Simple JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=int(os.environ.get('JWT_ACCESS_TOKEN_LIFETIME_HOURS', 24))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# --- Celery ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/1')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/2')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Task routing to dedicated queues
CELERY_TASK_ROUTES = {
    'apps.ocpp16.tasks.core.*': {'queue': 'ocpp.q.core'},
    'apps.ocpp16.tasks.telemetry.*': {'queue': 'ocpp.q.telemetry'},
    'apps.ocpp16.tasks.management.*': {'queue': 'ocpp.q.management'},
    'apps.ocpp16.tasks.commands.*': {'queue': 'ocpp.q.commands'},
    'apps.payment.tasks.*': {'queue': 'ocpp.q.commands'},
}

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_QUEUES_DEFAULT = 'default'

# Periodic tasks (django-celery-beat)
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'cleanup-ocpp-messages-daily': {
        'task': 'apps.ocpp16.tasks.management.cleanup_ocpp_messages',
        'schedule': crontab(hour=3, minute=0),  # 매일 새벽 3시
        'options': {'queue': 'ocpp.q.management'},
    },
}

# Define queues
from kombu import Queue
CELERY_TASK_QUEUES = (
    Queue('ocpp.q.core'),
    Queue('ocpp.q.telemetry'),
    Queue('ocpp.q.management'),
    Queue('ocpp.q.commands'),
    Queue('default'),
)

# --- Logging ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'chargeplus.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
_logs_dir = BASE_DIR / 'logs'
_logs_dir.mkdir(exist_ok=True)

# --- MB Paygate ---
MB_SECRET_KEY  = os.environ.get('MB_SECRET_KEY', '')
MB_ACCESS_CODE = os.environ.get('MB_ACCESS_CODE', '')
MB_MERCHANT_ID = os.environ.get('MB_MERCHANT_ID', '')
MB_SANDBOX     = os.environ.get('MB_SANDBOX', 'true') == 'true'
MB_IPN_URL     = os.environ.get('MB_IPN_URL', 'https://chargeplus.kr/api/payment/ipn/')
MB_RETURN_URL  = os.environ.get('MB_RETURN_URL', 'https://chargeplus.kr/api/payment/return/')
MB_CANCEL_URL  = os.environ.get('MB_CANCEL_URL', 'https://chargeplus.kr/api/payment/cancel/')
MB_PREPAID_AMOUNT = int(os.environ.get('MB_PREPAID_AMOUNT', '100000'))
