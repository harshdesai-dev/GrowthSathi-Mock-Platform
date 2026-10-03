"""Fail closed before opening a production listener; never echo configuration values."""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_production(env, database):
    def required(name):
        value = env.get(name, "").strip()
        if not value:
            raise ImproperlyConfigured(f"{name} must be set in production.")
        return value

    def reject(message):
        raise ImproperlyConfigured(message)

    if required("DJANGO_DEBUG").lower() not in {"false", "0", "no", "off"}:
        reject("DJANGO_DEBUG must explicitly be false in production.")
    for name, minimum in (("DJANGO_SECRET_KEY", 50), ("JWT_SECRET", 50)):
        value = required(name)
        if (
            len(value) < minimum
            or len(set(value)) < 10
            or any(
                marker in value.lower() for marker in ("replace", "development-only", "change-me")
            )
        ):
            reject(f"{name} must be an independent, strong random secret (50+ characters).")
    if env["JWT_SECRET"] == env["DJANGO_SECRET_KEY"]:
        reject("JWT_SECRET must differ from DJANGO_SECRET_KEY.")
    required("DATABASE_URL")
    if database["ENGINE"] != "django.db.backends.postgresql":
        reject("Production requires PostgreSQL.")
    if database.get("OPTIONS", {}).get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        reject("DATABASE_URL must require PostgreSQL TLS (sslmode=require or verify-full).")

    hosts = [host.strip() for host in required("DJANGO_ALLOWED_HOSTS").split(",")]
    if any(
        not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", host)
        or host.startswith(".")
        or host in {"localhost", "127.0.0.1"}
        for host in hosts
    ):
        reject("DJANGO_ALLOWED_HOSTS must contain exact deployed hostnames, without wildcards.")

    def origin(value, name):
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.hostname not in {"localhost", "127.0.0.1"}
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and "*" not in value
                and parsed.port in {None, 443}
            )
        except ValueError:
            valid = False
        if not valid:
            reject(f"{name} must contain exact HTTPS origins, with no path or trailing slash.")

    frontend = required("FRONTEND_URL")
    origin(frontend, "FRONTEND_URL")
    for name in ("CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS"):
        origins = [item.strip() for item in required(name).split(",")]
        for item in origins:
            origin(item, name)
        if frontend not in origins:
            reject(f"{name} must include FRONTEND_URL exactly.")
    if not required("GOOGLE_CLIENT_ID").endswith(".apps.googleusercontent.com"):
        reject("GOOGLE_CLIENT_ID must identify a Google OAuth Web client.")
    if not required("RAZORPAY_KEY_ID").startswith("rzp_test_"):
        reject("Only Razorpay TEST keys are allowed; live payments remain blocked.")
    for name in ("RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        value = required(name)
        if len(value) < 16 or "replace" in value.lower():
            reject(f"{name} must be configured with a non-placeholder secret.")
    if env["RAZORPAY_WEBHOOK_SECRET"] == env["RAZORPAY_KEY_SECRET"]:
        reject("Use a separate RAZORPAY_WEBHOOK_SECRET.")
    for name in ("AUTH_REFRESH_COOKIE_SAMESITE", "CSRF_COOKIE_SAMESITE"):
        if env.get(name, "Lax") not in {"Lax", "Strict", "None"}:
            reject(f"{name} must be Lax, Strict or None.")
    # API-host-only cookies are sufficient: CSRF bootstrap returns the token in JSON.
    for name in ("AUTH_REFRESH_COOKIE_DOMAIN", "CSRF_COOKIE_DOMAIN"):
        if env.get(name):
            reject(f"Leave {name} empty to keep cookies scoped to the API host.")
    if env.get("MEDIA_STORAGE_CONFIG"):
        reject("MEDIA_STORAGE_CONFIG is not implemented; use durable external HTTPS image URLs.")
    if required("DJANGO_TRUST_PROXY_HEADERS").lower() != "true":
        reject(
            "Confirm a trusted, header-sanitizing HTTPS proxy with DJANGO_TRUST_PROXY_HEADERS=true."
        )
    try:
        if not 0 <= int(required("TRUSTED_PROXY_COUNT")) <= 5:
            raise ValueError
        if not 1 <= int(env.get("AUTH_ACCESS_TOKEN_MINUTES", "5")) <= 15:
            raise ValueError
        if not 1 <= int(env.get("AUTH_REFRESH_TOKEN_DAYS", "7")) <= 14:
            raise ValueError
    except ValueError:
        reject("Invalid proxy count or token lifetime (access 1-15 minutes, refresh 1-14 days).")
