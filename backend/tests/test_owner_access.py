import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


@pytest.fixture
def owner(db):
    return User.objects.create_superuser(
        email="owner@example.com",
        google_sub="owner-google-sub",
        first_name="GrowthSathi",
        last_name="Owner",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student@example.com",
        google_sub="student-google-sub",
    )


def client_for(user=None):
    api_client = APIClient()
    if user is not None:
        api_client.force_authenticate(user)
    return api_client


@pytest.mark.django_db
def test_owner_access_requires_authentication():
    response = client_for().get(reverse("owner-access"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_student_cannot_access_owner_endpoint(student):
    response = client_for(student).get(reverse("owner-access"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_user_without_superuser_flag_cannot_access_owner_endpoint(student):
    student.is_staff = True
    student.save(update_fields=["is_staff", "updated_at"])

    response = client_for(student).get(reverse("owner-access"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_superuser_without_staff_flag_cannot_access_owner_endpoint(student):
    student.is_superuser = True
    student.save(update_fields=["is_superuser", "updated_at"])

    response = client_for(student).get(reverse("owner-access"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_superuser_cannot_access_owner_endpoint(owner):
    owner.is_active = False
    owner.save(update_fields=["is_active", "updated_at"])

    response = client_for(owner).get(reverse("owner-access"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_active_staff_superuser_can_access_owner_endpoint(owner):
    token = RefreshToken.for_user(owner).access_token
    response = APIClient().get(reverse("owner-access"), HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    assert response.json() == {"is_owner": True}


@pytest.mark.django_db
def test_me_includes_superuser_flag_for_authenticated_owner(owner):
    response = client_for(owner).get(reverse("auth-me"))

    assert response.status_code == 200
    assert response.json()["is_staff"] is True
    assert response.json()["is_superuser"] is True
