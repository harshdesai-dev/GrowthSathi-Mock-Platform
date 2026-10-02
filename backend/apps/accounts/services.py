from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .models import User


class GoogleTokenVerificationError(Exception):
    pass


class IdentityConflictError(Exception):
    pass


class InactiveUserError(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    first_name: str
    last_name: str


def verify_google_id_token(credential: str) -> GoogleIdentity:
    if not settings.GOOGLE_CLIENT_ID:
        raise ImproperlyConfigured("GOOGLE_CLIENT_ID must be configured for Google authentication.")
    try:
        claims = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=settings.GOOGLE_CLIENT_ID,
        )
    except (GoogleAuthError, ValueError) as exc:
        raise GoogleTokenVerificationError("The Google credential is invalid or expired.") from exc

    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleTokenVerificationError("The Google credential issuer is invalid.")
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise GoogleTokenVerificationError("The Google credential audience is invalid.")
    if claims.get("email_verified") is not True:
        raise GoogleTokenVerificationError("The Google email address is not verified.")

    sub = str(claims.get("sub", "")).strip()
    email = str(claims.get("email", "")).strip().lower()
    if not sub or not email:
        raise GoogleTokenVerificationError(
            "The Google credential is missing required identity claims."
        )
    return GoogleIdentity(
        sub=sub,
        email=email,
        first_name=str(claims.get("given_name", "")).strip(),
        last_name=str(claims.get("family_name", "")).strip(),
    )


def _resolve_google_identity_locked(identity: GoogleIdentity) -> tuple[User, bool]:
    user_by_sub = User.objects.select_for_update().filter(google_sub=identity.sub).first()
    user_by_email = User.objects.select_for_update().filter(email=identity.email).first()

    if user_by_sub:
        if not user_by_sub.is_active:
            raise InactiveUserError
        if user_by_email and user_by_email.pk != user_by_sub.pk:
            raise IdentityConflictError

        previous_google_name = user_by_sub.get_full_name()
        changed_fields: list[str] = []
        for field, value in (
            ("email", identity.email),
            ("first_name", identity.first_name),
            ("last_name", identity.last_name),
        ):
            if getattr(user_by_sub, field) != value:
                setattr(user_by_sub, field, value)
                changed_fields.append(field)
        if changed_fields:
            user_by_sub.save(update_fields=[*changed_fields, "updated_at"])
        profile = user_by_sub.profile
        if not profile.onboarding_completed and profile.full_name in {"", previous_google_name}:
            profile.full_name = user_by_sub.get_full_name()
            profile.save(update_fields=["full_name", "updated_at"])
        return user_by_sub, False

    if user_by_email:
        raise IdentityConflictError

    user = User.objects.create_user(
        email=identity.email,
        google_sub=identity.sub,
        first_name=identity.first_name,
        last_name=identity.last_name,
    )
    return user, True


def resolve_google_identity(identity: GoogleIdentity) -> tuple[User, bool]:
    try:
        with transaction.atomic():
            return _resolve_google_identity_locked(identity)
    except IntegrityError:
        # A concurrent first login can win either unique insert. Re-read once so the
        # same Google identity resolves normally while a genuine collision stays blocked.
        try:
            with transaction.atomic():
                return _resolve_google_identity_locked(identity)
        except IntegrityError as exc:
            raise IdentityConflictError from exc
