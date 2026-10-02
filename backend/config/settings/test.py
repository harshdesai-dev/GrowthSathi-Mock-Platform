import os

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "SIGNING_KEY": "test-only-signing-key-at-least-thirty-two-bytes-long",
}

if not os.getenv("DATABASE_URL"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
