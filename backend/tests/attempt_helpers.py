"""Synthetic exam fixtures; no gateway calls or official-rules attestation claims."""

import io
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.commerce.models import MockAccessGrant, MockOffer, Order, OrderItem
from apps.commerce.services import writing
from apps.exams.models import ExamScheme
from apps.exams.services import transition_mock
from tests.test_exam_administration import make_mock, populate, verify


def exam_fixture(code="JEE_MAIN"):
    call_command("seed_exam_schemes", stdout=io.StringIO())
    owner = User.objects.create_superuser(email="exam-admin@test.invalid", google_sub="exam-admin")
    mock = make_mock(ExamScheme.objects.get(exam_type__code=code))
    populate(mock, owner)
    verify(mock, owner)
    transition_mock(mock.pk, "SCHEDULED", actor=owner)
    mock.refresh_from_db()
    return mock


def paid_student(mock, number=0):
    user = User.objects.create_user(
        email=f"exam-{number}@test.invalid", google_sub=f"exam-{number}"
    )
    StudentProfile.objects.update_or_create(
        user=user, defaults={"full_name": "Exam student", "onboarding_completed": True}
    )
    offer, _ = MockOffer.objects.get_or_create(
        slug="exam-fixture",
        defaults={
            "name": "Synthetic exam",
            "offer_type": "JEE" if mock.exam_type.code == "JEE_MAIN" else "CET",
            "price_paise": 2900,
            "sales_start_at": timezone.now() - timedelta(days=1),
            "sales_end_at": timezone.now() + timedelta(days=1),
        },
    )
    with writing():
        order = Order.objects.create(
            student=user,
            offer=offer,
            offer_name_snapshot=offer.name,
            offer_slug_snapshot=offer.slug,
            offer_type_snapshot=offer.offer_type,
            total_amount_paise=2900,
            status="PAID",
            paid_at=timezone.now(),
        )
        item = OrderItem.objects.create(order=order, mock_test=mock, price_paise_snapshot=2900)
        MockAccessGrant.objects.create(
            student=user, mock_test=mock, source_order_item=item, granted_at=timezone.now()
        )
    return user


def mutation(question, version=1, *, option=None, numeric="", review=False):
    return {
        "selected_option": option,
        "numeric_answer": numeric,
        "marked_for_review": review,
        "mutation_version": version,
    }
