import os

from config.production_validation import validate_production

from .base import *  # noqa: F403

DEBUG = False

validate_production(os.environ, DATABASES["default"])  # noqa: F405

DATABASES["default"]["OPTIONS"].setdefault("connect_timeout", 5)  # noqa: F405
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES = {
    "default": {"BACKEND": "apps.common.storage.DisabledMediaStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
REST_FRAMEWORK["NUM_PROXIES"] = int(os.environ["TRUSTED_PROXY_COUNT"])  # noqa: F405
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_REFERRER_POLICY = "same-origin"

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
AUTH_REFRESH_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
AUTH_PASSWORD_VALIDATORS[1]["OPTIONS"] = {"min_length": 12}  # noqa: F405
LOGGING["handlers"]["console"]["formatter"] = "safe_json"  # noqa: F405
# Django's default error mail includes request/exception data. Use the scrubbed console only.
LOGGING["loggers"] = {  # noqa: F405
    "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
}
