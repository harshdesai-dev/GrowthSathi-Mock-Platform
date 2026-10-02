"""Narrow, replaceable Razorpay boundary. V1 deliberately rejects live keys."""

import razorpay
from django.conf import settings
from razorpay.errors import SignatureVerificationError
from rest_framework.exceptions import APIException, ValidationError


class GatewayUnavailable(APIException):
    status_code = 503
    default_detail = "Payment service unavailable. Retry status verification or contact support."
    default_code = "payment_unavailable"


def public_key():
    key = settings.RAZORPAY_KEY_ID
    if not key.startswith("rzp_test_") or not settings.RAZORPAY_KEY_SECRET:
        raise GatewayUnavailable("Only configured Razorpay test-mode payments are enabled.")
    return key


class RazorpayGateway:
    def __init__(self):
        self.client = razorpay.Client(auth=(public_key(), settings.RAZORPAY_KEY_SECRET))
        self.client.set_app_details({"title": "GrowthSathi", "version": "phase3"})

    def create_order(self, order):
        return self.client.order.create(
            data={
                "amount": order.total_amount_paise,
                "currency": "INR",
                "receipt": order.pk.hex,
                "partial_payment": False,
            },
            timeout=15,
        )

    def fetch_payment(self, payment_id):
        return self.client.payment.fetch(payment_id, timeout=15)

    def fetch_order(self, order_id):
        return self.client.order.fetch(order_id, timeout=15)

    def verify_callback(self, order_id, payment_id, signature):
        try:
            self.client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
        except SignatureVerificationError as exc:
            raise ValidationError("Invalid payment signature.") from exc

    def verify_webhook(self, body, signature):
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            raise GatewayUnavailable("Test webhook secret is not configured.")
        try:
            self.client.utility.verify_webhook_signature(
                body.decode("utf-8"), signature, settings.RAZORPAY_WEBHOOK_SECRET
            )
        except (SignatureVerificationError, UnicodeDecodeError) as exc:
            raise ValidationError("Invalid webhook signature.") from exc
