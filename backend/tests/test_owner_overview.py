from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commerce.models import MockOffer, Order, Payment
from apps.commerce.services import writing as commerce_writing
from apps.exams.models import ExamScheme, ExamType, MockTest
from apps.exams.services import service_write as exam_writing


@pytest.fixture
def owner(db):
    return User.objects.create_superuser(
        email="overview-owner@example.com",
        google_sub="overview-owner-google-sub",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="overview-student@example.com",
        google_sub="overview-student-google-sub",
    )


def client_for(user=None):
    api_client = APIClient()
    if user is not None:
        api_client.force_authenticate(user)
    return api_client


@pytest.fixture
def exam_scheme(db):
    exam_type = ExamType.objects.create(code="OVERVIEW", name="Overview Test")
    return ExamScheme.objects.create(
        exam_type=exam_type,
        version="overview-v1",
        name="Overview Test Scheme",
        effective_from=date(2026, 1, 1),
        source_reference="Owner overview aggregate fixture.",
        total_duration_minutes=60,
        maximum_marks=100,
        total_question_count=10,
    )


def create_mock(exam_scheme, index, status, starts_at):
    mock = MockTest.objects.create(
        exam_type=exam_scheme.exam_type,
        exam_scheme=exam_scheme,
        title=f"Overview mock {index}",
        slug=f"overview-mock-{index}",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        result_release_at=starts_at + timedelta(hours=2),
    )
    if status != MockTest.Status.DRAFT:
        with exam_writing():
            mock.status = status
            mock.save()
    return mock


def create_offer():
    now = timezone.now()
    return MockOffer.objects.create(
        name="Overview fixture offer",
        slug="overview-fixture-offer",
        offer_type=MockOffer.Type.JEE,
        price_paise=2900,
        sales_start_at=now - timedelta(days=1),
        sales_end_at=now + timedelta(days=1),
    )


def create_payment_order(*, student, offer, index, order_status, payment_status, amount_paise):
    now = timezone.now()
    with commerce_writing():
        order = Order.objects.create(
            student=student,
            offer=offer,
            offer_name_snapshot=offer.name,
            offer_slug_snapshot=offer.slug,
            offer_type_snapshot=offer.offer_type,
            total_amount_paise=amount_paise,
            status=order_status,
            paid_at=now if order_status == Order.Status.PAID else None,
        )
        create_payment(
            order=order,
            index=index,
            payment_status=payment_status,
            amount_paise=amount_paise,
        )
    return order


def create_payment(*, order, index, payment_status, amount_paise):
    with commerce_writing():
        return Payment.objects.create(
            order=order,
            gateway_payment_id=f"pay_overview_fixture_{index}",
            amount_paise=amount_paise,
            status=payment_status,
        )


@pytest.mark.django_db
def test_owner_overview_requires_authentication():
    response = client_for().get(reverse("owner-overview"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_student_cannot_receive_owner_overview_data(student):
    response = client_for(student).get(reverse("owner-overview"))

    assert response.status_code == 403
    assert "total_students" not in response.json()


@pytest.mark.django_db
def test_owner_overview_returns_aggregates_without_loading_rows(owner, student, exam_scheme):
    now = timezone.now()
    User.objects.create_user(
        email="overview-student-two@example.com",
        google_sub="overview-student-two-google-sub",
    )
    User.objects.create_user(
        email="overview-staff@example.com",
        google_sub="overview-staff-google-sub",
        is_staff=True,
    )

    create_mock(
        exam_scheme,
        1,
        MockTest.Status.REGISTRATION_OPEN,
        now + timedelta(days=1),
    )
    create_mock(exam_scheme, 2, MockTest.Status.SCHEDULED, now + timedelta(days=2))
    create_mock(exam_scheme, 3, MockTest.Status.CLOSED, now - timedelta(days=3))
    create_mock(
        exam_scheme,
        4,
        MockTest.Status.RESULTS_PUBLISHED,
        now - timedelta(days=5),
    )
    create_mock(exam_scheme, 5, MockTest.Status.CANCELLED, now + timedelta(days=3))
    create_mock(exam_scheme, 6, MockTest.Status.DRAFT, now + timedelta(days=4))
    create_mock(exam_scheme, 7, MockTest.Status.REGISTRATION_OPEN, now - timedelta(days=1))

    offer = create_offer()
    first_paid_order = create_payment_order(
        student=student,
        offer=offer,
        index=1,
        order_status=Order.Status.PAID,
        payment_status=Payment.Status.CAPTURED,
        amount_paise=2900,
    )
    # The second capture flags this order for duplicate-payment refund review.
    first_paid_order.review_required = True
    first_paid_order.review_note = "Multiple verified captures: manual review."
    with commerce_writing():
        first_paid_order.save(update_fields=("review_required", "review_note"))
    create_payment(
        order=first_paid_order,
        index=8,
        payment_status=Payment.Status.CAPTURED,
        amount_paise=2900,
    )
    create_payment_order(
        student=student,
        offer=offer,
        index=2,
        order_status=Order.Status.PAID,
        payment_status=Payment.Status.CAPTURED,
        amount_paise=5000,
    )
    failed_order = create_payment_order(
        student=student,
        offer=offer,
        index=3,
        order_status=Order.Status.FAILED,
        payment_status=Payment.Status.FAILED,
        amount_paise=9900,
    )
    create_payment(
        order=failed_order,
        index=9,
        payment_status=Payment.Status.FAILED,
        amount_paise=9900,
    )
    create_payment_order(
        student=student,
        offer=offer,
        index=4,
        order_status=Order.Status.PENDING,
        payment_status=Payment.Status.AUTHORIZED,
        amount_paise=8700,
    )
    create_payment_order(
        student=student,
        offer=offer,
        index=5,
        order_status=Order.Status.PENDING,
        payment_status=Payment.Status.CAPTURED,
        amount_paise=7600,
    )
    create_payment_order(
        student=student,
        offer=offer,
        index=6,
        order_status=Order.Status.FAILED,
        payment_status=Payment.Status.CAPTURED,
        amount_paise=6500,
    )
    create_payment_order(
        student=student,
        offer=offer,
        index=7,
        order_status=Order.Status.REFUNDED,
        payment_status=Payment.Status.REFUNDED,
        amount_paise=5400,
    )

    with CaptureQueriesContext(connection) as queries:
        response = client_for(owner).get(reverse("owner-overview"))

    assert response.status_code == 200
    assert response.json() == {
        "total_students": 2,
        "upcoming_mocks": 2,
        "completed_mocks": 2,
        "paid_orders": 2,
        "failed_payments": 2,
        "total_revenue_paise": 7900,
    }
    assert len(queries) == 4


@pytest.mark.django_db
def test_owner_overview_returns_genuine_zero_aggregates(owner):
    response = client_for(owner).get(reverse("owner-overview"))

    assert response.status_code == 200
    assert response.json() == {
        "total_students": 0,
        "upcoming_mocks": 0,
        "completed_mocks": 0,
        "paid_orders": 0,
        "failed_payments": 0,
        "total_revenue_paise": 0,
    }
