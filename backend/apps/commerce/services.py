"""All saleability, state transitions and entitlement writes live here.

Lock order: student -> offer/order -> mocks (UUID order). Remote requests are
outside database transactions; durable CREATED receipts survive network failure.
"""

import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.exams.models import MockTest
from apps.exams.services import require_owner
from apps.exams.validation import validate_paper

from .gateway import GatewayUnavailable, RazorpayGateway
from .models import (
    MockAccessGrant,
    MockOffer,
    Order,
    OrderItem,
    Payment,
    PaymentWebhookEvent,
    service_write,
)

SALEABLE_STATUSES = {"REGISTRATION_OPEN", "SCHEDULED", "LIVE"}
PUBLIC_STATUSES = SALEABLE_STATUSES | {"CLOSED", "RESULTS_PUBLISHED", "CANCELLED"}
ORDER_TRANSITIONS = {
    "CREATED": {"PENDING"},
    "PENDING": {"PAID", "FAILED"},
    "FAILED": {"PAID"},
    "PAID": {"REFUNDED"},
    "REFUNDED": set(),
}
REFUND_REASONS = {"MOCK_CANCELLED", "DUPLICATE_VERIFIED_PAYMENT", "PLATFORM_FAILURE"}


@contextmanager
def writing():
    token = service_write.set(True)
    try:
        yield
    finally:
        service_write.reset(token)


def transition(order, status):
    if order.status == status:
        return
    if status not in ORDER_TRANSITIONS[order.status]:
        raise ValidationError("Illegal order transition.")
    order.status = status


def offer_mocks(offer, *, lock=False):
    ids = list(offer.items.values_list("mock_test_id", flat=True))
    query = MockTest.objects.filter(pk__in=ids).order_by("pk")
    if lock:
        query = query.select_for_update()
    return list(query.select_related("exam_type", "exam_scheme"))


def validate_contents(offer, mocks):
    codes = sorted(mock.exam_type.code for mock in mocks)
    expected = {"JEE": ["JEE_MAIN"], "CET": ["MHT_CET_PCM"], "COMBO": ["JEE_MAIN", "MHT_CET_PCM"]}
    if codes != expected.get(offer.offer_type):
        raise ValidationError("Offer must contain exactly the specified JEE/CET mock(s).")


def validate_saleability(offer, *, student=None, mocks=None, require_active=True):
    """Only registration-open/scheduled/live, before end, and fully valid papers."""
    now = timezone.now()
    mocks = offer_mocks(offer) if mocks is None else mocks
    validate_contents(offer, mocks)
    if require_active and not offer.active:
        raise ValidationError("Offer is not active.")
    if not offer.sales_start_at <= now < offer.sales_end_at:
        raise ValidationError("Offer sales window is closed.")
    for mock in mocks:
        if mock.status not in SALEABLE_STATUSES or mock.ends_at <= now:
            raise ValidationError("A mock is unavailable for purchase.")
        if not mock.rules_verified_at or not mock.exam_scheme.active or not mock.exam_type.active:
            raise ValidationError("Mock rules have not been verified or its scheme is inactive.")
        if not validate_paper(mock).valid:
            raise ValidationError("Mock paper is not valid for sale.")
    if student and MockAccessGrant.objects.filter(
        student=student, mock_test__in=mocks, status="ACTIVE"
    ).count() == len(mocks):
        raise ValidationError("You already have active access to every mock in this offer.")
    return mocks


@transaction.atomic
def set_offer_active(offer_id, active, *, actor):
    require_owner(actor)
    offer = MockOffer.objects.select_for_update().get(pk=offer_id)
    if active:
        # Future offers may be activated before their sales window opens.
        mocks = offer_mocks(offer, lock=True)
        validate_contents(offer, mocks)
        for mock in mocks:
            if (
                mock.status not in SALEABLE_STATUSES
                or not mock.rules_verified_at
                or not validate_paper(mock).valid
            ):
                raise ValidationError("Only verified, valid, published mocks can be offered.")
    with writing():
        offer.active = active
        offer.save()
    return offer


def gateway_call(operation):
    try:
        return operation()
    except (ValidationError, GatewayUnavailable):
        raise
    except Exception as exc:
        # Never expose gateway exception bodies, which may contain private information.
        raise GatewayUnavailable() from exc


def validate_gateway_order(order, remote):
    if (
        not isinstance(remote, dict)
        or remote.get("amount") != order.total_amount_paise
        or remote.get("currency") != "INR"
        or remote.get("receipt") != order.pk.hex
        or not isinstance(remote.get("id"), str)
        or not remote["id"].startswith("order_")
    ):
        raise ValidationError("Gateway order does not match the local order.")
    if order.gateway_order_id and remote["id"] != order.gateway_order_id:
        raise ValidationError("Gateway order identity mismatch.")


def create_order(student, offer_id):
    gateway = RazorpayGateway()  # Reject absent/live configuration before creating records.
    with transaction.atomic(), writing():
        student = User.objects.select_for_update().get(pk=student.pk)
        if not hasattr(student, "profile") or not student.profile.onboarding_completed:
            raise ValidationError("Complete student onboarding before purchasing.")
        offer = MockOffer.objects.select_for_update().get(pk=offer_id)
        mocks = validate_saleability(offer, student=student, mocks=offer_mocks(offer, lock=True))
        # Never automatically retry a remote create with an unknown outcome, even after 30m.
        unresolved = Order.objects.filter(student=student, offer=offer, status="CREATED").first()
        if unresolved:
            return unresolved
        existing = (
            Order.objects.filter(
                student=student,
                offer=offer,
                status="PENDING",
                created_at__gte=timezone.now() - timedelta(minutes=30),
            )
            .order_by("-created_at")
            .first()
        )
        if (
            existing
            and existing.total_amount_paise == offer.price_paise
            and set(existing.items.values_list("mock_test_id", flat=True))
            == {mock.pk for mock in mocks}
        ):
            return existing
        order = Order.objects.create(
            student=student,
            offer=offer,
            offer_name_snapshot=offer.name,
            offer_slug_snapshot=offer.slug,
            offer_type_snapshot=offer.offer_type,
            total_amount_paise=offer.price_paise,
        )
        # Equal deterministic integer allocation; remainder assigned in UUID order.
        share, remainder = divmod(offer.price_paise, len(mocks))
        for index, mock in enumerate(mocks):
            OrderItem.objects.create(
                order=order, mock_test=mock, price_paise_snapshot=share + (index < remainder)
            )
    try:
        remote = gateway_call(lambda: gateway.create_order(order))
        validate_gateway_order(order, remote)
        return attach_gateway_order(order.pk, remote)
    except Exception:
        with transaction.atomic(), writing():
            User.objects.select_for_update().get(pk=student.pk)
            order = Order.objects.select_for_update().get(pk=order.pk)
            order.review_required = True
            order.review_note = (
                "Gateway creation outcome unknown; reconcile using the local UUID receipt."
            )
            order.save()
        raise


@transaction.atomic
def attach_gateway_order(order_id, remote):
    original = Order.objects.get(pk=order_id)
    User.objects.select_for_update().get(pk=original.student_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    validate_gateway_order(order, remote)
    if order.status != "CREATED":
        return order
    with writing():
        order.gateway_order_id = remote["id"]
        transition(order, "PENDING")
        order.review_required = False
        order.review_note = ""
        order.save()
    return order


def reconcile_gateway_order(order_id, gateway_order_id, *, actor):
    require_owner(actor)
    gateway = RazorpayGateway()
    remote = gateway_call(lambda: gateway.fetch_order(gateway_order_id))
    return attach_gateway_order(order_id, remote)


def verify_payment(student, order_id, gateway_order_id, payment_id, signature):
    # Ownership check precedes signature checking or any payment lookup at the gateway.
    order = Order.objects.get(pk=order_id, student=student)
    if not order.gateway_order_id or order.gateway_order_id != gateway_order_id:
        raise ValidationError("Payment order mismatch.")
    gateway = RazorpayGateway()
    gateway.verify_callback(order.gateway_order_id, payment_id, signature)
    payment = gateway_call(lambda: gateway.fetch_payment(payment_id))
    if payment.get("id") != payment_id:
        raise ValidationError("Gateway payment identity mismatch.")
    remote_order = gateway_call(lambda: gateway.fetch_order(order.gateway_order_id))
    return reconcile_payment(order.pk, payment, remote_order, signature=signature)


@transaction.atomic
def reconcile_payment(order_id, remote, remote_order, *, signature=""):
    initial = Order.objects.get(pk=order_id)
    User.objects.select_for_update().get(pk=initial.student_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    validate_gateway_order(order, remote_order)
    if (
        not order.gateway_order_id
        or remote.get("order_id") != order.gateway_order_id
        or remote.get("amount") != order.total_amount_paise
        or remote.get("currency") != "INR"
        or not isinstance(remote.get("id"), str)
        or not remote["id"].startswith("pay_")
    ):
        raise ValidationError("Payment does not match the order amount, currency or identity.")
    status = remote.get("status", "").upper()
    if status not in {"AUTHORIZED", "CAPTURED", "FAILED"}:
        raise ValidationError(
            "Payment is not ready for reconciliation; contact support for refunds."
        )
    if status == "CAPTURED" and (
        remote.get("captured") is not True
        or remote_order.get("status") != "paid"
        or remote_order.get("amount_paid") != order.total_amount_paise
    ):
        raise ValidationError("Payment capture is not confirmed by the gateway order.")
    with writing():
        payment = Payment.objects.filter(gateway_payment_id=remote["id"]).first()
        if payment and payment.order_id != order.pk:
            raise ValidationError("Gateway payment already belongs to a different order.")
        if not payment:
            payment = Payment.objects.create(
                order=order,
                gateway_payment_id=remote["id"],
                amount_paise=remote["amount"],
                status=status,
                gateway_signature=signature,
            )
        elif payment.status not in {"CAPTURED", "REFUNDED"}:
            payment.status = status
            payment.gateway_signature = signature or payment.gateway_signature
            payment.save()
        if order.status in {"PAID", "REFUNDED"}:
            if order.payments.filter(status="CAPTURED").count() > 1:
                order.review_required = True
                order.review_note = (
                    "Multiple verified captures: manual duplicate-payment refund review."
                )
                order.save()
            return order
        if status == "CAPTURED":
            transition(order, "PAID")
            order.paid_at = timezone.now()
            order.save()
            items = list(order.items.select_related("mock_test").order_by("mock_test_id"))
            mocks = {
                mock.pk: mock
                for mock in MockTest.objects.select_for_update()
                .filter(pk__in=[item.mock_test_id for item in items])
                .order_by("pk")
            }
            for item in items:
                if MockAccessGrant.objects.filter(
                    student=order.student, mock_test=item.mock_test, status="ACTIVE"
                ).exists():
                    continue
                cancelled = mocks[item.mock_test_id].status == "CANCELLED"
                MockAccessGrant.objects.create(
                    student=order.student,
                    mock_test=item.mock_test,
                    source_order_item=item,
                    status="REVOKED" if cancelled else "ACTIVE",
                    granted_at=timezone.now(),
                    revoked_at=timezone.now() if cancelled else None,
                    revocation_note="Mock cancelled before capture reconciliation."
                    if cancelled
                    else "",
                )
                if cancelled:
                    order.review_required = True
                    order.review_note = (
                        "Captured payment includes a cancelled mock; manual refund review required."
                    )
                    order.save()
        elif status == "FAILED" and order.status == "PENDING":
            transition(order, "FAILED")
            order.save()
    return order


def process_webhook(body, signature, event_id):
    gateway = RazorpayGateway()
    gateway.verify_webhook(body, signature)
    if not event_id or len(event_id) > 150:
        raise ValidationError("Missing or invalid gateway event ID.")
    digest = hashlib.sha256(body).hexdigest()
    previous = PaymentWebhookEvent.objects.filter(gateway_event_id=event_id).first()
    if previous:
        if previous.payload_hash != digest:
            raise ValidationError("Webhook event ID was reused with a different payload.")
        return
    try:
        payload = json.loads(body)
        event_type = payload["event"]
        if not isinstance(event_type, str) or len(event_type) > 60:
            raise ValueError
    except (ValueError, KeyError, TypeError) as exc:
        raise ValidationError("Malformed webhook.") from exc
    if event_type not in {"payment.captured", "payment.failed"}:
        try:
            with transaction.atomic(), writing():
                event, _ = PaymentWebhookEvent.objects.get_or_create(
                    gateway_event_id=event_id,
                    defaults={
                        "event_type": event_type,
                        "payload_hash": digest,
                        "processing_status": "IGNORED",
                        "processed_at": timezone.now(),
                    },
                )
        except ValidationError:
            # Model full_clean may see a concurrent insert before the DB INSERT.
            event = PaymentWebhookEvent.objects.filter(gateway_event_id=event_id).first()
            if event is None:
                raise
        if event.payload_hash != digest:
            raise ValidationError("Webhook event identity mismatch.")
        return
    try:
        entity = payload["payload"]["payment"]["entity"]
        payment_id, gateway_order_id = entity["id"], entity["order_id"]
    except (KeyError, TypeError) as exc:
        raise ValidationError("Malformed payment event.") from exc
    order = Order.objects.filter(gateway_order_id=gateway_order_id).first()
    if order is None:
        # A remote-create response may have been lost. Keep retryable, never grant unknown orders.
        raise GatewayUnavailable(
            "Gateway order is not linked locally; owner reconciliation required."
        )
    remote = gateway_call(lambda: gateway.fetch_payment(payment_id))
    if remote.get("id") != payment_id:
        raise ValidationError("Gateway payment identity mismatch.")
    remote_order = gateway_call(lambda: gateway.fetch_order(gateway_order_id))
    with transaction.atomic(), writing():
        User.objects.select_for_update().get(pk=order.student_id)
        event, created = PaymentWebhookEvent.objects.get_or_create(
            gateway_event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload_hash": digest,
                "processed_at": timezone.now(),
            },
        )
        if event.payload_hash != digest:
            raise ValidationError("Webhook event identity mismatch.")
        if created:
            reconcile_payment(order.pk, remote, remote_order)


@transaction.atomic
def revoke_access(grant_id, *, actor, note):
    require_owner(actor)
    if not note.strip():
        raise ValidationError("A reason is required.")
    initial = MockAccessGrant.objects.get(pk=grant_id)
    User.objects.select_for_update().get(pk=initial.student_id)
    grant = MockAccessGrant.objects.select_for_update().get(pk=grant_id)
    if grant.status != "ACTIVE":
        return grant
    with writing():
        grant.status = "REVOKED"
        grant.revoked_at = timezone.now()
        grant.revoked_by = actor
        grant.revocation_note = note
        grant.save()
    return grant


@transaction.atomic
def record_manual_refund(order_id, *, actor, reason, reference):
    """Record an already verified, full-order refund; never initiates money movement."""
    require_owner(actor)
    if reason not in REFUND_REASONS or not reference.strip():
        raise ValidationError(
            "An eligible refund reason and verified gateway reference are required."
        )
    original = Order.objects.get(pk=order_id)
    User.objects.select_for_update().get(pk=original.student_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == "REFUNDED":
        if order.refund_reference != reference or order.refund_reason != reason:
            raise ValidationError("Refund audit is immutable.")
        return order
    with writing():
        transition(order, "REFUNDED")
        order.refunded_at = timezone.now()
        order.refund_reference = reference
        order.refund_reason = reason
        order.refund_recorded_by = actor
        order.save()
        for payment in order.payments.filter(status="CAPTURED"):
            payment.status = "REFUNDED"
            payment.save()
        for grant in MockAccessGrant.objects.filter(
            source_order_item__order=order, status="ACTIVE"
        ):
            # A partially overlapping combo may still pay for this mock independently.
            replacement = (
                OrderItem.objects.filter(
                    order__student=order.student, order__status="PAID", mock_test=grant.mock_test
                )
                .exclude(order=order)
                .order_by("created_at")
                .first()
            )
            if replacement:
                grant.source_order_item = replacement
            else:
                grant.status = "REFUNDED"
                grant.revoked_at = timezone.now()
                grant.revoked_by = actor
                grant.revocation_note = reason
            grant.save()
    return order
