from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.exams.models import (
    ExamScheme,
    ExamType,
    MockTest,
    Question,
    QuestionOption,
    QuestionType,
    SchemePhase,
    SchemeRule,
    Subject,
)
from apps.exams.services import generate_phases, service_write


@pytest.fixture
def owner(db):
    return User.objects.create_superuser(
        email="owner-operations@example.com",
        google_sub="owner-operations-google-sub",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student-operations@example.com",
        google_sub="student-operations-google-sub",
    )


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


@pytest.fixture
def mock(db):
    exam_type = ExamType.objects.create(code="JEE_MAIN", name="JEE Main")
    scheme = ExamScheme.objects.create(
        exam_type=exam_type,
        version="owner-operations-v1",
        name="Owner operations fixture",
        effective_from=date(2026, 1, 1),
        source_reference="Test-only operations fixture.",
        total_duration_minutes=60,
        maximum_marks=4,
        total_question_count=1,
    )
    scheme_phase = SchemePhase.objects.create(
        scheme=scheme,
        name="Full paper",
        order=1,
        start_offset_minutes=0,
        duration_minutes=60,
        sequence_locked=False,
    )
    SchemeRule.objects.create(
        phase=scheme_phase,
        subject=Subject.PHYSICS,
        question_type=QuestionType.MCQ_SINGLE,
        question_count=1,
        positive_marks=Decimal("4"),
        negative_marks=Decimal("1"),
    )
    starts_at = timezone.now() + timedelta(days=2)
    mock = MockTest.objects.create(
        exam_type=exam_type,
        exam_scheme=scheme,
        title="Owner operations mock",
        slug="owner-operations-mock",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=60),
        result_release_at=starts_at + timedelta(hours=2),
    )
    generate_phases(mock)
    return mock


def add_valid_question(mock):
    question = Question.objects.create(
        mock_test=mock,
        phase=mock.phases.get(),
        subject=Subject.PHYSICS,
        question_number=1,
        question_type=QuestionType.MCQ_SINGLE,
        question_text_md="A valid physics question.",
        positive_marks=Decimal("4"),
        negative_marks=Decimal("1"),
        explanation_md="A valid explanation.",
        status=Question.Status.READY,
    )
    for order, label in enumerate("ABCD", 1):
        QuestionOption.objects.create(
            question=question,
            label=label,
            option_text_md=f"Option {label}",
            is_correct=label == "A",
            order=order,
        )
    return question


def validation_url(mock):
    return reverse("owner-mock-validate", kwargs={"mock_id": mock.pk})


def verification_url(mock):
    return reverse("owner-mock-verify-rules", kwargs={"mock_id": mock.pk})


@pytest.mark.django_db
def test_owner_paper_validation_is_owner_only(owner, student, mock):
    add_valid_question(mock)
    url = validation_url(mock)

    assert client_for().post(url, {}, format="json").status_code == 401
    assert client_for(student).post(url, {}, format="json").status_code == 403

    response = client_for(owner).post(url, {}, format="json")

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["status"] == "VALID"
    assert response.json()["errors"] == []
    assert response.json()["warnings"] == []


@pytest.mark.django_db
def test_valid_paper_summary_and_validation_are_read_only(owner, mock):
    question = add_valid_question(mock)
    before_mock = MockTest.objects.values(
        "status", "rules_verified_at", "rules_verified_by_id", "rules_source_notes"
    ).get(pk=mock.pk)
    before_question = Question.objects.values(
        "status", "question_number", "question_text_md", "correct_numeric_answer"
    ).get(pk=question.pk)
    before_options = list(
        question.options.order_by("order").values_list("label", "is_correct", "option_text_md")
    )

    response = client_for(owner).post(validation_url(mock), {}, format="json")

    assert response.json()["actual_question_count"] == 1
    assert response.json()["expected_question_count"] == 1
    assert Decimal(response.json()["marks_summary"]["actual"]) == Decimal("4.00")
    assert Decimal(response.json()["marks_summary"]["expected"]) == Decimal("4.00")
    assert (
        MockTest.objects.values(
            "status", "rules_verified_at", "rules_verified_by_id", "rules_source_notes"
        ).get(pk=mock.pk)
        == before_mock
    )
    assert (
        Question.objects.values(
            "status", "question_number", "question_text_md", "correct_numeric_answer"
        ).get(pk=question.pk)
        == before_question
    )
    assert (
        list(
            question.options.order_by("order").values_list("label", "is_correct", "option_text_md")
        )
        == before_options
    )
    assert "is_correct" not in str(response.json())
    assert "correct_numeric_answer" not in str(response.json())


@pytest.mark.django_db
def test_invalid_paper_returns_existing_validator_errors(owner, mock):
    response = client_for(owner).post(validation_url(mock), {}, format="json")

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["status"] == "INVALID"
    assert "Expected 1 questions; found 0." in response.json()["errors"]
    assert response.json()["actual_question_count"] == 0
    assert Decimal(response.json()["marks_summary"]["actual"]) == Decimal("0.00")


@pytest.mark.django_db
def test_owner_rules_verification_uses_service_and_persists_service_metadata(owner, mock):
    source_notes = "  NTA JEE Main bulletin, 2026 edition; checked 2026-09-25; verified pattern.  "
    response = client_for(owner).post(
        verification_url(mock),
        {"source_notes": source_notes, "confirmed": True},
        format="json",
    )

    assert response.status_code == 200
    mock.refresh_from_db()
    assert mock.rules_source_notes == source_notes.strip()
    assert mock.rules_verified_by_id == owner.pk
    assert mock.rules_verified_at is not None
    assert response.json()["rules_source_notes"] == source_notes.strip()
    assert response.json()["rules_verified_at"]
    assert mock.status == MockTest.Status.DRAFT

    detail = client_for(owner).get(reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}))
    assert detail.status_code == 200
    assert detail.json()["rules_source_notes"] == source_notes.strip()
    assert detail.json()["rules_verified_at"] == response.json()["rules_verified_at"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"source_notes": "", "confirmed": True},
        {"source_notes": "Source reviewed.", "confirmed": False},
        {
            "source_notes": "Source reviewed.",
            "confirmed": True,
            "rules_verified_at": "2026-01-01T00:00:00Z",
        },
    ],
)
def test_rules_verification_rejects_invalid_or_forged_input(owner, mock, payload):
    response = client_for(owner).post(verification_url(mock), payload, format="json")

    assert response.status_code == 400
    mock.refresh_from_db()
    assert mock.rules_verified_at is None
    assert mock.rules_verified_by_id is None
    assert mock.rules_source_notes == ""


@pytest.mark.django_db
def test_rules_verification_requires_owner_authentication(student, mock):
    url = verification_url(mock)
    payload = {"source_notes": "Source checked.", "confirmed": True}

    assert client_for().post(url, payload, format="json").status_code == 401
    assert client_for(student).post(url, payload, format="json").status_code == 403


@pytest.mark.django_db
def test_rules_verification_is_draft_only(owner, mock):
    with service_write():
        mock.status = MockTest.Status.CLOSED
        mock.save()

    response = client_for(owner).post(
        verification_url(mock),
        {"source_notes": "Source checked.", "confirmed": True},
        format="json",
    )

    assert response.status_code == 400
    mock.refresh_from_db()
    assert mock.rules_verified_at is None
    assert mock.rules_source_notes == ""


@pytest.mark.django_db
def test_generic_owner_patch_cannot_forge_rules_verification(owner, mock):
    response = client_for(owner).patch(
        reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}),
        {
            "rules_source_notes": "Forged verification.",
            "rules_verified_at": "2026-01-01T00:00:00Z",
            "rules_verified_by": str(owner.pk),
        },
        format="json",
    )

    assert response.status_code == 400
    mock.refresh_from_db()
    assert mock.rules_verified_at is None
    assert mock.rules_verified_by_id is None
    assert mock.rules_source_notes == ""
