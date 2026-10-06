from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.commerce.models import MockOffer, MockOfferItem
from apps.commerce.services import set_offer_active, validate_contents
from apps.exams.models import MockTest

from .permissions import IsActiveOwner


class OwnerOfferMockSerializer(serializers.ModelSerializer):
    exam_code = serializers.CharField(source="exam_type.code", read_only=True)

    class Meta:
        model = MockTest
        fields = ("id", "title", "slug", "status", "starts_at", "ends_at", "exam_code")


class OwnerOfferSerializer(serializers.ModelSerializer):
    mocks = serializers.SerializerMethodField()
    purchase_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MockOffer
        fields = (
            "id",
            "name",
            "slug",
            "offer_type",
            "price_paise",
            "active",
            "sales_start_at",
            "sales_end_at",
            "mocks",
            "purchase_count",
        )

    def get_mocks(self, obj):
        mocks = [item.mock_test for item in obj.items.all()]
        return OwnerOfferMockSerializer(mocks, many=True).data


class OwnerOfferWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    slug = serializers.SlugField(max_length=50)
    offer_type = serializers.ChoiceField(choices=MockOffer.Type.choices)
    price_paise = serializers.IntegerField(min_value=1)
    sales_start_at = serializers.DateTimeField()
    sales_end_at = serializers.DateTimeField()
    mock_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        max_length=2,
    )

    def validate(self, attrs):
        if attrs["sales_end_at"] <= attrs["sales_start_at"]:
            raise serializers.ValidationError(
                {"sales_end_at": "Sales end must be after sales start."}
            )
        if len(set(attrs["mock_ids"])) != len(attrs["mock_ids"]):
            raise serializers.ValidationError({"mock_ids": "Choose each mock only once."})

        mocks = list(
            MockTest.objects.select_related("exam_type", "exam_scheme")
            .filter(pk__in=attrs["mock_ids"])
            .order_by("pk")
        )
        if len(mocks) != len(attrs["mock_ids"]):
            raise serializers.ValidationError({"mock_ids": "One or more mocks do not exist."})

        candidate = MockOffer(
            offer_type=attrs["offer_type"],
            name=attrs["name"],
            slug=attrs["slug"],
            price_paise=attrs["price_paise"],
            sales_start_at=attrs["sales_start_at"],
            sales_end_at=attrs["sales_end_at"],
        )
        try:
            validate_contents(candidate, mocks)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"mock_ids": exc.messages}) from exc

        attrs["mocks"] = mocks
        return attrs


def _offer_queryset():
    return (
        MockOffer.objects.prefetch_related("items__mock_test__exam_type")
        .annotate(
            purchase_count=Count(
                "orders",
                filter=Q(orders__status="PAID"),
                distinct=True,
            )
        )
        .order_by("-created_at")
    )


def _raise_domain(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise ValidationError(exc.message_dict) from exc
    raise ValidationError({"non_field_errors": exc.messages}) from exc


@transaction.atomic
def _create_offer(validated):
    mocks = validated.pop("mocks")
    validated.pop("mock_ids")
    try:
        offer = MockOffer.objects.create(**validated)
        for mock in mocks:
            MockOfferItem.objects.create(offer=offer, mock_test=mock)
    except DjangoValidationError as exc:
        _raise_domain(exc)
    return offer


@transaction.atomic
def _update_offer(offer, validated):
    offer = MockOffer.objects.select_for_update().get(pk=offer.pk)
    if offer.active:
        raise ValidationError({"active": "Deactivate the offer before editing."})

    mocks = validated.pop("mocks")
    validated.pop("mock_ids")
    for field, value in validated.items():
        setattr(offer, field, value)

    try:
        offer.save()
        offer.items.all().delete()
        for mock in mocks:
            MockOfferItem.objects.create(offer=offer, mock_test=mock)
    except DjangoValidationError as exc:
        _raise_domain(exc)
    return offer


class OwnerOffersView(APIView):
    permission_classes = [IsActiveOwner]

    @extend_schema(responses={200: OwnerOfferSerializer(many=True)})
    def get(self, request):
        return Response({"results": OwnerOfferSerializer(_offer_queryset(), many=True).data})

    @extend_schema(request=OwnerOfferWriteSerializer, responses={201: OwnerOfferSerializer})
    def post(self, request):
        serializer = OwnerOfferWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offer = _create_offer(dict(serializer.validated_data))
        detail = _offer_queryset().get(pk=offer.pk)
        return Response(OwnerOfferSerializer(detail).data, status=status.HTTP_201_CREATED)


class OwnerOfferDetailView(APIView):
    permission_classes = [IsActiveOwner]

    @extend_schema(responses={200: OwnerOfferSerializer})
    def get(self, request, offer_id):
        return Response(OwnerOfferSerializer(get_object_or_404(_offer_queryset(), pk=offer_id)).data)

    @extend_schema(request=OwnerOfferWriteSerializer, responses={200: OwnerOfferSerializer})
    def patch(self, request, offer_id):
        offer = get_object_or_404(MockOffer, pk=offer_id)
        serializer = OwnerOfferWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _update_offer(offer, dict(serializer.validated_data))
        detail = _offer_queryset().get(pk=updated.pk)
        return Response(OwnerOfferSerializer(detail).data)


class OwnerOfferActivationSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class OwnerOfferActivationView(APIView):
    permission_classes = [IsActiveOwner]

    @extend_schema(request=OwnerOfferActivationSerializer, responses={200: OwnerOfferSerializer})
    def post(self, request, offer_id):
        serializer = OwnerOfferActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_offer_active(
                offer_id,
                serializer.validated_data["active"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            _raise_domain(exc)
        detail = get_object_or_404(_offer_queryset(), pk=offer_id)
        return Response(OwnerOfferSerializer(detail).data)
