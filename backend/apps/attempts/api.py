from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.commerce.api import StrictSerializer

from . import services
from .student_payload import StudentQuestionSerializer, student_paper


class EmptyInput(StrictSerializer):
    pass


class DecimalText(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Use decimal text, not a JSON number.")
        return super().to_internal_value(data)


class MutationInput(StrictSerializer):
    selected_option = serializers.UUIDField(allow_null=True)
    numeric_answer = DecimalText(allow_blank=True, max_length=32, trim_whitespace=False)
    marked_for_review = serializers.BooleanField()
    mutation_version = serializers.IntegerField(min_value=1, max_value=9007199254740991)


class ResponseSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_option = serializers.UUIDField(allow_null=True)
    numeric_answer = serializers.CharField(allow_blank=True)
    marked_for_review = serializers.BooleanField()
    mutation_version = serializers.IntegerField()


class PhaseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    order = serializers.IntegerField()


class StateSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField()
    mock_id = serializers.UUIDField()
    mock_title = serializers.CharField()
    status = serializers.CharField()
    server_time = serializers.DateTimeField()
    started_at = serializers.DateTimeField()
    mock_starts_at = serializers.DateTimeField()
    mock_ends_at = serializers.DateTimeField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    current_phase = PhaseSerializer(allow_null=True)
    phase_starts_at = serializers.DateTimeField(allow_null=True)
    phase_ends_at = serializers.DateTimeField(allow_null=True)
    can_submit = serializers.BooleanField()
    responses = ResponseSerializer(many=True)
    saved_response_count = serializers.IntegerField()
    answered_count = serializers.IntegerField()
    question_count = serializers.IntegerField()


class PaperSerializer(serializers.Serializer):
    state = StateSerializer()
    questions = StudentQuestionSerializer(many=True)


class SavedSerializer(serializers.Serializer):
    response = ResponseSerializer()
    acknowledgement = serializers.CharField()
    server_time = serializers.DateTimeField()


class InfoPhaseSerializer(serializers.Serializer):
    name = serializers.CharField()
    order = serializers.IntegerField()
    start_offset_minutes = serializers.IntegerField()
    duration_minutes = serializers.IntegerField()


class InfoSerializer(serializers.Serializer):
    mock_id = serializers.UUIDField()
    title = serializers.CharField()
    instructions_md = serializers.CharField()
    server_time = serializers.DateTimeField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    can_start = serializers.BooleanField()
    attempt_id = serializers.UUIDField(allow_null=True)
    attempt_status = serializers.CharField(allow_null=True)
    phases = InfoPhaseSerializer(many=True)


class ExamThrottle(SimpleRateThrottle):
    # Abuse guard, not a correctness lock. Process-local cache until deployment review.
    rate = "600/min"
    scope = "exam"

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class ExamView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ExamThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def empty(self, request):
        payload = EmptyInput(data=request.data)
        payload.is_valid(raise_exception=True)


class Start(ExamView):
    @extend_schema(request=EmptyInput, responses=StateSerializer)
    def post(self, request, mock_id):
        self.empty(request)
        return Response(services.start_attempt(request.user, mock_id))


class State(ExamView):
    @extend_schema(responses=StateSerializer)
    def get(self, request, attempt_id):
        return Response(services.attempt_state(request.user, attempt_id))


class Paper(ExamView):
    @extend_schema(responses=PaperSerializer)
    def get(self, request, attempt_id):
        return Response(student_paper(request.user, attempt_id))


class Heartbeat(ExamView):
    @extend_schema(request=EmptyInput, responses=StateSerializer)
    def post(self, request, attempt_id):
        self.empty(request)
        return Response(services.heartbeat(request.user, attempt_id))


class Save(ExamView):
    @extend_schema(request=MutationInput, responses=SavedSerializer)
    def put(self, request, attempt_id, question_id):
        serializer = MutationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            services.save_response(request.user, attempt_id, question_id, serializer.validated_data)
        )


class Submit(ExamView):
    @extend_schema(request=EmptyInput, responses=StateSerializer)
    def post(self, request, attempt_id):
        self.empty(request)
        return Response(services.submit_attempt(request.user, attempt_id))


class Info(ExamView):
    @extend_schema(responses=InfoSerializer)
    def get(self, request, mock_id):
        return Response(services.exam_info(request.user, mock_id))


urlpatterns = [
    path("mocks/<uuid:mock_id>/start/", Start.as_view()),
    path("mocks/<uuid:mock_id>/exam-info/", Info.as_view()),
    path("attempts/<uuid:attempt_id>/", State.as_view()),
    path("attempts/<uuid:attempt_id>/paper/", Paper.as_view()),
    path("attempts/<uuid:attempt_id>/heartbeat/", Heartbeat.as_view()),
    path("attempts/<uuid:attempt_id>/responses/<uuid:question_id>/", Save.as_view()),
    path("attempts/<uuid:attempt_id>/submit/", Submit.as_view()),
]
