"""Published-generation reads only; never serialize private calculation models wholesale."""

from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response

from apps.attempts.api import ExamView
from apps.attempts.models import Attempt
from apps.exams.models import MockTest

from .models import Result, ResultCalculationRun
from .scoring import METRICS, participant_reason, score_question


class Unavailable(APIException):
    status_code = 409
    default_code = "result_unavailable"
    default_detail = "Results are not published yet. Please check again after Admin publishes them."


def published_results():
    return Result.objects.filter(
        calculation_run__status="PUBLISHED", attempt__mock_test__status="RESULTS_PUBLISHED"
    ).select_related("calculation_run", "entry", "attempt__mock_test", "attempt__student__profile")


def private_result(user, mock_id):
    # One SQL statement chooses a coherent immutable generation at READ COMMITTED.
    result = (
        published_results().filter(attempt__student=user, attempt__mock_test_id=mock_id).first()
    )
    if result:
        return result
    mock = get_object_or_404(MockTest, pk=mock_id)
    attempt = Attempt.objects.filter(student=user, mock_test=mock).first()
    if not attempt:
        raise NotFound("No attempt belongs to this student for this mock.")
    if mock.status != "RESULTS_PUBLISHED":
        raise Unavailable()
    reason = participant_reason(attempt.status, attempt.responses.exists())
    raise Unavailable(f"This attempt is not ranked: {reason or 'no published result'}.")


def student_name(student):
    try:
        return student.profile.full_name.strip() or student.get_full_name() or "Student"
    except ObjectDoesNotExist:
        return student.get_full_name() or "Student"


def masked_name(student):
    parts = student_name(student).split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else parts[0]


def summary(result):
    paper = result.calculation_run.paper_snapshot
    return {
        "mock_id": paper["mock_id"],
        "mock_title": paper["mock_title"],
        "exam": paper["exam"]["name"],
        "starts_at": paper["starts_at"],
        "maximum_score": paper["scheme"]["maximum_marks"],
        **{name: getattr(result, name) for name in METRICS},
    }


class SummarySerializer(serializers.Serializer):
    mock_id = serializers.UUIDField()
    mock_title = serializers.CharField()
    exam = serializers.CharField()
    starts_at = serializers.DateTimeField()
    maximum_score = serializers.DecimalField(max_digits=18, decimal_places=2)
    score = serializers.DecimalField(max_digits=18, decimal_places=2)
    rank = serializers.IntegerField()
    percentile = serializers.DecimalField(max_digits=5, decimal_places=2)
    correct_count = serializers.IntegerField()
    incorrect_count = serializers.IntegerField()
    attempted_count = serializers.IntegerField()
    unattempted_count = serializers.IntegerField()


class ReportSerializer(SummarySerializer):
    student_name = serializers.CharField()
    previous_score = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    score_difference = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)


class Report(ExamView):
    @extend_schema(responses=ReportSerializer)
    def get(self, request, mock_id):
        result = private_result(request.user, mock_id)
        mock = result.attempt.mock_test
        previous = (
            published_results()
            .filter(
                attempt__student=request.user,
                attempt__mock_test__exam_type_id=mock.exam_type_id,
                attempt__mock_test__starts_at__lt=mock.starts_at,
            )
            .order_by("-attempt__mock_test__starts_at", "-published_at", "id")
            .first()
        )
        data = {
            **summary(result),
            "student_name": student_name(request.user),
            "previous_score": previous.score if previous else None,
            "score_difference": result.score - previous.score if previous else None,
        }
        return Response(ReportSerializer(data).data)


class History(ExamView):
    @extend_schema(responses=SummarySerializer(many=True))
    def get(self, request):
        results = (
            published_results()
            .filter(attempt__student=request.user)
            .order_by("-attempt__mock_test__starts_at", "id")
        )
        return Response(SummarySerializer([summary(result) for result in results], many=True).data)


class LeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    name = serializers.CharField()
    score = serializers.DecimalField(max_digits=18, decimal_places=2)
    percentile = serializers.DecimalField(max_digits=5, decimal_places=2)


class LeaderboardSerializer(serializers.Serializer):
    mock_title = serializers.CharField()
    rows = LeaderboardRowSerializer(many=True)


class Leaderboard(ExamView):
    @extend_schema(responses=LeaderboardSerializer)
    def get(self, request, mock_id):
        run = ResultCalculationRun.objects.filter(
            mock_test_id=mock_id, mock_test__status="RESULTS_PUBLISHED", status="PUBLISHED"
        ).first()
        if not run:
            get_object_or_404(MockTest, pk=mock_id)
            raise Unavailable()
        entries = run.entries.select_related("attempt__student__profile").order_by("rank", "id")
        data = {
            "mock_title": run.paper_snapshot["mock_title"],
            "rows": [
                {
                    "rank": entry.rank,
                    "name": masked_name(entry.attempt.student),
                    "score": entry.score,
                    "percentile": entry.percentile,
                }
                for entry in entries
            ],
        }
        return Response(LeaderboardSerializer(data).data)


class ReviewOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    option_text_md = serializers.CharField()
    option_image_url = serializers.CharField()


class ReviewQuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    question_number = serializers.IntegerField()
    question_type = serializers.CharField()
    question_text_md = serializers.CharField()
    question_image_url = serializers.CharField()
    options = ReviewOptionSerializer(many=True)
    selected_option = serializers.UUIDField(allow_null=True)
    numeric_answer = serializers.CharField()
    correct_option = serializers.UUIDField(allow_null=True)
    correct_numeric_answer = serializers.CharField(allow_null=True)
    numeric_tolerance = serializers.CharField()
    outcome = serializers.CharField()
    marks = serializers.DecimalField(max_digits=18, decimal_places=2)
    explanation_md = serializers.CharField()


class ReviewSerializer(serializers.Serializer):
    mock_title = serializers.CharField()
    questions = ReviewQuestionSerializer(many=True)


class Review(ExamView):
    @extend_schema(responses=ReviewSerializer)
    def get(self, request, mock_id):
        result = private_result(request.user, mock_id)
        paper, responses = result.calculation_run.paper_snapshot, result.entry.response_snapshot
        questions = []
        for question in paper["questions"]:
            response = responses.get(question["id"], {})
            questions.append(
                {
                    **question,
                    "selected_option": response.get("selected_option"),
                    "numeric_answer": response.get("numeric_answer", ""),
                    **score_question(question, response),
                }
            )
        return Response(
            ReviewSerializer({"mock_title": paper["mock_title"], "questions": questions}).data
        )


urlpatterns = [
    path("mocks/<uuid:mock_id>/result/", Report.as_view()),
    path("mocks/<uuid:mock_id>/leaderboard/", Leaderboard.as_view()),
    path("mocks/<uuid:mock_id>/review/", Review.as_view()),
    path("results/history/", History.as_view()),
]
