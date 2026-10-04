from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commerce.models import (
    MockAccessGrant,
    MockOffer,
    MockOfferItem,
    Order,
    OrderItem,
    Payment,
)
from apps.commerce.services import writing as commerce_writing
from apps.exams.models import (
    AnswerKeyAuditEvent,
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
from apps.exams.services import generate_phases, service_write, verify_official_rules


def client_for(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client


@pytest.fixture
def owner(db):
    return User.objects.create_superuser(email="owner-ops@test.invalid", google_sub="owner-ops")


@pytest.fixture
def student(db):
    user = User.objects.create_user(email="student-ops@test.invalid", google_sub="student-ops")
    profile = user.profile
    profile.full_name = "Student Operator"
    profile.phone = "+919876543210"
    profile.class_level = "12"
    profile.target_exam = "JEE"
    profile.onboarding_completed = True
    profile.save()
    return user


def paper(owner, *, slug="owner-operations", release_offset=-1, verify_rules=True):
    exam_type = ExamType.objects.create(code=f"EXAM-{slug}", name="Owner test exam")
    scheme = ExamScheme.objects.create(
        exam_type=exam_type,
        version="v1",
        name="Owner test scheme",
        effective_from=date(2026, 1, 1),
        source_reference="Test source",
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
        title=f"Owner paper {slug}",
        slug=slug,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        result_release_at=now + timedelta(hours=release_offset),
    )
    generate_phases(mock)
    with service_write():
        question = Question.objects.create(
            mock_test=mock,
            phase=mock.phases.get(),
            subject=Subject.PHYSICS,
            question_number=1,
            question_type=QuestionType.MCQ_SINGLE,
            question_text_md="Private question",
            explanation_md="Private explanation",
            positive_marks=Decimal("4"),
            negative_marks=Decimal("1"),
        )
        for index, label in enumerate("ABCD", 1):
            QuestionOption.objects.create(
                question=question,
                label=label,
                option_text_md=f"Option {label}",
                is_correct=label == "A",
                order=index,
            )
    if verify_rules:
        verify_official_rules(mock.pk, actor=owner, source_notes="Official rules checked.")
    return mock, question


def transition(client, mock, target):
    return client.post(
        reverse("owner-mock-transition", kwargs={"mock_id": mock.pk}),
        {"target": target, "confirmed": True},
        format="json",
    )


@pytest.mark.django_db
def test_owner_lifecycle_uses_domain_transition_and_locks_questions(owner, student):
    mock, question = paper(owner)
    url = reverse("owner-mock-transition", kwargs={"mock_id": mock.pk})
    assert client_for().post(url, {"target": "SCHEDULED"}, format="json").status_code == 401
    assert client_for(student).post(url, {"target": "SCHEDULED"}, format="json").status_code == 403

    client = client_for(owner)
    assert transition(client, mock, "SCHEDULED").status_code == 200
    assert transition(client, mock, "LIVE").status_code == 200
    question.refresh_from_db()
    assert question.status == Question.Status.LOCKED
    assert transition(client, mock, "CLOSED").status_code == 200
    rejected = transition(client, mock, "RESULTS_PUBLISHED")
    assert rejected.status_code == 400
    mock.refresh_from_db()
    assert mock.status == MockTest.Status.CLOSED


@pytest.mark.django_db
def test_illegal_transition_and_cancelled_terminal_are_rejected(owner):
    mock, _ = paper(owner, slug="cancel-terminal")
    client = client_for(owner)
    assert transition(client, mock, "LIVE").status_code == 400
    assert transition(client, mock, "CANCELLED").status_code == 200
    assert transition(client, mock, "SCHEDULED").status_code == 400


@pytest.mark.django_db
def test_lifecycle_rejects_invalid_paper_and_missing_rules_verification(owner):
    invalid, question = paper(owner, slug="invalid-paper")
    with service_write():
        question.explanation_md = ""
        question.save()
    assert transition(client_for(owner), invalid, "SCHEDULED").status_code == 400

    unverified, _ = paper(owner, slug="unverified-paper", verify_rules=False)
    assert transition(client_for(owner), unverified, "SCHEDULED").status_code == 400


@pytest.mark.django_db
def test_owner_result_workflow_calls_existing_services_and_enforces_order(owner, student):
    mock, question = paper(owner, slug="result-workflow")
    client = client_for(owner)
    for target in ("SCHEDULED", "LIVE", "CLOSED"):
        assert transition(client, mock, target).status_code == 200

    detail_url = reverse("owner-mock-results", kwargs={"mock_id": mock.pk})
    assert client_for(student).get(detail_url).status_code == 403
    assert client.get(detail_url).json()["latest_run"] is None

    correction = client.post(
        reverse("owner-answer-correction", kwargs={"mock_id": mock.pk}),
        {
            "question_id": question.pk,
            "reason": "Verified source corrected the option.",
            "correct_option": "B",
            "confirmed": True,
        },
        format="json",
    )
    assert correction.status_code == 200
    assert AnswerKeyAuditEvent.objects.filter(
        question=question,
        changed_by=owner,
        reason="Verified source corrected the option.",
    ).exists()

    verify_response = client.post(
        reverse("owner-result-verify", kwargs={"mock_id": mock.pk}),
        {"notes": "Checked every answer against the official key.", "confirmed": True},
        format="json",
    )
    assert verify_response.status_code == 200
    run_id = verify_response.json()["id"]
    publish_url = reverse("owner-result-publish", kwargs={"mock_id": mock.pk, "run_id": run_id})
    assert client.post(publish_url, {"confirmed": True}, format="json").status_code == 400
    calculate_url = reverse("owner-result-calculate", kwargs={"mock_id": mock.pk, "run_id": run_id})
    assert client.post(calculate_url, {"confirmed": True}, format="json").status_code == 200
    assert client.post(publish_url, {"confirmed": True}, format="json").status_code == 200
    mock.refresh_from_db()
    assert mock.status == MockTest.Status.RESULTS_PUBLISHED


@pytest.mark.django_db
def test_owner_students_are_searchable_read_only_and_do_not_leak_identity(owner, student):
    response = client_for(owner).get(reverse("owner-students"), {"search": "Operator"})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    row = response.json()["results"][0]
    assert row["email"] == student.email
    assert "google_sub" not in row
    assert "password" not in row

    detail = client_for(owner).get(
        reverse("owner-student-detail", kwargs={"student_id": student.pk})
    )
    assert detail.status_code == 200
    assert "google_sub" not in detail.json()
    assert client_for(student).get(reverse("owner-students")).status_code == 403


def paid_order(owner, student, mock):
    now = timezone.now()
    with commerce_writing():
        offer = MockOffer.objects.create(
            name="Owner payment offer",
            slug="owner-payment-offer",
            offer_type=MockOffer.Type.JEE,
            price_paise=2900,
            sales_start_at=now - timedelta(days=1),
            sales_end_at=now + timedelta(days=1),
        )
        MockOfferItem.objects.create(offer=offer, mock_test=mock)
        order = Order.objects.create(
            student=student,
            offer=offer,
            offer_name_snapshot=offer.name,
            offer_slug_snapshot=offer.slug,
            offer_type_snapshot=offer.offer_type,
            total_amount_paise=2900,
            status=Order.Status.PAID,
            gateway_order_id="order_safe_reference",
            paid_at=now,
        )
        item = OrderItem.objects.create(order=order, mock_test=mock, price_paise_snapshot=2900)
        Payment.objects.create(
            order=order,
            gateway_payment_id="pay_safe_reference",
            gateway_signature="must-never-leak",
            amount_paise=2900,
            status=Payment.Status.CAPTURED,
            metadata_json={"private": "must-never-leak"},
        )
        MockAccessGrant.objects.create(
            student=student,
            mock_test=mock,
            source_order_item=item,
            status=MockAccessGrant.Status.ACTIVE,
            granted_at=now,
        )
    return order


@pytest.mark.django_db
def test_owner_payment_views_are_safe_and_reconciliation_uses_service(owner, student, monkeypatch):
    mock, _ = paper(owner, slug="payment-paper")
    order = paid_order(owner, student, mock)
    listing = client_for(owner).get(reverse("owner-payments"))
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    searched = client_for(owner).get(reverse("owner-payments"), {"search": str(order.pk)})
    assert searched.status_code == 200
    assert searched.json()["count"] == 1
    detail_url = reverse("owner-payment-detail", kwargs={"order_id": order.pk})
    detail = client_for(owner).get(detail_url)
    assert detail.status_code == 200
    payload = str(detail.json())
    assert "must-never-leak" not in payload
    assert "gateway_signature" not in payload
    assert client_for(student).get(detail_url).status_code == 403

    called = {}

    def fake_reconcile(order_id, payment_id, *, actor):
        called.update(order_id=order_id, payment_id=payment_id, actor=actor)
        return order

    monkeypatch.setattr(
        "apps.accounts.api.owner_dashboard.reconcile_gateway_payment", fake_reconcile
    )
    response = client_for(owner).post(
        reverse("owner-payment-reconcile", kwargs={"order_id": order.pk}),
        {"kind": "PAYMENT", "reference": "pay_safe_reference", "confirmed": True},
        format="json",
    )
    assert response.status_code == 200
    assert called == {
        "order_id": order.pk,
        "payment_id": "pay_safe_reference",
        "actor": owner,
    }


@pytest.mark.django_db
def test_paid_order_revenue_is_not_inflated_by_duplicate_captures(owner, student):
    mock, _ = paper(owner, slug="revenue-paper")
    order = paid_order(owner, student, mock)
    with commerce_writing():
        Payment.objects.create(
            order=order,
            gateway_payment_id="pay_duplicate_capture",
            amount_paise=2900,
            status=Payment.Status.CAPTURED,
        )
    overview = client_for(owner).get(reverse("owner-overview")).json()
    assert overview["paid_orders"] == 1
    assert overview["total_revenue_paise"] == 2900
