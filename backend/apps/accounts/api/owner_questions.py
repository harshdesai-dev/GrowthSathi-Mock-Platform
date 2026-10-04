"""Owner-only read and import endpoints for mock questions."""

import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttles import ReadThrottle
from apps.exams.imports import commit_import, preview_import, template_bytes
from apps.exams.models import MockTest, Question, QuestionOption

from .permissions import IsActiveOwner


class DraftMockRequired(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "draft_mock_required"
    default_detail = "Questions can only be imported into a DRAFT mock."


class OwnerQuestionSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    question_number = serializers.IntegerField()
    phase_order = serializers.IntegerField(source="phase.order")
    phase_name = serializers.CharField(source="phase.name")
    subject = serializers.CharField()
    question_type = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField(source="get_status_display")
    question_preview = serializers.SerializerMethodField()
    has_image = serializers.SerializerMethodField()

    def get_question_preview(self, obj):
        return " ".join(obj.question_text_md.split())[:240]

    def get_has_image(self, obj):
        return bool(obj.question_image_url)


class OwnerQuestionOptionSerializer(serializers.Serializer):
    label = serializers.CharField()
    text = serializers.CharField(source="option_text_md")
    has_image = serializers.SerializerMethodField()

    def get_has_image(self, obj):
        return bool(obj.option_image_url)


class OwnerQuestionDetailSerializer(OwnerQuestionSummarySerializer):
    question_text_md = serializers.CharField()
    options = OwnerQuestionOptionSerializer(many=True)


class OwnerQuestionGroupSerializer(serializers.Serializer):
    phase_order = serializers.IntegerField()
    phase_name = serializers.CharField()
    subject = serializers.CharField()
    question_type = serializers.CharField()
    count = serializers.IntegerField()


class OwnerQuestionListResponseSerializer(serializers.Serializer):
    mock = serializers.DictField()
    grouped_counts = OwnerQuestionGroupSerializer(many=True)
    results = OwnerQuestionSummarySerializer(many=True)


class ImportPreviewRowSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    question_number = serializers.CharField(allow_blank=True)
    phase = serializers.CharField(allow_blank=True)
    subject = serializers.CharField(allow_blank=True)
    question_type = serializers.CharField(allow_blank=True)
    question_preview = serializers.CharField(allow_blank=True)


class ImportPreviewErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField(allow_null=True)
    message = serializers.CharField()


class OwnerQuestionImportPreviewSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    token = serializers.CharField(allow_blank=True)
    rows = ImportPreviewRowSerializer(many=True)
    errors = ImportPreviewErrorSerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ImportCommitSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True, max_length=3 * 1024 * 1024)


def _preview_payload(preview):
    rows = []
    for row in preview.rows:
        values = row.get("values", {})
        rows.append(
            {
                "row": row["row"],
                "question_number": values.get("question_number", ""),
                "phase": values.get("phase", ""),
                "subject": values.get("subject", ""),
                "question_type": values.get("question_type", ""),
                "question_preview": " ".join(values.get("question_text_md", "").split())[:240]
                or row.get("parse_error", ""),
            }
        )
    errors = []
    for message in preview.errors:
        match = re.match(r"^Row (\d+):\s*(.*)$", message)
        errors.append(
            {
                "row": int(match.group(1)) if match else None,
                "message": match.group(2) if match else message,
            }
        )
    return {
        "valid": preview.valid,
        "token": preview.token,
        "rows": rows,
        "errors": errors,
        "warnings": preview.warnings,
    }


def _get_mock(mock_id, *, with_count=False):
    queryset = MockTest.objects.select_related("exam_scheme")
    if with_count:
        queryset = queryset.annotate(question_count=Count("questions", distinct=True))
    return get_object_or_404(queryset, pk=mock_id)


class OwnerMockQuestionsView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(responses={200: OwnerQuestionListResponseSerializer})
    def get(self, request, mock_id):
        mock = _get_mock(mock_id, with_count=True)
        queryset = (
            Question.objects.filter(mock_test=mock)
            .select_related("phase")
            .only(
                "id",
                "question_number",
                "phase_id",
                "phase__id",
                "phase__order",
                "phase__name",
                "subject",
                "question_type",
                "status",
                "question_text_md",
                "question_image_url",
            )
            .order_by("question_number", "pk")
        )
        grouped_counts = list(
            Question.objects.filter(mock_test=mock)
            .values("phase__order", "phase__name", "subject", "question_type")
            .annotate(count=Count("pk"))
            .order_by("phase__order", "subject", "question_type")
        )
        response_data = {
            "mock": {
                "id": str(mock.pk),
                "title": mock.title,
                "status": mock.status,
                "question_count": mock.question_count,
                "expected_question_count": mock.exam_scheme.total_question_count,
                "read_only": mock.status != MockTest.Status.DRAFT,
            },
            "grouped_counts": [
                {
                    "phase_order": item["phase__order"],
                    "phase_name": item["phase__name"],
                    "subject": item["subject"],
                    "question_type": item["question_type"],
                    "count": item["count"],
                }
                for item in grouped_counts
            ],
            "results": OwnerQuestionSummarySerializer(queryset, many=True).data,
        }
        return Response(response_data)


class OwnerMockQuestionDetailView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(responses={200: OwnerQuestionDetailSerializer})
    def get(self, request, mock_id, question_id):
        mock = _get_mock(mock_id)
        question = get_object_or_404(
            Question.objects.filter(mock_test=mock)
            .select_related("phase")
            .only(
                "id",
                "question_number",
                "phase_id",
                "phase__id",
                "phase__order",
                "phase__name",
                "subject",
                "question_type",
                "status",
                "question_text_md",
                "question_image_url",
            )
            .prefetch_related(
                Prefetch(
                    "options",
                    queryset=QuestionOption.objects.only(
                        "id",
                        "question_id",
                        "label",
                        "option_text_md",
                        "option_image_url",
                        "order",
                    ),
                )
            ),
            pk=question_id,
        )
        return Response(OwnerQuestionDetailSerializer(question).data)


class OwnerMockQuestionImportPreviewView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=ImportUploadSerializer, responses={200: OwnerQuestionImportPreviewSerializer}
    )
    def post(self, request, mock_id):
        mock = _get_mock(mock_id)
        if mock.status != MockTest.Status.DRAFT:
            raise DraftMockRequired()
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = preview_import(mock.pk, serializer.validated_data["file"], actor=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(OwnerQuestionImportPreviewSerializer(_preview_payload(preview)).data)


class OwnerMockQuestionImportCommitView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]
    parser_classes = [JSONParser]

    @extend_schema(request=ImportCommitSerializer, responses={200: serializers.DictField()})
    def post(self, request, mock_id):
        mock = _get_mock(mock_id)
        if mock.status != MockTest.Status.DRAFT:
            raise DraftMockRequired()
        serializer = ImportCommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            imported_count = commit_import(
                mock.pk, serializer.validated_data["token"], actor=request.user
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"import": exc.messages}) from exc
        return Response({"imported_count": imported_count})


class OwnerQuestionTemplateView(APIView):
    throttle_classes = [ReadThrottle]
    permission_classes = [IsActiveOwner]

    @extend_schema(responses={200: bytes})
    def get(self, request, file_format):
        if file_format not in {"csv", "xlsx"}:
            from django.http import Http404

            raise Http404
        content_type = (
            "text/csv"
            if file_format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = HttpResponse(template_bytes(file_format), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="question-import.{file_format}"'
        return response
