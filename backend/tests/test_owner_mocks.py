from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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
        email="owner-mocks@example.com",
        google_sub="owner-mocks-google-sub",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student-mocks@example.com",
        google_sub="student-mocks-google-sub",
    )


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def create_scheme(code, name):
    exam_type = ExamType.objects.create(code=code, name=name)
    scheme = ExamScheme.objects.create(
        exam_type=exam_type,
        version="ops-v1",
        name=f"{name} operations scheme",
        effective_from=date(2026, 1, 1),
        source_reference="Owner mock read-only API fixture.",
        total_duration_minutes=60,
        maximum_marks=4,
        total_question_count=1,
    )
    phase = SchemePhase.objects.create(
        scheme=scheme,
        name="Full paper",
        order=1,
        start_offset_minutes=0,
        duration_minutes=60,
        sequence_locked=False,
    )
    SchemeRule.objects.create(
        phase=phase,
        subject=Subject.PHYSICS,
        question_type=QuestionType.MCQ_SINGLE,
        question_count=1,
        positive_marks=Decimal("4"),
        negative_marks=Decimal("1"),
    )
    return scheme


def create_mock(scheme, *, slug, title, starts_at, status=MockTest.Status.DRAFT):
    mock = MockTest.objects.create(
        exam_type=scheme.exam_type,
        exam_scheme=scheme,
        title=title,
        slug=slug,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        result_release_at=starts_at + timedelta(hours=2),
    )
    generate_phases(mock)
    if status != MockTest.Status.DRAFT:
        with service_write():
            mock.status = status
            mock.rules_verified_at = timezone.now()
            mock.save()
    return mock


def add_private_question(mock):
    with service_write():
        question = Question.objects.create(
            mock_test=mock,
            phase=mock.phases.get(),
            subject=Subject.PHYSICS,
            question_number=1,
            question_type=QuestionType.MCQ_SINGLE,
            question_text_md="PRIVATE QUESTION CONTENT",
            positive_marks=Decimal("4"),
            negative_marks=Decimal("1"),
        )
        for index, label in enumerate("ABCD", 1):
            QuestionOption.objects.create(
                question=question,
                label=label,
                option_text_md=f"PRIVATE OPTION {label}",
                is_correct=label == "C",
                order=index,
            )
    return question


@pytest.mark.django_db
def test_owner_mock_list_requires_authentication():
    response = client_for().get(reverse("owner-mocks"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_student_cannot_read_owner_mock_list_or_detail(student):
    mock = create_mock(
        create_scheme("JEE_MAIN", "JEE Main"),
        slug="student-denied-mock",
        title="Student denied mock",
        starts_at=timezone.now() + timedelta(days=1),
    )
    client = client_for(student)

    assert client.get(reverse("owner-mocks")).status_code == 403
    assert client.get(reverse("owner-mock-detail", kwargs={"mock_id": mock.pk})).status_code == 403


@pytest.mark.django_db
def test_owner_mock_list_returns_operational_fields_without_question_data(owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")
    mock = create_mock(
        scheme,
        slug="jee-operations-test",
        title="JEE Operations Test",
        starts_at=timezone.now() + timedelta(days=1),
        status=MockTest.Status.REGISTRATION_OPEN,
    )
    add_private_question(mock)

    response = client_for(owner).get(reverse("owner-mocks"))

    assert response.status_code == 200
    row = response.json()["results"][0]
    assert set(row) == {
        "id",
        "title",
        "slug",
        "exam_type",
        "exam_scheme",
        "status",
        "status_label",
        "starts_at",
        "ends_at",
        "result_release_at",
        "price_paise",
        "rules_verified_at",
        "question_count",
    }
    assert {
        key: row[key]
        for key in row
        if key not in {"starts_at", "ends_at", "result_release_at", "rules_verified_at"}
    } == {
        "id": str(mock.pk),
        "title": "JEE Operations Test",
        "slug": "jee-operations-test",
        "exam_type": {"code": "JEE_MAIN", "name": "JEE Main", "active": True},
        "exam_scheme": {
            "name": "JEE Main operations scheme",
            "version": "ops-v1",
            "active": True,
            "total_question_count": 1,
            "total_duration_minutes": 60,
            "maximum_marks": 4,
        },
        "status": MockTest.Status.REGISTRATION_OPEN,
        "status_label": "Registration Open",
        "price_paise": mock.price_paise,
        "question_count": 1,
    }
    for field in ("starts_at", "ends_at", "result_release_at", "rules_verified_at"):
        assert parse_datetime(row[field]) == getattr(mock, field)
    serialized = response.content.decode()
    assert "PRIVATE QUESTION CONTENT" not in serialized
    assert "PRIVATE OPTION" not in serialized
    assert "is_correct" not in serialized
    assert "correct_numeric_answer" not in serialized


@pytest.mark.django_db
def test_owner_mock_filters_search_and_ordering(owner):
    jee = create_scheme("JEE_MAIN", "JEE Main")
    cet = create_scheme("MHT_CET_PCM", "MHT-CET PCM")
    now = timezone.now()
    create_mock(
        jee,
        slug="jee-upcoming-registration",
        title="JEE Weekly Registration",
        starts_at=now + timedelta(days=1),
        status=MockTest.Status.REGISTRATION_OPEN,
    )
    create_mock(
        jee,
        slug="jee-recent-closed",
        title="JEE Recent Archive",
        starts_at=now - timedelta(days=1),
        status=MockTest.Status.CLOSED,
    )
    create_mock(
        cet,
        slug="cet-later-scheduled",
        title="CET PCM Simulation",
        starts_at=now + timedelta(days=2),
        status=MockTest.Status.SCHEDULED,
    )
    url = reverse("owner-mocks")
    client = client_for(owner)

    filtered = client.get(url, {"exam_type": "JEE_MAIN", "status": "REGISTRATION_OPEN"})
    searched = client.get(url, {"search": "archive"})
    ordered = client.get(url)

    assert [mock["slug"] for mock in filtered.json()["results"]] == ["jee-upcoming-registration"]
    assert [mock["slug"] for mock in searched.json()["results"]] == ["jee-recent-closed"]
    assert [mock["slug"] for mock in ordered.json()["results"]] == [
        "jee-upcoming-registration",
        "cet-later-scheduled",
        "jee-recent-closed",
    ]


@pytest.mark.django_db
def test_owner_mock_list_uses_constant_query_count(owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")
    now = timezone.now()
    for index in range(4):
        create_mock(
            scheme,
            slug=f"query-count-{index}",
            title=f"Query count mock {index}",
            starts_at=now + timedelta(days=index + 1),
        )

    with CaptureQueriesContext(connection) as queries:
        response = client_for(owner).get(reverse("owner-mocks"))

    assert response.status_code == 200
    assert len(response.json()["results"]) == 4
    assert len(queries) == 1


@pytest.mark.django_db
def test_owner_mock_detail_includes_phases_and_lightweight_warnings(owner):
    mock = create_mock(
        create_scheme("JEE_MAIN", "JEE Main"),
        slug="detail-phases-test",
        title="Detail Phases Test",
        starts_at=timezone.now() + timedelta(days=1),
    )
    add_private_question(mock)

    with CaptureQueriesContext(connection) as queries:
        response = client_for(owner).get(reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}))

    assert response.status_code == 200
    assert response.json()["question_count"] == 1
    assert response.json()["phases"] == [
        {
            "order": 1,
            "name": "Full paper",
            "start_offset_minutes": 0,
            "duration_minutes": 60,
            "sequence_locked": False,
            "question_count": 1,
        }
    ]
    assert response.json()["operational_warnings"] == [
        "Official rules have not been verified for this mock."
    ]
    assert "PRIVATE QUESTION CONTENT" not in response.content.decode()
    assert len(queries) == 3


def draft_mock_payload(scheme, **overrides):
    payload = {
        "exam_type": str(scheme.exam_type_id),
        "exam_scheme": str(scheme.pk),
        "title": "Owner API draft mock",
        "slug": "owner-api-draft-mock",
        "description": "An editable DRAFT mock.",
        "starts_at": "2026-11-10T09:00:00",
        "ends_at": "2026-11-10T10:00:00",
        "result_release_at": "2026-11-10T12:00:00",
        "price_paise": 2900,
        "instructions_md": "Read the instructions carefully.",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_owner_can_create_draft_and_generate_admin_equivalent_phases(owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")

    response = client_for(owner).post(
        reverse("owner-mocks"), draft_mock_payload(scheme), format="json"
    )

    assert response.status_code == 201
    mock = MockTest.objects.get(pk=response.json()["id"])
    assert mock.status == MockTest.Status.DRAFT
    assert mock.title == "Owner API draft mock"
    assert mock.price_paise == 2900
    assert mock.starts_at == datetime(2026, 11, 10, 9, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert list(
        mock.phases.values("order", "name", "start_offset_minutes", "duration_minutes")
    ) == [
        {
            "order": phase.order,
            "name": phase.name,
            "start_offset_minutes": phase.start_offset_minutes,
            "duration_minutes": phase.duration_minutes,
        }
        for phase in scheme.phases.all()
    ]
    assert response.json()["status"] == "DRAFT"


@pytest.mark.django_db
def test_mock_create_requires_owner_and_authentication(student, owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")
    url = reverse("owner-mocks")
    payload = draft_mock_payload(scheme)

    assert client_for().post(url, payload, format="json").status_code == 401
    assert client_for(student).post(url, payload, format="json").status_code == 403
    assert client_for(student).get(reverse("owner-mock-options")).status_code == 403
    assert client_for(owner).get(reverse("owner-mock-options")).status_code == 200


@pytest.mark.django_db
def test_create_rejects_forged_status_and_unsupported_fields(owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")
    response = client_for(owner).post(
        reverse("owner-mocks"), draft_mock_payload(scheme, status="SCHEDULED"), format="json"
    )

    assert response.status_code == 400
    assert "status" in response.json()["error"]["details"]
    assert not MockTest.objects.exists()


@pytest.mark.django_db
def test_create_rejects_scheme_mismatch_invalid_schedule_and_duplicate_slug(owner):
    jee_scheme = create_scheme("JEE_MAIN", "JEE Main")
    cet_scheme = create_scheme("MHT_CET_PCM", "MHT-CET PCM")
    url = reverse("owner-mocks")
    client = client_for(owner)

    mismatch = client.post(
        url,
        draft_mock_payload(jee_scheme, exam_scheme=str(cet_scheme.pk)),
        format="json",
    )
    invalid_dates = client.post(
        url,
        draft_mock_payload(
            jee_scheme,
            ends_at="2026-11-10T08:00:00",
            result_release_at="2026-11-10T07:00:00",
        ),
        format="json",
    )
    create_mock(
        jee_scheme,
        slug="owner-api-draft-mock",
        title="Existing mock",
        starts_at=timezone.now() + timedelta(days=1),
    )
    duplicate_slug = client.post(url, draft_mock_payload(jee_scheme), format="json")
    invalid_price = client.post(
        url, draft_mock_payload(jee_scheme, slug="free-draft", price_paise=0), format="json"
    )

    assert mismatch.status_code == 400
    assert "exam_scheme" in mismatch.json()["error"]["details"]
    assert invalid_dates.status_code == 400
    assert "ends_at" in invalid_dates.json()["error"]["details"]
    assert duplicate_slug.status_code == 400
    assert "slug" in duplicate_slug.json()["error"]["details"]
    assert invalid_price.status_code == 400
    assert "price_paise" in invalid_price.json()["error"]["details"]


@pytest.mark.django_db
def test_owner_can_edit_draft_and_change_scheme_with_consistent_phases(owner):
    jee_scheme = create_scheme("JEE_MAIN", "JEE Main")
    cet_scheme = create_scheme("MHT_CET_PCM", "MHT-CET PCM")
    mock = create_mock(
        jee_scheme,
        slug="draft-to-edit",
        title="Old title",
        starts_at=timezone.now() + timedelta(days=1),
    )

    response = client_for(owner).patch(
        reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}),
        {
            "exam_type": str(cet_scheme.exam_type_id),
            "exam_scheme": str(cet_scheme.pk),
            "title": "Updated draft title",
            "price_paise": 4500,
        },
        format="json",
    )

    assert response.status_code == 200
    mock.refresh_from_db()
    assert mock.status == MockTest.Status.DRAFT
    assert mock.title == "Updated draft title"
    assert mock.exam_scheme_id == cet_scheme.pk
    assert mock.exam_type_id == cet_scheme.exam_type_id
    phases = list(mock.phases.select_related("scheme_phase"))
    assert len(phases) == 1
    assert phases[0].scheme_phase_id == cet_scheme.phases.get().pk
    assert phases[0].name == cet_scheme.phases.get().name

    forged_status = client_for(owner).patch(
        reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}),
        {"status": "SCHEDULED"},
        format="json",
    )
    assert forged_status.status_code == 400
    mock.refresh_from_db()
    assert mock.status == MockTest.Status.DRAFT


@pytest.mark.django_db
def test_student_cannot_create_or_edit_and_non_draft_edit_is_rejected(student, owner):
    scheme = create_scheme("JEE_MAIN", "JEE Main")
    draft = create_mock(
        scheme,
        slug="student-edit-draft",
        title="Draft",
        starts_at=timezone.now() + timedelta(days=1),
    )
    active = create_mock(
        scheme,
        slug="owner-edit-active",
        title="Active",
        starts_at=timezone.now() + timedelta(days=2),
        status=MockTest.Status.SCHEDULED,
    )
    url = reverse("owner-mocks")
    detail_url = reverse("owner-mock-detail", kwargs={"mock_id": draft.pk})

    assert (
        client_for(student).post(url, draft_mock_payload(scheme), format="json").status_code == 403
    )
    assert (
        client_for(student).patch(detail_url, {"title": "Hacked"}, format="json").status_code == 403
    )
    assert client_for().patch(detail_url, {"title": "Hacked"}, format="json").status_code == 401

    active_url = reverse("owner-mock-detail", kwargs={"mock_id": active.pk})
    response = client_for(owner).patch(active_url, {"title": "Must not change"}, format="json")

    assert response.status_code == 400
    assert "DRAFT" in str(response.json()["error"]["details"])
    active.refresh_from_db()
    assert active.title == "Active"


@pytest.mark.django_db
def test_changing_scheme_is_rejected_after_questions_exist(owner):
    jee_scheme = create_scheme("JEE_MAIN", "JEE Main")
    cet_scheme = create_scheme("MHT_CET_PCM", "MHT-CET PCM")
    mock = create_mock(
        jee_scheme,
        slug="scheme-with-paper",
        title="Scheme with paper",
        starts_at=timezone.now() + timedelta(days=1),
    )
    add_private_question(mock)

    response = client_for(owner).patch(
        reverse("owner-mock-detail", kwargs={"mock_id": mock.pk}),
        {"exam_type": str(cet_scheme.exam_type_id), "exam_scheme": str(cet_scheme.pk)},
        format="json",
    )

    assert response.status_code == 400
    mock.refresh_from_db()
    assert mock.exam_scheme_id == jee_scheme.pk
    assert mock.questions.count() == 1
    assert mock.phases.get().scheme_phase_id == jee_scheme.phases.get().pk
