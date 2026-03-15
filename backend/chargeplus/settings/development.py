from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# Development: use console email backend
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# More verbose logging in development
LOGGING['root']['level'] = 'DEBUG'
LOGGING['loggers']['apps']['level'] = 'DEBUG'

# Django debug toolbar (optional, install separately)
# INSTALLED_APPS += ['debug_toolbar']

# Allow all origins for CORS in development (if django-cors-headers installed)
# CORS_ALLOW_ALL_ORIGINS = True
