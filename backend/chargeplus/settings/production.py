from .base import *

DEBUG = False

# Security settings
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = False  # SSL termination at nginx
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Production logging: also log to file
LOGGING['handlers']['file'] = {
    'class': 'logging.handlers.RotatingFileHandler',
    'filename': BASE_DIR / 'logs' / 'chargeplus.log',
    'maxBytes': 10 * 1024 * 1024,
    'backupCount': 10,
    'formatter': 'verbose',
}
LOGGING['root']['handlers'] = ['console', 'file']
LOGGING['loggers']['apps']['handlers'] = ['console', 'file']
