"""Read-only aggregates for the owner dashboard."""

from django.db.models import BigIntegerField, Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.models import StudentProfile
from apps.commerce.models import Order, Payment
from apps.exams.models import MockTest


def get_owner_overview_metrics(*, now=None) -> dict[str, int]:
    """Return platform totals without loading student, mock, order, or payment rows."""
    now = now or timezone.now()
    paid_order = Q(status=Order.Status.PAID, paid_at__isnull=False)

    mock_metrics = MockTest.objects.aggregate(
        upcoming_mocks=Count(
            "pk",
            filter=Q(
                status__in=(MockTest.Status.REGISTRATION_OPEN, MockTest.Status.SCHEDULED),
                starts_at__gt=now,
            ),
        ),
        completed_mocks=Count(
            "pk",
            filter=Q(
                status__in=(MockTest.Status.CLOSED, MockTest.Status.RESULTS_PUBLISHED),
            ),
        ),
    )
    order_metrics = Order.objects.aggregate(
        paid_orders=Count("pk", filter=paid_order),
        total_revenue_paise=Coalesce(
            Sum("total_amount_paise", filter=paid_order),
            Value(0),
            output_field=BigIntegerField(),
        ),
    )
    payment_metrics = Payment.objects.aggregate(
        failed_payments=Count("pk", filter=Q(status=Payment.Status.FAILED)),
    )

    return {
        "total_students": StudentProfile.objects.filter(
            user__is_staff=False,
            user__is_superuser=False,
        ).count(),
        **mock_metrics,
        **order_metrics,
        **payment_metrics,
    }
