from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commerce.models import MockOffer
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
        email="owner-offers@example.com",
        google_sub="owner-offers-google-sub",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="student-offers@example.com",
        google_sub="student-offers-google-sub",
    )


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def create_saleable_mock():
    exam_type = ExamType.objects.create(code="JEE_MAIN", name="JEE Main")
    scheme = ExamScheme.objects.create(
        exam_type=exam_type,
        version="offers-v1",
        name="Offers test scheme",
        effective_from=date(2026, 1, 1),
        source_reference="Owner offers API test.",
        total_duration_minutes=60,
        maximum_marks=4,
        total_question_count=1,
    )
    phase = SchemePhase.objects.create(
        scheme=scheme,
        name="Paper",
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
    now = timezone.now()
    mock = MockTest.objects.create(
        exam_type=exam_type,
        exam_scheme=scheme,
        title="Owner offer rehearsal",
        slug="owner-offer-rehearsal",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        result_release_at=now + timedelta(hours=3),
        price_paise=100,
    )
    generate_phases(mock)
    with service_write():
        question = Question.objects.create(
            mock_test=mock,
            phase=mock.phases.get(),
            subject=Subject.PHYSICS,
            question_number=1,
            question_type=QuestionType.MCQ_SINGLE,
            question_text_md="2 + 2 equals?",
            explanation_md="Two plus two equals four.",
            positive_marks=Decimal("4"),
            negative_marks=Decimal("1"),
        )
        for order, label in enumerate("ABCD", 1):
            QuestionOption.objects.create(
                question=question,
                label=label,
                option_text_md=str(order + 2),
                is_correct=label == "B",
                order=order,
            )
        mock.status = MockTest.Status.SCHEDULED
        mock.rules_verified_at = now
        mock.rules_source_notes = "Test verified."
        mock.save()
    return mock


def payload(mock):
    now = timezone.now()
    return {
        "name": "JEE rehearsal offer",
        "slug": "jee-rehearsal-offer",
        "offer_type": "JEE",
        "price_paise": 100,
        "sales_start_at": (now - timedelta(minutes=5)).isoformat(),
        "sales_end_at": (now + timedelta(minutes=30)).isoformat(),
        "mock_ids": [str(mock.pk)],
    }


@pytest.mark.django_db
def test_owner_offer_endpoints_require_owner(owner, student):
    mock = create_saleable_mock()
    url = reverse("owner-offers")

    assert client_for().get(url).status_code == 401
    assert client_for(student).get(url).status_code == 403
    assert client_for(student).post(url, payload(mock), format="json").status_code == 403
    assert client_for(owner).get(url).status_code == 200


@pytest.mark.django_db
def test_owner_can_create_activate_and_list_offer(owner):
    mock = create_saleable_mock()
    client = client_for(owner)

    created = client.post(reverse("owner-offers"), payload(mock), format="json")

    assert created.status_code == 201
    assert created.json()["active"] is False
    assert created.json()["price_paise"] == 100
    assert created.json()["mocks"][0]["id"] == str(mock.pk)
    offer_id = created.json()["id"]

    activated = client.post(
        reverse("owner-offer-activation", kwargs={"offer_id": offer_id}),
        {"active": True, "confirmed": True},
        format="json",
    )

    assert activated.status_code == 200
    assert activated.json()["active"] is True
    assert MockOffer.objects.get(pk=offer_id).active is True

    listed = client.get(reverse("owner-offers"))
    assert listed.status_code == 200
    assert listed.json()["results"][0]["name"] == "JEE rehearsal offer"
    assert listed.json()["results"][0]["purchase_count"] == 0


@pytest.mark.django_db
def test_active_offer_must_be_deactivated_before_edit(owner):
    mock = create_saleable_mock()
    client = client_for(owner)
    created = client.post(reverse("owner-offers"), payload(mock), format="json")
    offer_id = created.json()["id"]
    client.post(
        reverse("owner-offer-activation", kwargs={"offer_id": offer_id}),
        {"active": True, "confirmed": True},
        format="json",
    )

    edited = payload(mock)
    edited["name"] = "Must not update while active"
    response = client.patch(
        reverse("owner-offer-detail", kwargs={"offer_id": offer_id}),
        edited,
        format="json",
    )

    assert response.status_code == 400
    assert "Deactivate" in str(response.json()["error"]["details"])
    assert MockOffer.objects.get(pk=offer_id).name == "JEE rehearsal offer"
