from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

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


@pytest.mark.django_db
def test_bootstrapped_owner_can_receive_hashed_admin_password(client, monkeypatch):
    call_command(
        "bootstrap_admin",
        email="owner@example.com",
        google_sub="owner-google-sub",
    )
    password = "Owner-only-admin-password-482!"
    monkeypatch.setenv("GROWTHSATHI_ADMIN_PASSWORD", password)

    call_command(
        "set_admin_password",
        email="owner@example.com",
        google_sub="owner-google-sub",
        password_env="GROWTHSATHI_ADMIN_PASSWORD",
    )

    owner = User.objects.get(email="owner@example.com")
    assert owner.password != password
    assert owner.check_password(password) is True

    response = client.post(
        reverse("admin:login"),
        {"username": owner.email, "password": password, "next": reverse("admin:index")},
        follow=True,
    )
    assert response.status_code == 200
    assert response.context["user"].is_authenticated is True
    assert response.request["PATH_INFO"] == reverse("admin:index")


@pytest.mark.django_db
def test_non_staff_user_cannot_receive_admin_password(monkeypatch):
    student = User.objects.create_user(email="student@example.com", google_sub="student-sub")
    monkeypatch.setenv("GROWTHSATHI_ADMIN_PASSWORD", "Owner-only-admin-password-482!")

    with pytest.raises(CommandError, match="staff superuser"):
        call_command(
            "set_admin_password",
            email=student.email,
            google_sub=student.google_sub,
            password_env="GROWTHSATHI_ADMIN_PASSWORD",
        )

    student.refresh_from_db()
    assert student.has_usable_password() is False


@pytest.mark.django_db
def test_password_session_cannot_authenticate_to_product_api(client):
    student = User.objects.create_user(email="student@example.com", google_sub="student-sub")
    student.set_password("Test-only-student-password-482!")
    student.save(update_fields=["password", "updated_at"])
    assert client.login(email=student.email, password="Test-only-student-password-482!") is True

    response = client.get(reverse("auth-me"))
    assert response.status_code == 401
