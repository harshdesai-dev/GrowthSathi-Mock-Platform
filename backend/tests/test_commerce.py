import hashlib
import hmac
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Lock
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    models,
    transaction,
)
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import StudentProfile, User
from apps.commerce.gateway import GatewayUnavailable, RazorpayGateway
from apps.commerce.models import (
    MockAccessGrant,
    MockOffer,
    MockOfferItem,
    Order,
    Payment,
    PaymentWebhookEvent,
)
from apps.commerce.services import (
    create_order,
    process_webhook,
    reconcile_gateway_order,
    record_manual_refund,
    revoke_access,
    set_offer_active,
    validate_saleability,
    verify_payment,
    writing,
)
from apps.exams.models import ExamScheme
from apps.exams.services import transition_mock
from tests.test_exam_administration import make_mock, populate, verify

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_superuser(
        email="commerce-owner@example.com", google_sub="commerce-owner"
    )


@pytest.fixture
def schemes():
    call_command("seed_exam_schemes", stdout=io.StringIO())
    return {
        scheme.exam_type.code: scheme for scheme in ExamScheme.objects.select_related("exam_type")
    }


@pytest.fixture
def student():
    user = User.objects.create_user(email="buyer@example.com", google_sub="buyer")
    StudentProfile.objects.update_or_create(
        user=user, defaults={"full_name": "Buyer", "onboarding_completed": True}
    )
    return user


@pytest.fixture
def catalogue(schemes, owner):
    mocks = {}
    for code, scheme in schemes.items():
        mock = make_mock(scheme, slug=code.lower())
        populate(mock, owner)
        verify(mock, owner)
        transition_mock(mock.pk, "REGISTRATION_OPEN", actor=owner)
        mock.refresh_from_db()
        mocks[code] = mock
    offers = {}
    for kind, codes, amount in [
        ("JEE", ["JEE_MAIN"], 2900),
        ("CET", ["MHT_CET_PCM"], 2900),
        ("COMBO", ["JEE_MAIN", "MHT_CET_PCM"], 5000),
    ]:
        offer = MockOffer.objects.create(
            name=kind,
            slug=kind.lower(),
            offer_type=kind,
            price_paise=amount,
            sales_start_at=timezone.now() - timedelta(days=1),
            sales_end_at=timezone.now() + timedelta(days=1),
        )
        for code in codes:
            MockOfferItem.objects.create(offer=offer, mock_test=mocks[code])
        set_offer_active(offer.pk, True, actor=owner)
        offer.refresh_from_db()
        offers[kind] = offer
    return mocks, offers


@pytest.fixture
def gateway(settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_fixture"
    settings.RAZORPAY_KEY_SECRET = "test-only-key-secret"
    settings.RAZORPAY_WEBHOOK_SECRET = "test-only-webhook-secret"
    remote_orders = {}
    payments = {}
    mutex = Lock()

    def create(local):
        with mutex:
            value = {
                "id": "order_" + local.pk.hex,
                "amount": local.total_amount_paise,
                "currency": "INR",
                "receipt": local.pk.hex,
                "status": "created",
                "amount_paid": 0,
            }
            remote_orders[value["id"]] = value
            return value.copy()

    # Real SDK HMAC utilities are exercised; only network operations are replaced.
    with (
        patch.object(RazorpayGateway, "create_order", side_effect=create) as create_mock,
        patch.object(
            RazorpayGateway,
            "fetch_order",
            side_effect=lambda identity: remote_orders[identity].copy(),
        ),
        patch.object(
            RazorpayGateway, "fetch_payment", side_effect=lambda identity: payments[identity].copy()
        ),
    ):
        yield {"orders": remote_orders, "payments": payments, "create": create_mock}


def remote_payment(order, gateway, *, identity="pay_sample", status="captured"):
    remote = {
        "id": identity,
        "order_id": order.gateway_order_id,
        "amount": order.total_amount_paise,
        "currency": "INR",
        "status": status,
        "captured": status == "captured",
    }
    gateway["payments"][identity] = remote
    if status == "captured":
        gateway["orders"][order.gateway_order_id].update(
            status="paid", amount_paid=order.total_amount_paise
        )
    return remote


def sign(value, secret="test-only-key-secret"):
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def callback(order, student, identity="pay_sample"):
    return verify_payment(
        student,
        order.pk,
        order.gateway_order_id,
        identity,
        sign(f"{order.gateway_order_id}|{identity}"),
    )


def webhook(order, *, event="payment.captured", identity="pay_sample", event_id="evt_sample"):
    body = json.dumps(
        {
            "event": event,
            "payload": {
                "payment": {"entity": {"id": identity, "order_id": order.gateway_order_id}}
            },
        }
    ).encode()
    return body, sign(body.decode(), "test-only-webhook-secret"), event_id


@pytest.mark.parametrize(
    "kind,count,amount", [("JEE", 1, 2900), ("CET", 1, 2900), ("COMBO", 2, 5000)]
)
def test_offer_order_and_access(catalogue, student, gateway, kind, count, amount):
    offer = catalogue[1][kind]
    assert len(validate_saleability(offer)) == count
    order = create_order(student, offer.pk)
    assert order.total_amount_paise == amount
    assert order.items.count() == count
    assert sum(order.items.values_list("price_paise_snapshot", flat=True)) == amount
    assert not MockAccessGrant.objects.exists()
    remote_payment(order, gateway)
    callback(order, student)
    assert MockAccessGrant.objects.filter(status="ACTIVE").count() == count
    assert set(MockAccessGrant.objects.values_list("mock_test_id", flat=True)) == set(
        offer.items.values_list("mock_test_id", flat=True)
    )
    with pytest.raises(ValidationError, match="already"):
        create_order(student, offer.pk)


def test_offer_structure_and_duplicate(catalogue, owner):
    offer = catalogue[1]["COMBO"]
    set_offer_active(offer.pk, False, actor=owner)
    offer.refresh_from_db()
    with pytest.raises(ValidationError):
        MockOfferItem.objects.create(offer=offer, mock_test=catalogue[0]["JEE_MAIN"])
    offer.items.get(mock_test=catalogue[0]["MHT_CET_PCM"]).delete()
    with pytest.raises(ValidationError, match="exactly"):
        set_offer_active(offer.pk, True, actor=owner)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "DRAFT"),
        ("status", "CLOSED"),
        ("status", "CANCELLED"),
        ("rules_verified_at", None),
        ("ends_at", "past"),
    ],
)
def test_unavailable_mocks_not_sold(catalogue, student, gateway, field, value):
    mock = catalogue[0]["JEE_MAIN"]
    if value == "past":
        value = timezone.now() - timedelta(seconds=1)
        models.QuerySet.update(
            type(mock).objects.filter(pk=mock.pk), starts_at=value - timedelta(hours=3)
        )
    models.QuerySet.update(type(mock).objects.filter(pk=mock.pk), **{field: value})
    with pytest.raises(ValidationError):
        create_order(student, catalogue[1]["JEE"].pk)
    gateway["create"].assert_not_called()


def test_invalid_paper_and_scheme_not_sold(catalogue, student, gateway):
    mock = catalogue[0]["JEE_MAIN"]
    question = mock.questions.first()
    models.QuerySet.update(type(question).objects.filter(pk=question.pk), positive_marks=99)
    with pytest.raises(ValidationError, match="not valid"):
        create_order(student, catalogue[1]["JEE"].pk)


def test_sales_window_and_inactive(catalogue, student, gateway, owner):
    offer = catalogue[1]["JEE"]
    set_offer_active(offer.pk, False, actor=owner)
    with pytest.raises(ValidationError, match="not active"):
        create_order(student, offer.pk)
    offer.refresh_from_db()
    offer.sales_start_at = timezone.now() + timedelta(hours=2)
    offer.save()
    set_offer_active(offer.pk, True, actor=owner)
    with pytest.raises(ValidationError, match="window"):
        create_order(student, offer.pk)


def test_price_and_contents_are_snapshots(catalogue, student, gateway, owner):
    offer = catalogue[1]["COMBO"]
    order = create_order(student, offer.pk)
    snapshots = list(order.items.values_list("mock_test_id", "price_paise_snapshot"))
    set_offer_active(offer.pk, False, actor=owner)
    offer.refresh_from_db()
    offer.price_paise = 5101
    offer.name = "New price"
    offer.save()
    set_offer_active(offer.pk, True, actor=owner)
    new = create_order(student, offer.pk)
    order.refresh_from_db()
    assert order.total_amount_paise == 5000 and order.offer_name_snapshot == "COMBO"
    assert list(order.items.values_list("mock_test_id", "price_paise_snapshot")) == snapshots
    assert sum(new.items.values_list("price_paise_snapshot", flat=True)) == 5101
    with writing(), pytest.raises(ValidationError, match="immutable"):
        order.total_amount_paise = 9
        order.save()


def test_repeated_create_reuses_gateway_order(catalogue, student, gateway):
    first = create_order(student, catalogue[1]["JEE"].pk)
    second = create_order(student, catalogue[1]["JEE"].pk)
    assert first.pk == second.pk
    assert gateway["create"].call_count == 1


def test_unknown_create_retained_and_reconciled(catalogue, student, gateway, owner):
    original = gateway["create"].side_effect

    def timeout(order):
        original(order)
        raise TimeoutError()

    gateway["create"].side_effect = timeout
    with pytest.raises(GatewayUnavailable):
        create_order(student, catalogue[1]["JEE"].pk)
    order = Order.objects.get()
    assert order.status == "CREATED" and order.review_required
    assert create_order(student, catalogue[1]["JEE"].pk).pk == order.pk
    assert gateway["create"].call_count == 1
    reconciled = reconcile_gateway_order(order.pk, next(iter(gateway["orders"])), actor=owner)
    assert reconciled.status == "PENDING"


def test_repeated_callback_and_webhook_are_idempotent(catalogue, student, gateway):
    order = create_order(student, catalogue[1]["COMBO"].pk)
    remote_payment(order, gateway)
    paid = callback(order, student)
    paid_at = paid.paid_at
    callback(order, student)
    process_webhook(*webhook(order))
    process_webhook(*webhook(order))
    order.refresh_from_db()
    assert order.status == "PAID" and order.paid_at == paid_at
    assert Payment.objects.count() == PaymentWebhookEvent.objects.count() == 1
    assert MockAccessGrant.objects.count() == 2


@pytest.mark.parametrize(
    "alteration", ["amount", "currency", "order_id", "captured", "receipt", "amount_paid"]
)
def test_gateway_mismatch_rejected(catalogue, student, gateway, alteration):
    order = create_order(student, catalogue[1]["JEE"].pk)
    payment = remote_payment(order, gateway)
    if alteration in {"receipt", "amount_paid"}:
        gateway["orders"][order.gateway_order_id][alteration] = "wrong"
    else:
        payment[alteration] = "wrong"
    with pytest.raises(ValidationError):
        callback(order, student)
    assert not MockAccessGrant.objects.exists()


def test_bad_signature_no_gateway_fetch(catalogue, student, gateway):
    from rest_framework.exceptions import ValidationError as APIValidationError

    order = create_order(student, catalogue[1]["JEE"].pk)
    with patch.object(RazorpayGateway, "fetch_payment") as fetch, pytest.raises(APIValidationError):
        verify_payment(student, order.pk, order.gateway_order_id, "pay_sample", "0" * 64)
    fetch.assert_not_called()


def test_failed_then_captured_and_stale_failure(catalogue, student, gateway):
    order = create_order(student, catalogue[1]["JEE"].pk)
    remote_payment(order, gateway, status="failed")
    process_webhook(*webhook(order, event="payment.failed", event_id="evt_failed"))
    order.refresh_from_db()
    assert order.status == "FAILED" and not MockAccessGrant.objects.exists()
    remote_payment(order, gateway)
    callback(order, student)
    remote_payment(order, gateway, identity="pay_fail2", status="failed")
    process_webhook(
        *webhook(order, event="payment.failed", identity="pay_fail2", event_id="evt_late")
    )
    order.refresh_from_db()
    assert order.status == "PAID" and MockAccessGrant.objects.count() == 1


def test_authorized_not_unlocked(catalogue, student, gateway):
    order = create_order(student, catalogue[1]["JEE"].pk)
    remote_payment(order, gateway, status="authorized")
    assert callback(order, student).status == "PENDING"
    assert not MockAccessGrant.objects.exists()


def test_cross_order_payment_identity_rejected(catalogue, student, gateway):
    first = create_order(student, catalogue[1]["JEE"].pk)
    second = create_order(student, catalogue[1]["CET"].pk)
    remote_payment(first, gateway)
    callback(first, student)
    remote_payment(second, gateway)
    with pytest.raises(ValidationError, match="different order"):
        callback(second, student)
    assert Payment.objects.count() == 1


def test_revoke_and_refund_do_not_resurrect(catalogue, student, gateway, owner):
    order = create_order(student, catalogue[1]["COMBO"].pk)
    remote_payment(order, gateway)
    callback(order, student)
    grant = MockAccessGrant.objects.first()
    revoke_access(grant.pk, actor=owner, note="Confirmed platform failure")
    callback(order, student)
    assert MockAccessGrant.objects.filter(status="ACTIVE").count() == 1
    record_manual_refund(
        order.pk, actor=owner, reason="PLATFORM_FAILURE", reference="rfnd_verified"
    )
    callback(order, student)
    assert not MockAccessGrant.objects.filter(status="ACTIVE").exists()
    order.refresh_from_db()
    assert order.status == "REFUNDED" and order.refund_recorded_by == owner


def test_partial_overlap_and_refund_preserve_other_paid_coverage(
    catalogue, student, gateway, owner
):
    single = create_order(student, catalogue[1]["JEE"].pk)
    remote_payment(single, gateway)
    callback(single, student)
    combo = create_order(student, catalogue[1]["COMBO"].pk)
    remote_payment(combo, gateway, identity="pay_combo")
    callback(combo, student, "pay_combo")
    assert MockAccessGrant.objects.filter(status="ACTIVE").count() == 2
    record_manual_refund(
        single.pk, actor=owner, reason="DUPLICATE_VERIFIED_PAYMENT", reference="rfnd_single"
    )
    assert MockAccessGrant.objects.filter(status="ACTIVE").count() == 2
    assert not MockAccessGrant.objects.filter(
        source_order_item__order=single, status="ACTIVE"
    ).exists()


def test_cancelled_during_checkout_not_granted(catalogue, student, gateway, owner):
    order = create_order(student, catalogue[1]["JEE"].pk)
    transition_mock(catalogue[0]["JEE_MAIN"].pk, "CANCELLED", actor=owner)
    remote_payment(order, gateway)
    result = callback(order, student)
    assert result.status == "PAID" and result.review_required
    assert not MockAccessGrant.objects.filter(status="ACTIVE").exists()


def test_api_security_and_safe_payloads(catalogue, student, gateway):
    client = APIClient()
    offers = client.get("/api/v1/offers/")
    assert offers.status_code == 200 and len(offers.data) == 3
    mocks = client.get("/api/v1/mocks/")
    assert mocks.status_code == 200 and len(mocks.data) == 2
    for forbidden in (
        "correct_option",
        "numeric_answer",
        "explanation",
        "rules_source_notes",
        "questions",
        "test-only-key-secret",
    ):
        assert forbidden not in json.dumps(offers.data) + json.dumps(mocks.data)
    assert (
        client.post("/api/v1/orders/", {"offer_id": str(catalogue[1]["JEE"].pk)}).status_code == 401
    )
    client.force_authenticate(student)
    for extra in ("amount", "price", "mock_ids"):
        assert (
            client.post(
                "/api/v1/orders/",
                {"offer_id": str(catalogue[1]["JEE"].pk), extra: 1},
                format="json",
            ).status_code
            == 400
        )
    order = create_order(student, catalogue[1]["JEE"].pk)
    assert client.get(f"/api/v1/orders/{order.pk}/").data["checkout"]["key"] == "rzp_test_fixture"
    other = User.objects.create_user(email="other@example.com", google_sub="other")
    client.force_authenticate(other)
    assert client.get(f"/api/v1/orders/{order.pk}/").status_code == 404
    with patch.object(RazorpayGateway, "fetch_payment") as fetch:
        result = client.post(
            "/api/v1/payments/verify/",
            {
                "order_id": str(order.pk),
                "razorpay_order_id": order.gateway_order_id,
                "razorpay_payment_id": "pay_sample",
                "razorpay_signature": "0" * 64,
            },
            format="json",
        )
    assert result.status_code == 404
    fetch.assert_not_called()
    client.force_authenticate(student)
    assert (
        client.get(f"/api/v1/mocks/{catalogue[0]['JEE_MAIN'].pk}/access/").data["has_access"]
        is False
    )


def test_webhook_signature_and_retry_rollback(catalogue, student, gateway):
    order = create_order(student, catalogue[1]["JEE"].pk)
    remote_payment(order, gateway)
    body, signature, event_id = webhook(order)
    client = APIClient()
    url = "/api/v1/payments/webhook/"
    assert (
        client.post(
            url,
            body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="0" * 64,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        ).status_code
        == 400
    )
    assert not PaymentWebhookEvent.objects.exists()
    with patch.object(RazorpayGateway, "fetch_payment", side_effect=TimeoutError):
        assert (
            client.post(
                url,
                body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID=event_id,
            ).status_code
            == 503
        )
    assert not PaymentWebhookEvent.objects.exists()
    for _ in range(2):
        assert (
            client.post(
                url,
                body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID=event_id,
            ).status_code
            == 200
        )
    assert (
        PaymentWebhookEvent.objects.count()
        == Payment.objects.count()
        == MockAccessGrant.objects.count()
        == 1
    )


def test_owner_admin_and_financial_records_readonly(catalogue, student, gateway, owner):
    client = APIClient()
    client.force_login(student)
    assert client.get("/admin/commerce/order/").status_code == 302
    client.force_login(owner)
    assert client.get("/admin/commerce/order/").status_code == 200
    order = create_order(student, catalogue[1]["JEE"].pk)
    with pytest.raises(ValidationError):
        order.save()
    with pytest.raises(ValidationError):
        Order.objects.filter(pk=order.pk).update(status="PAID")
    with pytest.raises(ValidationError):
        order.items.first().delete()


def test_test_mode_guard(settings):
    settings.RAZORPAY_KEY_ID = "rzp_live_forbidden"
    settings.RAZORPAY_KEY_SECRET = "not-real"
    with pytest.raises(GatewayUnavailable):
        RazorpayGateway()


@pytest.mark.parametrize("kind,expected", [("JEE", 2900), ("CET", 2900), ("COMBO", 5000)])
def test_initial_offer_prices(kind, expected):
    offer = MockOffer.objects.create(
        name=kind,
        slug=kind.lower(),
        offer_type=kind,
        sales_start_at=timezone.now(),
        sales_end_at=timezone.now() + timedelta(days=1),
    )
    assert offer.price_paise == expected


def test_wrong_gateway_order_and_bad_refund_reason(catalogue, student, gateway, owner):
    order = create_order(student, catalogue[1]["JEE"].pk)
    with pytest.raises(ValidationError, match="mismatch"):
        verify_payment(student, order.pk, "order_other", "pay_sample", "0" * 64)
    remote_payment(order, gateway)
    callback(order, student)
    for reason in ("NO_SHOW", "LATE_ARRIVAL", "STUDENT_INTERNET"):
        with pytest.raises(ValidationError, match="eligible"):
            record_manual_refund(order.pk, actor=owner, reason=reason, reference="rfnd_test")
    assert MockAccessGrant.objects.filter(status="ACTIVE").count() == 1


def test_inactive_scheme_and_unfinished_profile(catalogue, student, gateway):
    mock = catalogue[0]["JEE_MAIN"]
    models.QuerySet.update(ExamScheme.objects.filter(pk=mock.exam_scheme_id), active=False)
    with pytest.raises(ValidationError, match="inactive"):
        create_order(student, catalogue[1]["JEE"].pk)
    student.profile.onboarding_completed = False
    student.profile.save()
    with pytest.raises(ValidationError, match="onboarding"):
        create_order(student, catalogue[1]["CET"].pk)


def test_webhook_reused_id_different_body_rejected(catalogue, student, gateway):
    order = create_order(student, catalogue[1]["JEE"].pk)
    remote_payment(order, gateway)
    process_webhook(*webhook(order))
    with pytest.raises(ValidationError, match="different payload"):
        process_webhook(*webhook(order, event="payment.failed"))
    assert PaymentWebhookEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_ignored_webhook_duplicates(gateway):
    body = b'{"event":"unhandled.test.event"}'
    args = (body, sign(body.decode(), "test-only-webhook-secret"), "evt_ignored")
    if connection.vendor == "postgresql":
        race(lambda: process_webhook(*args), lambda: process_webhook(*args))
    else:
        process_webhook(*args)
        process_webhook(*args)
    event = PaymentWebhookEvent.objects.get()
    assert event.processing_status == "IGNORED"
    assert not Payment.objects.exists()


def test_active_offer_edits_and_non_owner_operations_rejected(catalogue, student, owner):
    from django.core.exceptions import PermissionDenied

    offer = catalogue[1]["JEE"]
    with pytest.raises(ValidationError, match="Deactivate"):
        offer.price_paise = 100
        offer.save()
    with pytest.raises(PermissionDenied):
        set_offer_active(offer.pk, False, actor=student)
    client = APIClient()
    staff = User.objects.create_user(
        email="commerce-staff@example.com", google_sub="commerce-staff", is_staff=True
    )
    client.force_login(staff)
    assert client.get("/admin/commerce/payment/").status_code in {302, 403}


def race(*operations):
    barrier = Barrier(len(operations))

    def worker(operation):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        return list(executor.map(worker, operations))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "scenario", ["callbacks", "callback_webhook", "webhooks", "create", "constraint"]
)
def test_postgres_concurrency(catalogue, student, gateway, scenario):
    if connection.vendor != "postgresql":
        pytest.skip("Real row-lock semantics require PostgreSQL.")
    offer = catalogue[1]["COMBO"]
    if scenario == "create":
        orders = race(
            lambda: create_order(student, offer.pk), lambda: create_order(student, offer.pk)
        )
        assert orders[0].pk == orders[1].pk
        assert gateway["create"].call_count == 1
        assert Order.objects.count() == 1
        return
    order = create_order(student, offer.pk)
    remote_payment(order, gateway)
    if scenario == "constraint":
        callback(order, student)
        grant = MockAccessGrant.objects.first()

        def duplicate():
            try:
                with transaction.atomic():
                    # Bypass model validation to prove the DB partial unique constraint.
                    duplicate = MockAccessGrant(
                        student_id=student.pk,
                        mock_test_id=grant.mock_test_id,
                        source_order_item_id=grant.source_order_item_id,
                        granted_at=timezone.now(),
                    )
                    models.Model.save(duplicate, force_insert=True)
            except IntegrityError:
                return "blocked"

        assert race(duplicate, duplicate) == ["blocked", "blocked"]
    elif scenario == "callbacks":
        race(lambda: callback(order, student), lambda: callback(order, student))
    elif scenario == "webhooks":
        race(lambda: process_webhook(*webhook(order)), lambda: process_webhook(*webhook(order)))
    else:
        race(lambda: callback(order, student), lambda: process_webhook(*webhook(order)))
    order.refresh_from_db()
    assert order.status == "PAID"
    assert Payment.objects.count() == 1
    assert MockAccessGrant.objects.count() == 2
