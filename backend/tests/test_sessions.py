import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import GoogleIdentity


@pytest.fixture
def logged_in_client(db, monkeypatch, settings):
    api_client = APIClient(enforce_csrf_checks=True)
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token",
        lambda credential: GoogleIdentity(
            sub="session-sub",
            email="session@example.com",
            first_name="Session",
            last_name="Student",
        ),
    )
    csrf = api_client.get(reverse("auth-csrf")).json()["csrf_token"]
    login = api_client.post(
        reverse("auth-google"), {"credential": "valid"}, format="json", HTTP_X_CSRFTOKEN=csrf
    )
    assert login.status_code == 201
    assert settings.CSRF_COOKIE_NAME in api_client.cookies
    return api_client, login


@pytest.mark.django_db
def test_access_token_authenticates_me(logged_in_client):
    api_client, login = logged_in_client
    response = api_client.get(
        reverse("auth-me"),
        HTTP_AUTHORIZATION=f"Bearer {login.json()['access_token']}",
    )

    assert response.status_code == 200
    assert response.json()["email"] == "session@example.com"
    assert response.json()["is_staff"] is False


@pytest.mark.django_db
def test_refresh_rotates_cookie_and_rejects_reuse(logged_in_client, settings):
    api_client, _ = logged_in_client
    old_refresh = api_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value

    response = api_client.post(reverse("auth-refresh"), HTTP_X_CSRFTOKEN=csrf)

    assert response.status_code == 200
    assert response.json()["access_token"]
    rotated_refresh = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    assert rotated_refresh != old_refresh

    api_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = old_refresh
    reused = api_client.post(reverse("auth-refresh"), HTTP_X_CSRFTOKEN=csrf)
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "invalid_refresh"


@pytest.mark.django_db
def test_logout_revokes_refresh_and_clears_cookie(logged_in_client, settings):
    api_client, _ = logged_in_client
    refresh = api_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value

    logout = api_client.post(reverse("auth-logout"), HTTP_X_CSRFTOKEN=csrf)

    assert logout.status_code == 204
    assert logout.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value == ""
    api_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
    rejected = api_client.post(reverse("auth-refresh"), HTTP_X_CSRFTOKEN=csrf)
    assert rejected.status_code == 401


@pytest.mark.django_db
def test_inactive_account_cannot_refresh(logged_in_client, settings):
    api_client, login = logged_in_client
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value

    user = User.objects.get(pk=login.json()["user"]["id"])
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])

    response = api_client.post(reverse("auth-refresh"), HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "account_disabled"


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["auth-refresh", "auth-logout"])
def test_cookie_backed_session_endpoints_require_csrf(logged_in_client, endpoint):
    api_client, _ = logged_in_client
    response = api_client.post(reverse(endpoint))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
