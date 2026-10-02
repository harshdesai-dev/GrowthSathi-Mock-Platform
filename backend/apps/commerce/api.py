from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import path
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exams.models import MockTest

from .gateway import GatewayUnavailable, public_key
from .models import MockAccessGrant, MockOffer, Order, OrderItem
from .services import (
    PUBLIC_STATUSES,
    create_order,
    process_webhook,
    validate_saleability,
    verify_payment,
)


class MockSerializer(serializers.ModelSerializer):
    exam = serializers.CharField(source="exam_type.code")
    scheme_version = serializers.CharField(source="exam_scheme.version")

    class Meta:
        model = MockTest
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "exam",
            "scheme_version",
            "status",
            "starts_at",
            "ends_at",
        )


class OfferSerializer(serializers.ModelSerializer):
    mocks = MockSerializer(source="student_mocks", many=True)
    available = serializers.SerializerMethodField()

    class Meta:
        model = MockOffer
        fields = (
            "id",
            "name",
            "slug",
            "offer_type",
            "price_paise",
            "sales_start_at",
            "sales_end_at",
            "mocks",
            "available",
        )

    def get_available(self, obj) -> bool:
        try:
            validate_saleability(obj)
            return True
        except DjangoValidationError:
            return False


class OrderItemSerializer(serializers.ModelSerializer):
    mock = MockSerializer(source="mock_test")

    class Meta:
        model = OrderItem
        fields = ("id", "mock", "price_paise_snapshot")


class CheckoutSerializer(serializers.Serializer):
    key = serializers.CharField()
    order_id = serializers.CharField()
    amount = serializers.IntegerField()
    currency = serializers.CharField()
    description = serializers.CharField()


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    checkout = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "offer_name_snapshot",
            "total_amount_paise",
            "currency",
            "status",
            "created_at",
            "paid_at",
            "items",
            "checkout",
        )

    @extend_schema_field(CheckoutSerializer(allow_null=True))
    def get_checkout(self, obj):
        if obj.status != "PENDING" or not obj.gateway_order_id:
            return None
        try:
            # Old pending orders cannot initiate checkout after an offer is changed/closed.
            mocks = validate_saleability(obj.offer, student=obj.student)
            if obj.total_amount_paise != obj.offer.price_paise or {m.pk for m in mocks} != set(
                obj.items.values_list("mock_test_id", flat=True)
            ):
                return None
            return {
                "key": public_key(),
                "order_id": obj.gateway_order_id,
                "amount": obj.total_amount_paise,
                "currency": "INR",
                "description": obj.offer_name_snapshot,
            }
        except (DjangoValidationError, GatewayUnavailable):
            return None


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({"non_field_errors": ["Unexpected request fields."]})
        return super().to_internal_value(data)


class CreateOrderSerializer(StrictSerializer):
    offer_id = serializers.UUIDField()


class VerifySerializer(StrictSerializer):
    order_id = serializers.UUIDField()
    razorpay_order_id = serializers.RegexField(r"^order_[A-Za-z0-9]+$", max_length=100)
    razorpay_payment_id = serializers.RegexField(r"^pay_[A-Za-z0-9]+$", max_length=100)
    razorpay_signature = serializers.RegexField(r"^[a-fA-F0-9]{64}$")


class AccessSerializer(serializers.ModelSerializer):
    mock = MockSerializer(source="mock_test")
    has_access = serializers.SerializerMethodField()

    class Meta:
        model = MockAccessGrant
        fields = ("id", "mock", "status", "granted_at", "has_access")

    def get_has_access(self, obj) -> bool:
        return obj.status == "ACTIVE" and obj.mock_test.status != "CANCELLED"


class MockAccessSerializer(serializers.Serializer):
    has_access = serializers.BooleanField()
    grants = AccessSerializer(many=True)


class AcknowledgedSerializer(serializers.Serializer):
    received = serializers.BooleanField()


class WebhookPayloadSerializer(serializers.Serializer):
    event = serializers.CharField()
    payload = serializers.JSONField(required=False)


class CommerceView(APIView):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        elif isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.messages)
        return super().handle_exception(exc)


def public_mocks():
    return (
        MockTest.objects.filter(status__in=PUBLIC_STATUSES)
        .select_related("exam_type", "exam_scheme")
        .order_by("starts_at", "pk")
    )


def public_offers():
    result = []
    for offer in (
        MockOffer.objects.filter(active=True)
        .prefetch_related("items__mock_test__exam_type", "items__mock_test__exam_scheme")
        .order_by("price_paise", "pk")
    ):
        offer.student_mocks = [item.mock_test for item in offer.items.all()]
        if offer.student_mocks and all(
            mock.status in PUBLIC_STATUSES for mock in offer.student_mocks
        ):
            result.append(offer)
    return result


class MockList(CommerceView):
    permission_classes = [AllowAny]

    @extend_schema(responses=MockSerializer(many=True))
    def get(self, request):
        return Response(MockSerializer(public_mocks(), many=True).data)


class MockDetail(CommerceView):
    permission_classes = [AllowAny]

    @extend_schema(responses=MockSerializer)
    def get(self, request, pk):
        return Response(MockSerializer(public_mocks().get(pk=pk)).data)


class OfferList(CommerceView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OfferSerializer(many=True))
    def get(self, request):
        return Response(OfferSerializer(public_offers(), many=True).data)


class OfferDetail(CommerceView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OfferSerializer)
    def get(self, request, pk):
        offer = next((o for o in public_offers() if o.pk == pk), None)
        if offer is None:
            raise NotFound()
        return Response(OfferSerializer(offer).data)


class CreateOrder(CommerceView):
    @extend_schema(request=CreateOrderSerializer, responses=OrderSerializer)
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_order(request.user, serializer.validated_data["offer_id"])
        return Response(OrderSerializer(order).data, status=200)


class OrderDetail(CommerceView):
    @extend_schema(responses=OrderSerializer)
    def get(self, request, pk):
        return Response(OrderSerializer(Order.objects.get(pk=pk, student=request.user)).data)


class VerifyPayment(CommerceView):
    @extend_schema(request=VerifySerializer, responses=OrderSerializer)
    def post(self, request):
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = verify_payment(
            request.user,
            data["order_id"],
            data["razorpay_order_id"],
            data["razorpay_payment_id"],
            data["razorpay_signature"],
        )
        return Response(OrderSerializer(order).data)


class PaymentWebhook(CommerceView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=WebhookPayloadSerializer, responses=AcknowledgedSerializer, auth=[])
    def post(self, request):
        process_webhook(
            request.body,
            request.headers.get("X-Razorpay-Signature", ""),
            request.headers.get("X-Razorpay-Event-Id", ""),
        )
        return Response({"received": True})


class AccessList(CommerceView):
    @extend_schema(responses=AccessSerializer(many=True))
    def get(self, request):
        grants = (
            MockAccessGrant.objects.filter(student=request.user)
            .select_related("mock_test__exam_type", "mock_test__exam_scheme")
            .order_by("-granted_at")
        )
        return Response(AccessSerializer(grants, many=True).data)


class MockAccess(CommerceView):
    @extend_schema(responses=MockAccessSerializer)
    def get(self, request, pk):
        mock = public_mocks().get(pk=pk)
        grants = MockAccessGrant.objects.filter(student=request.user, mock_test=mock)
        return Response(
            {
                "has_access": mock.status != "CANCELLED"
                and grants.filter(status="ACTIVE").exists(),
                "grants": AccessSerializer(grants, many=True).data,
            }
        )


urlpatterns = [
    path("mocks/", MockList.as_view()),
    path("mocks/<uuid:pk>/", MockDetail.as_view()),
    path("mocks/<uuid:pk>/access/", MockAccess.as_view()),
    path("offers/", OfferList.as_view()),
    path("offers/<uuid:pk>/", OfferDetail.as_view()),
    path("orders/", CreateOrder.as_view()),
    path("orders/<uuid:pk>/", OrderDetail.as_view()),
    path("payments/verify/", VerifyPayment.as_view()),
    path("payments/webhook/", PaymentWebhook.as_view()),
    path("access/", AccessList.as_view()),
]
