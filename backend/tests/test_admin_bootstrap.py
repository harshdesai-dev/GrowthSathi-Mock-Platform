from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User


@pytest.mark.django_db
def test_bootstrap_admin_creates_passwordless_platform_owner():
    output = StringIO()
    call_command(
        "bootstrap_admin",
        email="owner@example.com",
        google_sub="owner-google-sub",
        first_name="Platform",
        last_name="Owner",
        stdout=output,
    )

    owner = User.objects.get(email="owner@example.com")
    assert owner.is_staff is True
    assert owner.is_superuser is True
    assert owner.has_usable_password() is False
    assert "Created platform owner" in output.getvalue()


@pytest.mark.django_db
def test_bootstrap_admin_refuses_identity_conflict():
    User.objects.create_user(email="owner@example.com", google_sub="different-sub")

    with pytest.raises(CommandError, match="conflicts"):
        call_command(
            "bootstrap_admin",
            email="owner@example.com",
            google_sub="owner-google-sub",
        )
