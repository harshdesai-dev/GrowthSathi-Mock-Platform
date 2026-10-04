"""Owner-only endpoints for existing mock validation and rules services."""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttles import ReadThrottle
from apps.exams.models import MockTest
from apps.exams.services import verify_official_rules
from apps.exams.validation import validate_paper

from .permissions import IsActiveOwner


class OwnerPaperMarksSummarySerializer(serializers.Serializer):
    actual = serializers.DecimalField(max_digits=12, decimal_places=2)
    expected = serializers.DecimalField(max_digits=12, decimal_places=2)


class OwnerPaperValidationSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    status = serializers.ChoiceField(choices=("VALID", "INVALID"))
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    actual_question_count = serializers.IntegerField(min_value=0)
    expected_question_count = serializers.IntegerField(min_value=0)
    marks_summary = OwnerPaperMarksSummarySerializer()


class OwnerRulesVerificationInputSerializer(serializers.Serializer):
    source_notes = serializers.CharField(allow_blank=True, trim_whitespace=False)
    confirmed = serializers.BooleanField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {
                    field: "This field cannot be set through the owner verification API."
                    for field in sorted(unexpected)
                }
            )
        if not attrs["confirmed"]:
            raise serializers.ValidationError(
                {"confirmed": "Explicit confirmation is required to record verification."}
            )
        return attrs


class OwnerRulesVerificationResultSerializer(serializers.Serializer):
    rules_verified_at = serializers.DateTimeField()
    rules_source_notes = serializers.CharField()


def _owner_mock(mock_id):
    return get_object_or_404(
        MockTest.objects.select_related("exam_scheme", "exam_type"),
        pk=mock_id,
    )


class OwnerMockPaperValidationView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(request=None, responses={200: OwnerPaperValidationSerializer})
    def post(self, request, mock_id):
        mock = _owner_mock(mock_id)
        result = validate_paper(mock)
        summary = mock.questions.aggregate(
            actual_question_count=Count("pk"),
            actual_marks=Sum("positive_marks"),
        )
        response_data = {
            "valid": result.valid,
            "status": result.status,
            "errors": result.errors,
            "warnings": [],
            "actual_question_count": summary["actual_question_count"],
            "expected_question_count": mock.exam_scheme.total_question_count,
            "marks_summary": {
                "actual": summary["actual_marks"] or Decimal("0.00"),
                "expected": Decimal(mock.exam_scheme.maximum_marks),
            },
        }
        return Response(OwnerPaperValidationSerializer(response_data).data)


class OwnerMockRulesVerificationView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(
        request=OwnerRulesVerificationInputSerializer,
        responses={200: OwnerRulesVerificationResultSerializer},
    )
    def post(self, request, mock_id):
        _owner_mock(mock_id)
        serializer = OwnerRulesVerificationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            mock = verify_official_rules(
                mock_id,
                actor=request.user,
                source_notes=serializer.validated_data["source_notes"],
            )
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError({"source_notes": exc.messages}) from exc
        return Response(
            OwnerRulesVerificationResultSerializer(
                {
                    "rules_verified_at": mock.rules_verified_at,
                    "rules_source_notes": mock.rules_source_notes,
                }
            ).data
        )
