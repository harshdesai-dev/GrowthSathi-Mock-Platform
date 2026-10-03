import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.sessions import rotate_session
from apps.common.api.exceptions import api_exception_handler
from apps.common.observability import RequestContextMiddleware, SafeJsonFormatter
from apps.common.throttles import OrderThrottle
from config.production_validation import validate_production


def production_env():
    # Synthetic values only; validation must never print any of them.
    return {
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "synthetic-django-abcdefghijklmnopqrstuvwxyz-0123456789-ABCDEFG",
        "JWT_SECRET": "synthetic-jwt-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789-abcdefghi",
        "DATABASE_URL": "postgresql://synthetic.invalid/db?sslmode=require",
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "FRONTEND_URL": "https://app.example.com",
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "CSRF_TRUSTED_ORIGINS": "https://app.example.com",
        "GOOGLE_CLIENT_ID": "synthetic.apps.googleusercontent.com",
        "RAZORPAY_KEY_ID": "rzp_test_synthetic",
        "RAZORPAY_KEY_SECRET": "synthetic-payment-secret",
        "RAZORPAY_WEBHOOK_SECRET": "synthetic-webhook-secret",
        "DJANGO_TRUST_PROXY_HEADERS": "true",
        "TRUSTED_PROXY_COUNT": "1",
    }


def production_db():
    return {"ENGINE": "django.db.backends.postgresql", "OPTIONS": {"sslmode": "require"}}


def test_valid_production_configuration():
    validate_production(production_env(), production_db())


@pytest.mark.parametrize("missing", list(production_env()))
def test_missing_production_configuration_fails_closed(missing):
    env = production_env()
    env.pop(missing)
    with pytest.raises(ImproperlyConfigured):
        validate_production(env, production_db())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DJANGO_DEBUG", "true"),
        ("DJANGO_SECRET_KEY", "replace-with-a-long-random-value"),
        ("JWT_SECRET", production_env()["DJANGO_SECRET_KEY"]),
        ("DJANGO_ALLOWED_HOSTS", "*"),
        ("DJANGO_ALLOWED_HOSTS", ".example.com"),
        ("DJANGO_ALLOWED_HOSTS", "https://api.example.com"),
        ("FRONTEND_URL", "http://app.example.com"),
        ("FRONTEND_URL", "https://app.example.com/"),
        ("CORS_ALLOWED_ORIGINS", "https://evil.example.com"),
        ("CSRF_TRUSTED_ORIGINS", "https://*.example.com"),
        ("RAZORPAY_KEY_ID", "rzp_live_blocked"),
        ("RAZORPAY_WEBHOOK_SECRET", production_env()["RAZORPAY_KEY_SECRET"]),
        ("AUTH_REFRESH_COOKIE_SAMESITE", "Invalid"),
        ("AUTH_REFRESH_COOKIE_DOMAIN", ".example.com"),
        ("MEDIA_STORAGE_CONFIG", "local"),
        ("DJANGO_TRUST_PROXY_HEADERS", "false"),
        ("TRUSTED_PROXY_COUNT", "99"),
        ("AUTH_ACCESS_TOKEN_MINUTES", "60"),
        ("AUTH_REFRESH_TOKEN_DAYS", "365"),
    ],
)
def test_unsafe_production_configuration_is_rejected_without_values(key, value):
    env = {**production_env(), key: value}
    with pytest.raises(ImproperlyConfigured) as exc:
        validate_production(env, production_db())
    assert env["RAZORPAY_KEY_SECRET"] not in str(exc.value)
    assert env["JWT_SECRET"] not in str(exc.value)


@pytest.mark.parametrize(
    "database",
    [
        {"ENGINE": "django.db.backends.sqlite3"},
        {"ENGINE": "django.db.backends.postgresql", "OPTIONS": {}},
    ],
)
def test_production_requires_postgresql_and_tls(database):
    with pytest.raises(ImproperlyConfigured):
        validate_production(production_env(), database)


def test_unknown_error_is_safe_json(settings):
    settings.DEBUG = False
    response = api_exception_handler(RuntimeError("SQL secret-token student@example.com"), {})
    assert response.status_code == 500
    assert response.data["error"]["code"] == "server_error"
    assert "secret-token" not in str(response.data)


def test_production_logging_omits_framework_messages_exception_values_and_request():
    try:
        raise RuntimeError("token=secret database-password student@example.com")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "django.request", 40, __file__, 1, "secret-path", (), sys.exc_info()
        )
    record.request = {"Authorization": "Bearer secret"}
    output = SafeJsonFormatter().format(record)
    assert "secret" not in output and "student@example.com" not in output
    assert json.loads(output)["exception_type"] == "RuntimeError"
    assert json.loads(output)["frames"]


def test_sensitive_responses_and_health_are_never_cached(client):
    for path in ("/api/v1/auth/csrf/", "/api/v1/health/live/", "/api/v1/auth/me/"):
        response = client.get(path)
        assert response["Cache-Control"] == "private, no-store"
        assert len(response["X-Request-ID"]) == 32


def test_request_id_is_generated_not_trusted_from_client():
    middleware = RequestContextMiddleware(lambda request: HttpResponse("ok"))
    response = middleware(RequestFactory().get("/api/v1/health/live/", HTTP_X_REQUEST_ID="secret"))
    assert response["X-Request-ID"] != "secret"


def test_readiness_failure_is_503_and_liveness_stays_up(client):
    with patch(
        "django.db.backends.base.base.BaseDatabaseWrapper.cursor",
        side_effect=OperationalError("secret"),
    ):
        assert client.get("/api/v1/health/live/").status_code == 200
        response = client.get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert "secret" not in response.content.decode()


def test_order_throttle_returns_retry_after_without_using_autosave_bucket():
    from apps.attempts.api import ExamThrottle

    class Limited(APIView):
        authentication_classes = []
        throttle_classes = [OrderThrottle]

        def post(self, request):
            from rest_framework.response import Response

            return Response({"ok": True})

    cache.clear()
    try:
        factory = APIRequestFactory()
        for _ in range(10):
            assert Limited.as_view()(factory.post("/")).status_code == 200
        response = Limited.as_view()(factory.post("/"))
        assert response.status_code == 429
        assert int(response["Retry-After"]) > 0
        assert ExamThrottle.scope != OrderThrottle.scope
        assert ExamThrottle.rate == "600/min"
    finally:
        cache.clear()


def test_google_login_cannot_be_forced_by_cross_site_form():
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/v1/auth/google/", {"credential": "attacker-token"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert "growthsathi_refresh" not in response.cookies


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_reuse_has_exactly_one_winner():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    user = User.objects.create_user(email="refresh-race@example.com", google_sub="refresh-race")
    token = str(RefreshToken.for_user(user))
    barrier = Barrier(2)

    def rotate():
        try:
            barrier.wait(timeout=10)
            rotate_session(token)
            return "rotated"
        except TokenError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(results) == ["rejected", "rotated"]
