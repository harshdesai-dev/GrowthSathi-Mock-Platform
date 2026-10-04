from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import (
    AnswerKeyAuditEvent,
    MockPhase,
    MockTest,
    Question,
    QuestionType,
    _draft_mock_edit,
    _service_write,
)
from .validation import validate_answers, validate_paper, validate_scheme


def require_owner(actor: User) -> None:
    if (
        not actor
        or not actor.is_authenticated
        or not actor.is_active
        or not actor.is_staff
        or not actor.is_superuser
    ):
        raise PermissionDenied("Only the active platform owner may administer exams.")


@contextmanager
def service_write():
    token = _service_write.set(True)
    try:
        yield
    finally:
        _service_write.reset(token)


@contextmanager
def draft_mock_edit():
    """Permit an owner-authoring service to change DRAFT exam bindings only."""
    token = _draft_mock_edit.set(True)
    try:
        yield
    finally:
        _draft_mock_edit.reset(token)


@transaction.atomic
def create_draft_mock(**fields) -> MockTest:
    """Create a validated DRAFT mock and generate its versioned scheme phases."""
    mock = MockTest(status=MockTest.Status.DRAFT, **fields)
    mock.save()
    generate_phases(mock)
    return mock


@transaction.atomic
def update_draft_mock(mock_id: UUID, **changes) -> MockTest:
    """Edit an operationally untouched DRAFT and resync phases on scheme changes."""
    mock = MockTest.objects.select_for_update().get(pk=mock_id)
    if mock.status != MockTest.Status.DRAFT:
        raise ValidationError("Only DRAFT mocks can be edited.")

    exam_type = changes.get("exam_type", mock.exam_type)
    exam_scheme = changes.get("exam_scheme", mock.exam_scheme)
    bindings_changed = exam_type.pk != mock.exam_type_id or exam_scheme.pk != mock.exam_scheme_id
    if exam_scheme.exam_type_id != exam_type.pk:
        raise ValidationError({"exam_scheme": "Scheme must match the exam type."})

    if bindings_changed and mock.questions.exists():
        raise ValidationError(
            {
                "exam_scheme": (
                    "The exam type or scheme cannot change after questions have been added. "
                    "Create a new DRAFT mock to preserve the authored paper."
                )
            }
        )

    if bindings_changed:
        # Question writes also lock the mock row, so the existence check and phase
        # replacement are serialized with any concurrent authoring request.
        mock.phases.all().delete()

    for field, value in changes.items():
        setattr(mock, field, value)

    if bindings_changed:
        with draft_mock_edit():
            mock.save()
        generate_phases(mock)
    else:
        mock.save()
    return mock


@transaction.atomic
def generate_phases(mock: MockTest) -> None:
    mock = MockTest.objects.select_for_update().get(pk=mock.pk)
    if mock.status != MockTest.Status.DRAFT:
        raise ValidationError("Only draft mocks may generate phases.")
    validate_scheme(mock.exam_scheme).require_valid()
    for phase in mock.exam_scheme.phases.all():
        MockPhase.objects.get_or_create(
            mock_test=mock,
            order=phase.order,
            defaults={
                "scheme_phase": phase,
                **{
                    f: getattr(phase, f)
                    for f in ("name", "start_offset_minutes", "duration_minutes", "sequence_locked")
                },
            },
        )


@transaction.atomic
def verify_official_rules(mock_id: UUID, *, actor: User, source_notes: str) -> MockTest:
    require_owner(actor)
    if not source_notes.strip():
        raise ValidationError("Record the official source, edition/date and checks performed.")
    mock = MockTest.objects.select_for_update().get(pk=mock_id)
    if mock.status != MockTest.Status.DRAFT:
        raise ValidationError("Verify official rules while the mock is a draft.")
    validate_scheme(mock.exam_scheme).require_valid()
    mock.rules_verified_at = timezone.now()
    mock.rules_verified_by = actor
    mock.rules_source_notes = source_notes.strip()
    with service_write():
        mock.save()
    return mock


TRANSITIONS = {
    "DRAFT": {"REGISTRATION_OPEN", "SCHEDULED", "CANCELLED"},
    "REGISTRATION_OPEN": {"SCHEDULED", "CANCELLED"},
    "SCHEDULED": {"LIVE", "CANCELLED"},
    "LIVE": {"CLOSED"},
    "CLOSED": {"RESULTS_PUBLISHED"},
    "RESULTS_PUBLISHED": set(),
    "CANCELLED": set(),
}


@transaction.atomic
def transition_mock(mock_id: UUID, target: str, *, actor: User) -> MockTest:
    require_owner(actor)
    mock = MockTest.objects.select_for_update().get(pk=mock_id)
    if target not in TRANSITIONS[mock.status]:
        raise ValidationError(f"Illegal transition: {mock.status} -> {target}.")
    if target == MockTest.Status.RESULTS_PUBLISHED:
        if timezone.now() < mock.result_release_at:
            raise ValidationError("Earliest result-publication time has not arrived.")
        raise ValidationError(
            "Publication requires verified calculations; use the result operations page."
        )
    if target in {"REGISTRATION_OPEN", "SCHEDULED", "LIVE"}:
        validate_paper(mock).require_valid()
        if not mock.rules_verified_at or not mock.rules_source_notes:
            raise ValidationError("Revalidate the latest official rules for this mock first.")
    with service_write():
        if target == "LIVE":
            # The complete paper was validated under the mock lock above. Only this
            # private lifecycle path may bypass the public bulk-write prohibition.
            models.QuerySet.update(
                mock.questions.all(), status=Question.Status.LOCKED, updated_at=timezone.now()
            )
        mock.status = target
        mock.save()
    return mock


@transaction.atomic
def correct_answer_key(
    question_id: UUID,
    *,
    actor: User,
    reason: str,
    correct_option: str | None = None,
    numeric_answer: Decimal | None = None,
    numeric_tolerance: Decimal | None = None,
) -> Question:
    require_owner(actor)
    if not reason.strip():
        raise ValidationError("A correction reason is required.")
    question = Question.objects.select_related("mock_test").get(pk=question_id)
    mock = MockTest.objects.select_for_update().get(pk=question.mock_test_id)
    question.refresh_from_db()
    if mock.status != MockTest.Status.CLOSED:
        raise ValidationError(
            "Answer-key corrections are allowed only after close, before publication."
        )
    changes = []
    with service_write():
        if question.question_type == QuestionType.MCQ_SINGLE:
            if (
                correct_option not in {"A", "B", "C", "D"}
                or numeric_answer is not None
                or numeric_tolerance is not None
            ):
                raise ValidationError("Supply one MCQ label A-D only.")
            options = list(question.options.all())
            if {o.label for o in options} != set("ABCD"):
                raise ValidationError("Question must have four options.")
            old = ",".join(o.label for o in options if o.is_correct)
            for option in options:
                option.is_correct = option.label == correct_option
                option.save()
            if old != correct_option:
                changes.append(("correct_option", old, correct_option))
        else:
            if correct_option is not None or numeric_answer is None:
                raise ValidationError("Supply a numerical answer only.")
            for field, value in (
                ("correct_numeric_answer", numeric_answer),
                (
                    "numeric_tolerance",
                    numeric_tolerance
                    if numeric_tolerance is not None
                    else question.numeric_tolerance,
                ),
            ):
                value = Question._meta.get_field(field).clean(value, question)
                old = getattr(question, field)
                if old != value:
                    changes.append((field, str(old), str(value)))
                    setattr(question, field, value)
            question.save()
        errors = validate_answers(question, list(question.options.all()))
        if errors:
            raise ValidationError(errors)
        if not changes:
            raise ValidationError("The answer key is unchanged.")
        for field, old, new in changes:
            AnswerKeyAuditEvent.objects.create(
                question=question,
                changed_by=actor,
                field_changed=field,
                old_value=old,
                new_value=new,
                reason=reason.strip(),
            )
    # The result service uses the same mock-row lock: correction and publication
    # cannot race. Published keys first require explicit audited withdrawal.
    from apps.results.services import invalidate_drafts

    invalidate_drafts(mock.pk, "Answer key corrected; verify and calculate a new result batch.")
    return question
