"""Commerce aggregates. Financial records can only be mutated by domain services."""

from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.exams.models import Entity

service_write = ContextVar("commerce_service_write", default=False)


class MockOffer(Entity):
    class Type(models.TextChoices):
        JEE = "JEE", "JEE Main"
        CET = "CET", "MHT-CET PCM"
        COMBO = "COMBO", "JEE + CET"

    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    offer_type = models.CharField(max_length=5, choices=Type.choices)
    price_paise = models.PositiveIntegerField(
        blank=True, help_text="Leave blank for initial pricing: JEE/CET 2900, combo 5000 paise."
    )
    active = models.BooleanField(default=False)
    sales_start_at = models.DateTimeField()
    sales_end_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_paise__gt=0), name="offer_price_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(offer_type__in=["JEE", "CET", "COMBO"]), name="offer_type_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(sales_end_at__gt=models.F("sales_start_at")),
                name="offer_sales_window",
            ),
        ]

    def __str__(self):
        return self.name

    def guard(self):
        if self._state.adding and self.price_paise is None:
            self.price_paise = 5000 if self.offer_type == self.Type.COMBO else 2900
        old = None if self._state.adding else MockOffer.objects.select_for_update().get(pk=self.pk)
        if not service_write.get() and (self.active or (old and old.active)):
            raise ValidationError("Deactivate the offer before editing. Use the activation action.")


class MockOfferItem(Entity):
    offer = models.ForeignKey(MockOffer, on_delete=models.PROTECT, related_name="items")
    mock_test = models.ForeignKey(
        "exams.MockTest", on_delete=models.PROTECT, related_name="offer_items"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offer", "mock_test"], name="offer_mock_unique")
        ]

    def __str__(self):
        return f"{self.offer}: {self.mock_test}"

    def guard(self):
        if (
            not self._state.adding
            and MockOfferItem.objects.get(pk=self.pk).offer_id != self.offer_id
        ):
            raise ValidationError("An offer item cannot be moved between offers.")
        offer = MockOffer.objects.select_for_update().get(pk=self.offer_id)
        if offer.active:
            raise ValidationError("Deactivate the offer before editing its contents.")


class FinancialRecord(Entity):
    class Meta:
        abstract = True

    def guard(self):
        if not service_write.get():
            raise ValidationError("Financial records are read-only; use commerce services.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Financial records must be retained for reconciliation.")


class Order(FinancialRecord):
    class Status(models.TextChoices):
        CREATED = "CREATED"
        PENDING = "PENDING"
        PAID = "PAID"
        FAILED = "FAILED"
        REFUNDED = "REFUNDED"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    offer = models.ForeignKey(MockOffer, on_delete=models.PROTECT, related_name="orders")
    offer_name_snapshot = models.CharField(max_length=160)
    offer_slug_snapshot = models.SlugField()
    offer_type_snapshot = models.CharField(max_length=5, choices=MockOffer.Type.choices)
    total_amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR", editable=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CREATED)
    gateway_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    review_required = models.BooleanField(default=False)
    review_note = models.CharField(max_length=250, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(max_length=100, blank=True)
    refund_reason = models.CharField(max_length=40, blank=True)
    refund_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recorded_refunds",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount_paise__gt=0), name="order_amount_positive"
            ),
            models.CheckConstraint(condition=models.Q(currency="INR"), name="order_currency_inr"),
            models.CheckConstraint(
                condition=models.Q(status__in=["CREATED", "PENDING", "PAID", "FAILED", "REFUNDED"]),
                name="order_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["student", "offer", "created_at"])]

    def __str__(self):
        return f"{self.id} / {self.status}"

    def clean(self):
        if not self._state.adding:
            old = Order.objects.get(pk=self.pk)
            fields = [
                "student_id",
                "offer_id",
                "offer_name_snapshot",
                "offer_slug_snapshot",
                "offer_type_snapshot",
                "total_amount_paise",
                "currency",
            ]
            if any(getattr(old, field) != getattr(self, field) for field in fields):
                raise ValidationError("Order snapshots are immutable.")
            if old.gateway_order_id and old.gateway_order_id != self.gateway_order_id:
                raise ValidationError("Gateway order identity is immutable.")


class OrderItem(FinancialRecord):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    mock_test = models.ForeignKey(
        "exams.MockTest", on_delete=models.PROTECT, related_name="order_items"
    )
    price_paise_snapshot = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "mock_test"], name="order_mock_unique")
        ]

    def __str__(self):
        return f"{self.order_id}: {self.mock_test_id}"

    def clean(self):
        if not self._state.adding:
            raise ValidationError("Order items are immutable.")


class Payment(FinancialRecord):
    class Status(models.TextChoices):
        AUTHORIZED = "AUTHORIZED"
        CAPTURED = "CAPTURED"
        FAILED = "FAILED"
        REFUNDED = "REFUNDED"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=8, default="RAZORPAY", editable=False)
    gateway_payment_id = models.CharField(max_length=100, unique=True)
    gateway_signature = models.CharField(max_length=64, blank=True)
    amount_paise = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paise__gt=0), name="payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(gateway="RAZORPAY"), name="payment_gateway_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["AUTHORIZED", "CAPTURED", "FAILED", "REFUNDED"]),
                name="payment_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.gateway_payment_id}: {self.status}"


class PaymentWebhookEvent(FinancialRecord):
    gateway_event_id = models.CharField(max_length=150, unique=True)
    event_type = models.CharField(max_length=60)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_status = models.CharField(
        max_length=10,
        default="PROCESSED",
        choices=[("PROCESSED", "Processed"), ("IGNORED", "Ignored")],
    )
    payload_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(processing_status__in=["PROCESSED", "IGNORED"]),
                name="webhook_status_valid",
            )
        ]

    def __str__(self):
        return f"{self.gateway_event_id}: {self.event_type}"


class MockAccessGrant(FinancialRecord):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        REVOKED = "REVOKED"
        REFUNDED = "REFUNDED"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mock_access"
    )
    mock_test = models.ForeignKey(
        "exams.MockTest", on_delete=models.PROTECT, related_name="access_grants"
    )
    source_order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="access_grants"
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    granted_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_note = models.CharField(max_length=250, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="revoked_grants",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "mock_test"],
                condition=models.Q(status="ACTIVE"),
                name="one_active_mock_access",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "REVOKED", "REFUNDED"]),
                name="access_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.student_id}: {self.mock_test_id} / {self.status}"

    def clean(self):
        item = self.source_order_item
        if item.mock_test_id != self.mock_test_id or item.order.student_id != self.student_id:
            raise ValidationError("Access must belong to the purchasing student and mock.")
        if self.status == self.Status.ACTIVE and item.order.status != Order.Status.PAID:
            raise ValidationError("Active access requires a paid order.")
