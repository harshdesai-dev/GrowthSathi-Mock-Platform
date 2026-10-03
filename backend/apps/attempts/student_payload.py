"""Student-only allowlist. Never reuse authoring serializers or model __dict__."""

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import serializers

from apps.exams.models import Question, QuestionOption

from .services import ExamConflict, current_phase, load_attempt, state_data, writable


class StudentOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    option_text_md = serializers.CharField()
    option_image_url = serializers.CharField()


class StudentQuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    question_number = serializers.IntegerField()
    phase_id = serializers.UUIDField()
    subject = serializers.CharField()
    question_type = serializers.CharField()
    question_text_md = serializers.CharField()
    question_image_url = serializers.CharField()
    options = StudentOptionSerializer(many=True)


def student_paper(student, attempt_id):
    attempt = load_attempt(student, attempt_id)
    now = timezone.now()
    denied = writable(attempt, now)
    if denied:
        raise denied
    phase = current_phase(attempt.mock_test, now)
    questions = (
        Question.objects.filter(mock_test=attempt.mock_test, phase=phase)
        .only(
            "id",
            "question_number",
            "phase_id",
            "subject",
            "question_type",
            "question_text_md",
            "question_image_url",
        )
        .prefetch_related(
            Prefetch(
                "options",
                queryset=QuestionOption.objects.only(
                    "id", "question_id", "label", "option_text_md", "option_image_url", "order"
                ),
            )
        )
    )
    data = StudentQuestionSerializer(questions, many=True).data
    # A slow query may cross a boundary; never deliver a now-closed/future phase.
    after = timezone.now()
    next_phase = current_phase(attempt.mock_test, after)
    if not next_phase or next_phase.pk != phase.pk:
        load_attempt(student, attempt_id)
        raise ExamConflict("Phase changed; refresh the authoritative state.", "phase_closed")
    return {"state": state_data(attempt, after), "questions": data}
