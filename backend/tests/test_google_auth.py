from unittest.mock import Mock

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import (
    GoogleIdentity,
    GoogleTokenVerificationError,
    verify_google_id_token,
)

VALID_IDENTITY = GoogleIdentity(
    sub="google-sub-123",
    email="student@example.com",
    first_name="Asha",
    last_name="Patil",
)


def test_google_certificate_lookup_has_bounded_network_timeout(monkeypatch, settings):
    settings.GOOGLE_CLIENT_ID = "test.apps.googleusercontent.com"
    transport = Mock()
    monkeypatch.setattr("apps.accounts.services.google_requests.Request", lambda: transport)

    def verify(credential, request, audience):
        request("https://www.googleapis.com/oauth2/v1/certs", method="GET")
        return {
            "iss": "accounts.google.com",
            "aud": audience,
            "email_verified": True,
            "sub": "bounded",
            "email": "bounded@example.com",
        }

    monkeypatch.setattr("apps.accounts.services.google_id_token.verify_oauth2_token", verify)
    assert verify_google_id_token("synthetic").sub == "bounded"
    assert transport.call_args.kwargs["timeout"] == 5


@pytest.mark.django_db
def test_valid_google_login_creates_user_profile_and_secure_session(client, monkeypatch, settings):
    settings.AUTH_REFRESH_COOKIE_SECURE = True
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token", lambda credential: VALID_IDENTITY
    )

    response = client.post(
        reverse("auth-google"),
        {"credential": "verified-google-token"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == VALID_IDENTITY.email
    assert response.json()["user"]["onboarding_completed"] is False
    assert response.json()["access_token"]
    user = User.objects.get(google_sub=VALID_IDENTITY.sub)
    assert user.has_usable_password() is False
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.profile.full_name == "Asha Patil"
    refresh_cookie = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
    assert refresh_cookie["httponly"] is True
    assert refresh_cookie["secure"] is True
    assert refresh_cookie["samesite"] == "Lax"
    assert refresh_cookie["path"] == "/api/v1/auth/"
    assert settings.CSRF_COOKIE_NAME in response.cookies


@pytest.mark.django_db
def test_invalid_google_token_is_rejected(client, monkeypatch):
    def reject(_credential):
        raise GoogleTokenVerificationError("The Google credential is invalid or expired.")

    monkeypatch.setattr("apps.accounts.api.views.verify_google_id_token", reject)
    response = client.post(
        reverse("auth-google"), {"credential": "bad-token"}, content_type="application/json"
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_google_token"
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_repeat_login_uses_same_user_and_updates_google_name_and_email(client, monkeypatch):
    identities = iter(
        [
            VALID_IDENTITY,
            GoogleIdentity(
                sub=VALID_IDENTITY.sub,
                email="asha.new@example.com",
                first_name="Aashi",
                last_name="Patil",
            ),
        ]
    )
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token", lambda credential: next(identities)
    )

    first = client.post(
        reverse("auth-google"), {"credential": "first"}, content_type="application/json"
    )
    original_id = first.json()["user"]["id"]
    second = client.post(
        reverse("auth-google"), {"credential": "second"}, content_type="application/json"
    )

    assert second.status_code == 200
    assert second.json()["user"]["id"] == original_id
    assert User.objects.count() == 1
    user = User.objects.get()
    assert user.email == "asha.new@example.com"
    assert user.first_name == "Aashi"
    assert user.profile.full_name == "Aashi Patil"


@pytest.mark.django_db
def test_different_google_subject_cannot_claim_existing_email(client, monkeypatch):
    User.objects.create_user(email=VALID_IDENTITY.email, google_sub="first-sub")
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token",
        lambda credential: GoogleIdentity(
            sub="different-sub",
            email=VALID_IDENTITY.email,
            first_name="Other",
            last_name="Student",
        ),
    )

    response = client.post(
        reverse("auth-google"), {"credential": "conflicting"}, content_type="application/json"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_conflict"
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_google_subject_email_change_cannot_take_another_users_email(client, monkeypatch):
    User.objects.create_user(email="original@example.com", google_sub="same-sub")
    User.objects.create_user(email="claimed@example.com", google_sub="other-sub")
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token",
        lambda credential: GoogleIdentity(
            sub="same-sub",
            email="claimed@example.com",
            first_name="Asha",
            last_name="Patil",
        ),
    )

    response = client.post(
        reverse("auth-google"), {"credential": "conflicting"}, content_type="application/json"
    )

    assert response.status_code == 409
    assert User.objects.get(google_sub="same-sub").email == "original@example.com"


@pytest.mark.django_db
def test_inactive_user_is_rejected(client, monkeypatch):
    User.objects.create_user(
        email=VALID_IDENTITY.email, google_sub=VALID_IDENTITY.sub, is_active=False
    )
    monkeypatch.setattr(
        "apps.accounts.api.views.verify_google_id_token", lambda credential: VALID_IDENTITY
    )

    response = client.post(
        reverse("auth-google"), {"credential": "valid"}, content_type="application/json"
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "account_disabled"


@pytest.mark.parametrize(
    ("claims", "message"),
    [
        (
            {
                "sub": "sub",
                "email": "student@example.com",
                "email_verified": True,
                "iss": "https://accounts.google.com",
                "aud": "wrong-client",
            },
            "audience",
        ),
        (
            {
                "sub": "sub",
                "email": "student@example.com",
                "email_verified": True,
                "iss": "https://untrusted.example.com",
                "aud": "test-client",
            },
            "issuer",
        ),
    ],
)
def test_google_verifier_rejects_wrong_audience_or_issuer(monkeypatch, settings, claims, message):
    settings.GOOGLE_CLIENT_ID = "test-client"
    monkeypatch.setattr(
        "apps.accounts.services.google_id_token.verify_oauth2_token", lambda *args, **kwargs: claims
    )

    with pytest.raises(GoogleTokenVerificationError, match=message):
        verify_google_id_token("credential")


def test_google_verifier_rejects_expired_or_invalid_signature(monkeypatch, settings):
    settings.GOOGLE_CLIENT_ID = "test-client"
    verifier = Mock(side_effect=ValueError("Token expired"))
    monkeypatch.setattr("apps.accounts.services.google_id_token.verify_oauth2_token", verifier)

    with pytest.raises(GoogleTokenVerificationError, match="invalid or expired"):
        verify_google_id_token("expired-token")


def test_google_verifier_accepts_verified_claims(monkeypatch, settings):
    settings.GOOGLE_CLIENT_ID = "test-client"
    verifier = Mock(
        return_value={
            "sub": VALID_IDENTITY.sub,
            "email": VALID_IDENTITY.email,
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": "test-client",
            "given_name": "Asha",
            "family_name": "Patil",
        }
    )
    monkeypatch.setattr(
        "apps.accounts.services.google_id_token.verify_oauth2_token",
        verifier,
    )

    assert verify_google_id_token("valid-token") == VALID_IDENTITY
    assert verifier.call_args.kwargs["audience"] == "test-client"
