"""Exam authoring models. Mutations serialize on the owning scheme/mock row.

Bulk writes are deliberately unavailable: they bypass validation and lifecycle guards.
Services use a private context for transitions and audited corrections, never HTTP input.
"""

import uuid
from contextvars import ContextVar
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

_service_write = ContextVar("exam_service_write", default=False)


class Subject(models.TextChoices):
    PHYSICS = "PHYSICS", "Physics"
    CHEMISTRY = "CHEMISTRY", "Chemistry"
    MATHEMATICS = "MATHEMATICS", "Mathematics"


class QuestionType(models.TextChoices):
    MCQ_SINGLE = "MCQ_SINGLE", "Single correct MCQ"
    NUMERICAL = "NUMERICAL", "Numerical"


class GuardedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Bulk updates bypass exam validation; use model/domain services.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Use validated authoring/import services.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Use validated authoring/import services.")

    def delete(self):
        with transaction.atomic():
            count = 0
            for obj in self.order_by("pk"):
                obj.delete()
                count += 1
            return count, {self.model._meta.label: count}


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.guard()
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            self.guard()
            return super().delete(*args, **kwargs)

    def guard(self):
        """Lock/check the aggregate before any model write; overridden below."""


class ExamType(Entity):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def clean(self):
        if not self._state.adding:
            old = ExamType.objects.get(pk=self.pk)
            if old.code != self.code:
                raise ValidationError({"code": "Exam codes are stable identifiers."})


class ExamScheme(Entity):
    exam_type = models.ForeignKey(ExamType, on_delete=models.PROTECT, related_name="schemes")
    version = models.CharField(max_length=50)
    name = models.CharField(max_length=160)
    effective_from = models.DateField()
    source_reference = models.TextField(
        help_text="Source/version notes; seeds require revalidation."
    )
    total_duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    maximum_marks = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    total_question_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    active = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["exam_type", "version"], name="scheme_exam_version"),
            models.CheckConstraint(
                condition=models.Q(total_duration_minutes__gt=0), name="scheme_duration_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(maximum_marks__gt=0), name="scheme_marks_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(total_question_count__gt=0), name="scheme_count_positive"
            ),
        ]

    def __str__(self):
        return f"{self.exam_type.code} / {self.version}"

    def guard(self):
        if not self._state.adding:
            old = ExamScheme.objects.select_for_update().get(pk=self.pk)
            if old.locked or old.mocks.exists():
                raise ValidationError(
                    "Referenced/locked schemes are immutable. Create a new version."
                )


def lock_scheme(scheme_id):
    scheme = ExamScheme.objects.select_for_update().get(pk=scheme_id)
    if scheme.locked or scheme.mocks.exists():
        raise ValidationError("Referenced/locked scheme rules are immutable. Create a new version.")


class SchemePhase(Entity):
    scheme = models.ForeignKey(ExamScheme, on_delete=models.PROTECT, related_name="phases")
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    start_offset_minutes = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    sequence_locked = models.BooleanField(default=False, help_text="Lock this phase after its end.")

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["scheme", "order"], name="scheme_phase_order"),
            models.CheckConstraint(
                condition=models.Q(order__gt=0), name="scheme_phase_order_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gt=0), name="scheme_phase_duration_positive"
            ),
        ]

    def __str__(self):
        return f"{self.scheme}: {self.order}. {self.name}"

    def guard(self):
        if (
            not self._state.adding
            and SchemePhase.objects.get(pk=self.pk).scheme_id != self.scheme_id
        ):
            raise ValidationError("Cannot move a scheme phase; create a new one.")
        lock_scheme(self.scheme_id)


class SchemeRule(Entity):
    phase = models.ForeignKey(SchemePhase, on_delete=models.PROTECT, related_name="rules")
    subject = models.CharField(max_length=20, choices=Subject.choices)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    question_count = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    positive_marks = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    negative_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Penalty magnitude: 1 means minus one.",
    )
    unanswered_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phase", "subject", "question_type"], name="scheme_rule_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(question_count__gt=0), name="rule_count_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(positive_marks__gt=0, negative_marks__gte=0, unanswered_marks=0),
                name="rule_marks_valid",
            ),
        ]

    def __str__(self):
        return f"{self.subject} / {self.question_type} ({self.question_count})"

    def guard(self):
        if not self._state.adding and SchemeRule.objects.get(pk=self.pk).phase_id != self.phase_id:
            raise ValidationError("Cannot move a rule; create a new one.")
        lock_scheme(self.phase.scheme_id)


class MockTest(Entity):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        REGISTRATION_OPEN = "REGISTRATION_OPEN"
        SCHEDULED = "SCHEDULED"
        LIVE = "LIVE"
        CLOSED = "CLOSED"
        RESULTS_PUBLISHED = "RESULTS_PUBLISHED"
        CANCELLED = "CANCELLED"

    exam_type = models.ForeignKey(ExamType, on_delete=models.PROTECT)
    exam_scheme = models.ForeignKey(ExamScheme, on_delete=models.PROTECT, related_name="mocks")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    result_release_at = models.DateTimeField()
    price_paise = models.PositiveIntegerField(default=2900)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    instructions_md = models.TextField(blank=True)
    rules_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    rules_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="verified_mock_rules",
    )
    rules_source_notes = models.TextField(blank=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(starts_at__lt=models.F("ends_at")), name="mock_schedule_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(result_release_at__gte=models.F("ends_at")),
                name="mock_release_valid",
            ),
        ]

    def __str__(self):
        return self.title

    def guard(self):
        if self._state.adding:
            ExamScheme.objects.select_for_update().get(pk=self.exam_scheme_id)
            if self.rules_verified_at or self.rules_verified_by_id or self.rules_source_notes:
                raise ValidationError(
                    "Use the official-rule verification action after creating the draft."
                )
        else:
            old = MockTest.objects.select_for_update().get(pk=self.pk)
            if old.exam_scheme_id != self.exam_scheme_id or old.exam_type_id != self.exam_type_id:
                raise ValidationError("Mock scheme/exam bindings are immutable; create a new mock.")
            if old.status != self.Status.DRAFT and not _service_write.get():
                raise ValidationError("Operational mocks are read-only; use lifecycle services.")
            if old.status != self.status and not _service_write.get():
                raise ValidationError("Use the transition service to change status.")
            if not _service_write.get() and any(
                getattr(old, f) != getattr(self, f)
                for f in ("rules_verified_at", "rules_verified_by_id", "rules_source_notes")
            ):
                raise ValidationError("Use the official-rule verification action.")

    def clean(self):
        if self._state.adding and self.status != self.Status.DRAFT:
            raise ValidationError({"status": "New mocks must be DRAFT."})
        if (
            self.exam_scheme_id
            and self.exam_type_id
            and self.exam_scheme.exam_type_id != self.exam_type_id
        ):
            raise ValidationError({"exam_scheme": "Scheme must match the exam type."})
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "End must follow start."})
        if self.result_release_at and self.ends_at and self.result_release_at < self.ends_at:
            raise ValidationError({"result_release_at": "Release cannot precede the exam end."})


def lock_mock(mock_id):
    mock = MockTest.objects.select_for_update().get(pk=mock_id)
    if mock.status != MockTest.Status.DRAFT and not _service_write.get():
        raise ValidationError(
            "Paper content is editable only in DRAFT. Use audited corrections after close."
        )
    return mock


class MockPhase(Entity):
    mock_test = models.ForeignKey(MockTest, on_delete=models.PROTECT, related_name="phases")
    scheme_phase = models.ForeignKey(SchemePhase, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    start_offset_minutes = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    sequence_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["mock_test", "order"], name="mock_phase_order")
        ]

    def __str__(self):
        return f"{self.mock_test}: {self.name}"

    def guard(self):
        if (
            not self._state.adding
            and MockPhase.objects.get(pk=self.pk).mock_test_id != self.mock_test_id
        ):
            raise ValidationError("Cannot move phases between mocks.")
        lock_mock(self.mock_test_id)

    def clean(self):
        if self.scheme_phase_id and self.mock_test_id:
            if self.scheme_phase.scheme_id != self.mock_test.exam_scheme_id:
                raise ValidationError("Phase must belong to the mock's scheme.")
            for field in (
                "name",
                "order",
                "start_offset_minutes",
                "duration_minutes",
                "sequence_locked",
            ):
                if getattr(self, field) != getattr(self.scheme_phase, field):
                    raise ValidationError({field: "Must match the versioned scheme phase."})


class Question(Entity):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        READY = "READY"
        LOCKED = "LOCKED"

    mock_test = models.ForeignKey(MockTest, on_delete=models.PROTECT, related_name="questions")
    phase = models.ForeignKey(MockPhase, on_delete=models.PROTECT, related_name="questions")
    subject = models.CharField(max_length=20, choices=Subject.choices)
    question_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    question_text_md = models.TextField()
    question_image_url = models.URLField(blank=True)
    positive_marks = models.DecimalField(max_digits=6, decimal_places=2)
    negative_marks = models.DecimalField(max_digits=6, decimal_places=2)
    correct_numeric_answer = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )
    numeric_tolerance = models.DecimalField(
        max_digits=20, decimal_places=8, default=0, validators=[MinValueValidator(0)]
    )
    explanation_md = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["question_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["mock_test", "question_number"], name="mock_question_number"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    question_number__gt=0,
                    positive_marks__gt=0,
                    negative_marks__gte=0,
                    numeric_tolerance__gte=0,
                ),
                name="question_values_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(question_type="NUMERICAL", correct_numeric_answer__isnull=False)
                    | models.Q(
                        question_type="MCQ_SINGLE",
                        correct_numeric_answer__isnull=True,
                        numeric_tolerance=0,
                    )
                ),
                name="question_answer_shape",
            ),
        ]

    def __str__(self):
        return f"{self.mock_test}: Q{self.question_number}"

    def guard(self):
        if not self._state.adding:
            old = Question.objects.get(pk=self.pk)
            if old.mock_test_id != self.mock_test_id:
                raise ValidationError("Cannot move questions between mocks.")
            if old.status == self.Status.LOCKED and not _service_write.get():
                raise ValidationError("Question is locked.")
        if self.status == self.Status.LOCKED and not _service_write.get():
            raise ValidationError("Only the lifecycle service locks questions.")
        lock_mock(self.mock_test_id)

    def clean(self):
        if self.phase_id and self.mock_test_id:
            if self.phase.mock_test_id != self.mock_test_id:
                raise ValidationError({"phase": "Phase belongs to a different mock."})
            rule = self.phase.scheme_phase.rules.filter(
                subject=self.subject, question_type=self.question_type
            ).first()
            if not rule:
                raise ValidationError("Subject/question type is not allowed in this phase.")
            if (
                self.positive_marks != rule.positive_marks
                or self.negative_marks != rule.negative_marks
            ):
                raise ValidationError(
                    "Marks must match the scheme rule (negative marks are a penalty magnitude)."
                )
        if self.question_type == QuestionType.NUMERICAL:
            if self.correct_numeric_answer is None:
                raise ValidationError({"correct_numeric_answer": "Numerical answer is required."})
            if not self._state.adding and self.options.exists():
                raise ValidationError("Numerical questions cannot have options.")
        elif self.correct_numeric_answer is not None or self.numeric_tolerance != 0:
            raise ValidationError("MCQs cannot have numerical answer/tolerance fields.")
        if self.status != self.Status.DRAFT and not self.explanation_md.strip():
            raise ValidationError(
                {"explanation_md": "Ready/locked questions require an explanation."}
            )


class QuestionOption(Entity):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=1, choices=[(v, v) for v in "ABCD"])
    option_text_md = models.TextField(blank=True)
    option_image_url = models.URLField(blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["question", "label"], name="option_label_unique"),
            models.UniqueConstraint(fields=["question", "order"], name="option_order_unique"),
        ]

    def __str__(self):
        return self.label

    def guard(self):
        if (
            not self._state.adding
            and QuestionOption.objects.get(pk=self.pk).question_id != self.question_id
        ):
            raise ValidationError("Cannot move options between questions.")
        lock_mock(self.question.mock_test_id)
        if self.question.status == Question.Status.LOCKED and not _service_write.get():
            raise ValidationError("Question is locked.")

    def clean(self):
        if self.question_id and self.question.question_type != QuestionType.MCQ_SINGLE:
            raise ValidationError("Only MCQ questions have options.")
        if not self.option_text_md.strip() and not self.option_image_url:
            raise ValidationError("Option text or image is required.")


class AnswerKeyAuditEvent(Entity):
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="answer_key_audit"
    )
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    field_changed = models.CharField(max_length=60)
    old_value = models.TextField()
    new_value = models.TextField()
    reason = models.TextField()

    def __str__(self):
        return f"{self.question_id}: {self.field_changed}"

    def guard(self):
        if not self._state.adding or not _service_write.get():
            raise ValidationError(
                "Audit events are append-only and created by the correction service."
            )

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")
