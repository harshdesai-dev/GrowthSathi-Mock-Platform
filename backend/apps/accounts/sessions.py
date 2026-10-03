"""Serialize rotation/revocation so two concurrent uses cannot rotate the same token."""

from django.db import transaction
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .services import InactiveUserError


def rotate_session(token):
    verified = RefreshToken(token)
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(pk=verified[api_settings.USER_ID_CLAIM], is_active=True)
            .first()
        )
        if user is None:
            raise InactiveUserError
        # Serializer checks the blacklist again AFTER the user lock is acquired.
        serializer = TokenRefreshSerializer(data={"refresh": token})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


def revoke_session(token):
    verified = RefreshToken(token)
    with transaction.atomic():
        User.objects.select_for_update().filter(pk=verified[api_settings.USER_ID_CLAIM]).first()
        RefreshToken(token).blacklist()
