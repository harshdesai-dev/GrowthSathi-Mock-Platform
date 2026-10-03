"""Protected exam records. Only validated, transactional attempt services write them."""

import uuid
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.exams.models import GuardedQuerySet

service_write = ContextVar("attempt_service_write", default=False)


class ExamRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not service_write.get():
            raise ValidationError("Exam records are writable only through attempt services.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attempt history cannot be deleted through application code.")


class Attempt(ExamRecord):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS"
        SUBMITTED = "SUBMITTED"
        AUTO_SUBMITTED = "AUTO_SUBMITTED"
        INVALID = "INVALID"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attempts"
    )
    mock_test = models.ForeignKey(
        "exams.MockTest", on_delete=models.PROTECT, related_name="attempts"
    )
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.IN_PROGRESS)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "mock_test"], name="one_attempt_per_mock"),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["IN_PROGRESS", "SUBMITTED", "AUTO_SUBMITTED", "INVALID"]
                ),
                name="attempt_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="IN_PROGRESS", submitted_at__isnull=True)
                    | models.Q(
                        status__in=["SUBMITTED", "AUTO_SUBMITTED", "INVALID"],
                        submitted_at__isnull=False,
                    )
                ),
                name="attempt_terminal_timestamp",
            ),
        ]
        indexes = [models.Index(fields=["status", "mock_test"])]

    def __str__(self):
        return f"{self.id}: {self.status}"


class StudentResponse(ExamRecord):
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT, related_name="responses")
    question = models.ForeignKey(
        "exams.Question", on_delete=models.PROTECT, related_name="student_responses"
    )
    selected_option = models.ForeignKey(
        "exams.QuestionOption", on_delete=models.PROTECT, null=True, blank=True
    )
    numeric_answer = models.CharField(max_length=32, blank=True, default="")
    marked_for_review = models.BooleanField(default=False)
    first_visited_at = models.DateTimeField()
    mutation_version = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"], name="one_response_per_question"
            ),
            models.CheckConstraint(
                condition=models.Q(mutation_version__gte=1, mutation_version__lte=9007199254740991),
                name="response_version_safe_integer",
            ),
            models.CheckConstraint(
                condition=models.Q(selected_option__isnull=True) | models.Q(numeric_answer=""),
                name="response_single_answer_kind",
            ),
        ]

    def __str__(self):
        return f"{self.attempt_id}: {self.question_id} v{self.mutation_version}"
