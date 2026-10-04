import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attempts.student_payload import StudentQuestionSerializer
from apps.exams.imports import COLUMNS
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
        email="owner-questions@example.com",
        google_sub="owner-questions-google-sub",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student-questions@example.com",
        google_sub="student-questions-google-sub",
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
        version="owner-questions-v1",
        name="Owner question fixture",
        effective_from=date(2026, 1, 1),
        source_reference="Test-only owner question fixture.",
        total_duration_minutes=60,
        maximum_marks=8,
        total_question_count=2,
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
        question_count=2,
        positive_marks=Decimal("4"),
        negative_marks=Decimal("1"),
    )
    starts_at = timezone.now() + timedelta(days=2)
    mock = MockTest.objects.create(
        exam_type=exam_type,
        exam_scheme=scheme,
        title="Owner questions mock",
        slug="owner-questions-mock",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        result_release_at=starts_at + timedelta(hours=2),
    )
    generate_phases(mock)
    return mock


def import_rows(*, correct_option="A", second=False, phase="1", subject="PHYSICS"):
    rows = []
    for number in range(1, 3 if second else 2):
        row = dict.fromkeys(COLUMNS, "")
        row.update(
            question_number=str(number),
            phase=phase,
            subject=subject,
            question_type="MCQ_SINGLE",
            question_text_md="Question content " + str(number),
            option_a="Option A",
            option_b="Option B",
            option_c="Option C",
            option_d="Option D",
            correct_option=correct_option,
            positive_marks="4",
            negative_marks="1",
            numeric_tolerance="0",
            explanation_md="An explanation.",
        )
        rows.append(row)
    return rows


def upload_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile("questions.csv", stream.getvalue().encode("utf-8"))


def preview_url(mock):
    return reverse("owner-question-import-preview", kwargs={"mock_id": mock.pk})


def commit_url(mock):
    return reverse("owner-question-import-commit", kwargs={"mock_id": mock.pk})


@pytest.mark.django_db
def test_owner_question_routes_require_owner_auth(mock, student):
    client = client_for()
    student_client = client_for(student)

    assert (
        client.get(reverse("owner-mock-questions", kwargs={"mock_id": mock.pk})).status_code == 401
    )
    assert (
        student_client.get(reverse("owner-mock-questions", kwargs={"mock_id": mock.pk})).status_code
        == 403
    )
    assert (
        student_client.post(
            preview_url(mock), {"file": upload_csv(import_rows())}, format="multipart"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_owner_question_list_and_detail_are_sanitized(owner, mock):
    preview = client_for(owner).post(
        preview_url(mock), {"file": upload_csv(import_rows())}, format="multipart"
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert Question.objects.filter(mock_test=mock).count() == 0

    committed = client_for(owner).post(
        commit_url(mock), {"token": preview.json()["token"]}, format="json"
    )
    assert committed.status_code == 200
    assert committed.json() == {"imported_count": 1}

    client = client_for(owner)
    response = client.get(reverse("owner-mock-questions", kwargs={"mock_id": mock.pk}))
    assert response.status_code == 200
    payload = response.json()
    assert payload["mock"] == {
        "id": str(mock.pk),
        "title": mock.title,
        "status": MockTest.Status.DRAFT,
        "question_count": 1,
        "expected_question_count": 2,
        "read_only": False,
    }
    assert payload["grouped_counts"] == [
        {
            "phase_order": 1,
            "phase_name": "Full paper",
            "subject": "PHYSICS",
            "question_type": "MCQ_SINGLE",
            "count": 1,
        }
    ]
    row = payload["results"][0]
    assert row["question_number"] == 1
    assert row["status"] == Question.Status.READY
    assert row["question_preview"] == "Question content 1"
    assert "correct_option" not in str(payload)
    assert "numeric_answer" not in str(payload)
    assert "is_correct" not in str(payload)
    assert "PRIVATE" not in str(payload)

    detail = client.get(
        reverse(
            "owner-mock-question-detail",
            kwargs={"mock_id": mock.pk, "question_id": row["id"]},
        )
    )
    assert detail.status_code == 200
    assert detail.json()["options"][0] == {
        "label": "A",
        "text": "Option A",
        "has_image": False,
    }
    assert "correct_option" not in str(detail.json())
    assert "correct_numeric_answer" not in str(detail.json())
    assert "is_correct" not in str(detail.json())

    student_payload = StudentQuestionSerializer(Question.objects.get(mock_test=mock)).data
    assert "correct_numeric_answer" not in str(student_payload)
    assert "is_correct" not in str(student_payload)


@pytest.mark.django_db
def test_invalid_preview_and_invalid_commit_create_no_rows(owner, mock):
    response = client_for(owner).post(
        preview_url(mock),
        {"file": upload_csv(import_rows(correct_option="E"))},
        format="multipart",
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["token"] == ""
    assert "correct_option" in str(response.json()["errors"])

    failed_commit = client_for(owner).post(commit_url(mock), {"token": ""}, format="json")
    assert failed_commit.status_code == 400
    assert Question.objects.filter(mock_test=mock).count() == 0
    assert QuestionOption.objects.count() == 0


@pytest.mark.django_db
def test_atomic_commit_rolls_back_question_rows_on_option_insert_error(owner, mock, monkeypatch):
    response = client_for(owner).post(
        preview_url(mock),
        {"file": upload_csv(import_rows(second=True))},
        format="multipart",
    )
    assert response.json()["valid"] is True

    def fail_insert(_options):
        assert Question.objects.filter(mock_test=mock).count() == 2
        raise ValidationError("Simulated option insertion failure.")

    monkeypatch.setattr("apps.exams.imports._insert_options", fail_insert)
    committed = client_for(owner).post(
        commit_url(mock), {"token": response.json()["token"]}, format="json"
    )
    assert committed.status_code == 400
    assert Question.objects.filter(mock_test=mock).count() == 0
    assert QuestionOption.objects.count() == 0


@pytest.mark.django_db
def test_import_rejects_non_draft_mock(owner, mock):
    with service_write():
        mock.status = MockTest.Status.REGISTRATION_OPEN
        mock.save(update_fields=["status"])

    response = client_for(owner).post(
        preview_url(mock), {"file": upload_csv(import_rows())}, format="multipart"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "draft_mock_required"
    assert Question.objects.filter(mock_test=mock).count() == 0


@pytest.mark.django_db
def test_question_list_query_count_is_constant(owner, mock):
    client = client_for(owner)
    url = reverse("owner-mock-questions", kwargs={"mock_id": mock.pk})
    with CaptureQueriesContext(connection) as empty_queries:
        assert client.get(url).status_code == 200
    empty_count = len(empty_queries)

    preview = client.post(
        preview_url(mock), {"file": upload_csv(import_rows(second=True))}, format="multipart"
    )
    client.post(commit_url(mock), {"token": preview.json()["token"]}, format="json")
    with CaptureQueriesContext(connection) as populated_queries:
        assert client.get(url).status_code == 200

    assert len(populated_queries) == empty_count


@pytest.mark.django_db
def test_owner_template_supports_csv_and_xlsx(owner, student):
    client = client_for(owner)
    csv_response = client.get(
        reverse("owner-question-import-template", kwargs={"file_format": "csv"})
    )
    xlsx_response = client.get(
        reverse("owner-question-import-template", kwargs={"file_format": "xlsx"})
    )

    assert csv_response.status_code == xlsx_response.status_code == 200
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert xlsx_response["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert (
        client_for(student)
        .get(reverse("owner-question-import-template", kwargs={"file_format": "csv"}))
        .status_code
        == 403
    )
