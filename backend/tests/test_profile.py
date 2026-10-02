import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student@example.com",
        google_sub="student-google-sub",
        first_name="Asha",
        last_name="Patil",
    )


@pytest.fixture
def authenticated_client(student):
    api_client = APIClient()
    api_client.force_authenticate(student)
    return api_client


def valid_onboarding(**overrides):
    data = {
        "full_name": "Asha Patil",
        "phone": "98765 43210",
        "class_level": "12",
        "target_exam": "BOTH",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_profile_is_created_with_user(student):
    assert student.profile.full_name == "Asha Patil"
    assert student.profile.phone == ""
    assert student.profile.onboarding_completed is False


@pytest.mark.django_db
def test_valid_onboarding_normalizes_phone_and_persists(authenticated_client, student):
    response = authenticated_client.patch(
        reverse("student-profile"), valid_onboarding(), format="json"
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "+919876543210"
    assert response.json()["onboarding_completed"] is True
    student.profile.refresh_from_db()
    assert student.profile.phone == "+919876543210"
    assert student.profile.class_level == "12"
    assert student.profile.target_exam == "BOTH"
    assert student.profile.onboarding_completed is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [("class_level", "10"), ("target_exam", "NEET")],
)
def test_onboarding_rejects_invalid_choices(authenticated_client, field, value):
    response = authenticated_client.patch(
        reverse("student-profile"), valid_onboarding(**{field: value}), format="json"
    )

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


@pytest.mark.django_db
@pytest.mark.parametrize("phone", ["12345", "+14155552671", "5123456789", "98765abc10"])
def test_onboarding_rejects_invalid_indian_mobile(authenticated_client, phone):
    response = authenticated_client.patch(
        reverse("student-profile"), valid_onboarding(phone=phone), format="json"
    )

    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_two_students_may_share_phone(student):
    other = User.objects.create_user(email="other@example.com", google_sub="other-sub")
    for current in (student, other):
        api_client = APIClient()
        api_client.force_authenticate(current)
        response = api_client.patch(reverse("student-profile"), valid_onboarding(), format="json")
        assert response.status_code == 200

    assert student.profile.phone == other.profile.phone


@pytest.mark.django_db
def test_incomplete_profile_requires_all_onboarding_fields(authenticated_client):
    response = authenticated_client.patch(
        reverse("student-profile"), {"full_name": "Asha Patil"}, format="json"
    )

    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert {"phone", "class_level", "target_exam"}.issubset(details)


@pytest.mark.django_db
def test_unauthenticated_profile_request_is_rejected(client):
    response = client.get(reverse("student-profile"))
    assert response.status_code == 401


@pytest.mark.django_db
def test_authenticated_profile_request_succeeds(authenticated_client, student):
    response = authenticated_client.get(reverse("student-profile"))
    assert response.status_code == 200
    assert response.json()["email"] == student.email


@pytest.mark.django_db
def test_user_cannot_access_another_students_profile(student):
    other = User.objects.create_user(email="other@example.com", google_sub="other-sub")
    other.profile.full_name = "Other Student"
    other.profile.save()
    api_client = APIClient()
    api_client.force_authenticate(student)

    response = api_client.get(reverse("student-profile"))

    assert response.status_code == 200
    assert response.json()["email"] == student.email
    assert response.json()["full_name"] != other.profile.full_name


@pytest.mark.django_db
def test_profile_api_cannot_promote_student_to_staff(authenticated_client, student):
    response = authenticated_client.patch(
        reverse("student-profile"),
        {**valid_onboarding(), "is_staff": True, "is_superuser": True},
        format="json",
    )

    assert response.status_code == 200
    student.refresh_from_db()
    assert student.is_staff is False
    assert student.is_superuser is False
