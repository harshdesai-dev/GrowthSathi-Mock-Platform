"""Clock/phase authority and atomic operations, independent of request handlers/workers."""

import logging
import re
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from apps.accounts.models import User
from apps.commerce.models import MockAccessGrant
from apps.exams.models import MockTest, Question, QuestionOption
from apps.exams.services import service_write as exam_writing
from apps.exams.validation import validate_paper

from .models import Attempt, StudentResponse, service_write

logger = logging.getLogger(__name__)


class ExamConflict(APIException):
    status_code = 409
    default_code = "exam_conflict"

    def __init__(self, message, code="exam_conflict"):
        super().__init__(message, code=code)


class ExamDenied(ExamConflict):
    status_code = 403


@contextmanager
def writing():
    token = service_write.set(True)
    try:
        yield
    finally:
        service_write.reset(token)


def committed(operation):
    """Reconciliation must COMMIT even when the requested late write is rejected."""

    @wraps(operation)
    def wrapped(*args, **kwargs):
        with transaction.atomic(), writing():
            result = operation(*args, **kwargs)
        if isinstance(result, APIException):
            raise result
        return result

    return wrapped


def has_access(student_id, mock_id):
    return MockAccessGrant.objects.filter(
        student_id=student_id,
        mock_test_id=mock_id,
        status="ACTIVE",
        source_order_item__order__status="PAID",
    ).exists()


def current_phase(mock, now):
    for phase in mock.phases.all():
        start = mock.starts_at + timedelta(minutes=phase.start_offset_minutes)
        end = min(start + timedelta(minutes=phase.duration_minutes), mock.ends_at)
        if start <= now < end:
            return phase
    return None


def reconcile_locked(attempt, now):
    if attempt.status != "IN_PROGRESS":
        return
    mock = attempt.mock_test
    if mock.status == "CANCELLED":
        attempt.status, attempt.submitted_at = "INVALID", now
    elif now >= mock.ends_at:
        attempt.status, attempt.submitted_at = "AUTO_SUBMITTED", mock.ends_at
    else:
        return
    attempt.save(update_fields=["status", "submitted_at", "updated_at"])
    logger.info("attempt_lifecycle attempt=%s status=%s", attempt.pk, attempt.status)


def own_attempt(student, attempt_id, *, lock=False):
    query = Attempt.objects.select_related("mock_test").prefetch_related("mock_test__phases")
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        return query.get(pk=attempt_id, student=student)
    except Attempt.DoesNotExist as exc:
        raise NotFound() from exc


def response_data(response):
    return {
        "question_id": str(response.question_id),
        "selected_option": str(response.selected_option_id)
        if response.selected_option_id
        else None,
        "numeric_answer": response.numeric_answer,
        "marked_for_review": response.marked_for_review,
        "mutation_version": response.mutation_version,
    }


def state_data(attempt, now, *, newly_created=False):
    mock = attempt.mock_test
    phase = current_phase(mock, now) if attempt.status == "IN_PROGRESS" else None
    phase_start = mock.starts_at + timedelta(minutes=phase.start_offset_minutes) if phase else None
    phase_end = (
        min(phase_start + timedelta(minutes=phase.duration_minutes), mock.ends_at)
        if phase
        else None
    )
    responses = attempt.responses.all()
    visible = responses.filter(question__phase=phase) if phase else responses.none()
    return {
        "attempt_id": str(attempt.pk),
        "mock_id": str(mock.pk),
        "mock_title": mock.title,
        "status": attempt.status,
        "server_time": now,
        "started_at": attempt.started_at,
        "mock_starts_at": mock.starts_at,
        "mock_ends_at": mock.ends_at,
        "submitted_at": attempt.submitted_at,
        "current_phase": {"id": str(phase.pk), "name": phase.name, "order": phase.order}
        if phase
        else None,
        "phase_starts_at": phase_start,
        "phase_ends_at": phase_end,
        "can_submit": bool(
            phase
            and phase.order == max(p.order for p in mock.phases.all())
            and mock.status == "LIVE"
        ),
        "responses": [] if newly_created else [response_data(response) for response in visible],
        "saved_response_count": 0 if newly_created else responses.count(),
        "answered_count": 0
        if newly_created
        else responses.exclude(selected_option__isnull=True, numeric_answer="").count(),
        "question_count": mock.exam_scheme.total_question_count,
    }


def load_attempt(student, attempt_id):
    attempt = own_attempt(student, attempt_id)
    now = timezone.now()
    if attempt.status == "IN_PROGRESS" and (
        now >= attempt.mock_test.ends_at or attempt.mock_test.status == "CANCELLED"
    ):
        with transaction.atomic(), writing():
            attempt = own_attempt(student, attempt_id, lock=True)
            reconcile_locked(attempt, timezone.now())
    return attempt


def attempt_state(student, attempt_id):
    attempt = load_attempt(student, attempt_id)
    return state_data(attempt, timezone.now())


@committed
def start_attempt(student, mock_id):
    # Same student lock used by payment/refund services: entitlement checks cannot race them.
    student = (
        User.objects.select_related("profile").select_for_update(of=("self",)).get(pk=student.pk)
    )
    try:
        mock = (
            MockTest.objects.select_related("exam_scheme")
            .prefetch_related("phases")
            .get(pk=mock_id)
        )
    except MockTest.DoesNotExist as exc:
        raise NotFound() from exc
    existing = Attempt.objects.filter(student=student, mock_test=mock).first()
    if existing:
        existing = own_attempt(student, existing.pk, lock=True)
        reconcile_locked(existing, timezone.now())
        if existing.status != "IN_PROGRESS":
            return state_data(existing, timezone.now())  # Terminal, never reopened.
    if (
        not hasattr(student, "profile")
        or not student.profile.onboarding_completed
        or not has_access(student.pk, mock.pk)
    ):
        logger.info("attempt_access_denied student=%s mock=%s", student.pk, mock.pk)
        return ExamDenied(
            "Active paid access and completed onboarding are required.", "access_denied"
        )
    now = timezone.now()
    if now < mock.starts_at:
        return ExamConflict("This mock has not started.", "not_started")
    if now >= mock.ends_at:
        return ExamConflict("The global exam window has ended.", "exam_closed")
    if mock.status not in {"SCHEDULED", "LIVE"}:
        return ExamDenied("This mock is not ready or is no longer available.", "mock_unavailable")
    if not existing:
        # Papers/schedules are immutable in SCHEDULED/LIVE. Validate each new start,
        # outside a shared mock-row lock so distinct students are not serialized.
        if not mock.rules_verified_at or not validate_paper(mock, persisted=True).valid:
            return ExamDenied("This mock is not valid for an exam.", "mock_invalid")
    if mock.status == "SCHEDULED":
        locked_mock = MockTest.objects.select_for_update().get(pk=mock.pk)
        if locked_mock.status not in {"SCHEDULED", "LIVE"}:
            return ExamDenied("Mock is unavailable.", "mock_unavailable")
        if locked_mock.status == "SCHEDULED":
            with exam_writing():
                models.QuerySet.update(
                    locked_mock.questions.all(), status="LOCKED", updated_at=timezone.now()
                )
                locked_mock.status = "LIVE"
                locked_mock.save()
        mock.status = "LIVE"
    # Validation or a lock wait must not buy additional time.
    now = timezone.now()
    if now >= mock.ends_at:
        if existing:
            reconcile_locked(existing, now)
        return ExamConflict("The global exam window has ended.", "exam_closed")
    if existing:
        existing.mock_test = mock
        return state_data(existing, now)
    attempt = Attempt.objects.create(
        student=student, mock_test=mock, started_at=now, last_heartbeat_at=now
    )
    logger.info("attempt_started attempt=%s mock=%s", attempt.pk, mock.pk)
    # The new UUID is not visible outside this uncommitted transaction: it cannot
    # have responses yet. Resumes still read authoritative saved responses.
    return state_data(attempt, now, newly_created=True)


def writable(attempt, now):
    if attempt.status != "IN_PROGRESS" or now >= attempt.mock_test.ends_at:
        return ExamConflict(
            "This attempt is closed. Only server-saved answers are retained.", "exam_closed"
        )
    if attempt.mock_test.status != "LIVE" or not has_access(
        attempt.student_id, attempt.mock_test_id
    ):
        return ExamDenied("Exam access is unavailable. Contact the owner.", "access_denied")
    if not current_phase(attempt.mock_test, now):
        return ExamConflict("No exam phase is currently writable.", "phase_closed")
    return None


def canonical_numeric(value):
    # Decimal text, not a JS/Python float. Matches the existing 20,8 answer-key storage.
    if (
        not isinstance(value, str)
        or len(value) > 32
        or (
            value
            and not re.fullmatch(
                r"[+-]?(?:\d{1,12}(?:\.\d{0,8})?|\.\d{1,8})", value, flags=re.ASCII
            )
        )
    ):
        raise ValueError("Enter a finite decimal with at most 12 integer and 8 decimal digits.")
    if not value:
        return ""
    decimal = Decimal(value)
    if decimal == 0:
        return "0"
    return (
        format(decimal, "f").rstrip("0").rstrip(".")
        if "." in format(decimal, "f")
        else format(decimal, "f")
    )


@committed
def save_response(student, attempt_id, question_id, data):
    attempt = own_attempt(student, attempt_id, lock=True)
    now = timezone.now()  # AFTER row lock, never the request arrival/client timestamp.
    reconcile_locked(attempt, now)
    denied = writable(attempt, now)
    if denied:
        return denied
    try:
        question = Question.objects.only("id", "mock_test_id", "phase_id", "question_type").get(
            pk=question_id, mock_test_id=attempt.mock_test_id
        )
    except Question.DoesNotExist:
        return ExamConflict("Question does not belong to this attempt.", "invalid_response")
    if question.phase_id != current_phase(attempt.mock_test, now).pk:
        return ExamConflict("This question's phase is not writable.", "phase_closed")
    option, numeric = data["selected_option"], data["numeric_answer"]
    if question.question_type == "MCQ_SINGLE":
        if numeric or (
            option and not QuestionOption.objects.filter(pk=option, question=question).exists()
        ):
            return ExamConflict("Select an option belonging to this question.", "invalid_response")
    elif option:
        return ExamConflict("Numerical questions accept decimal text only.", "invalid_response")
    try:
        numeric = canonical_numeric(numeric)
    except ValueError as exc:
        return ExamConflict(str(exc), "invalid_response")
    version = data["mutation_version"]
    response = StudentResponse.objects.filter(attempt=attempt, question=question).first()
    values = {
        "selected_option_id": option,
        "numeric_answer": numeric,
        "marked_for_review": data["marked_for_review"],
    }
    if response and version <= response.mutation_version:
        same = version == response.mutation_version and all(
            getattr(response, key) == value for key, value in values.items()
        )
        if not same:
            logger.info("response_version_rejected attempt=%s question=%s", attempt.pk, question.pk)
            return ExamConflict(
                "A newer or conflicting answer is already saved. "
                "Reload its server state before editing.",
                "stale_mutation",
            )
        return {
            "response": response_data(response),
            "acknowledgement": "duplicate",
            "server_time": now,
        }
    if response is None:
        response = StudentResponse(attempt=attempt, question=question, first_visited_at=now)
    for key, value in values.items():
        setattr(response, key, value)
    response.mutation_version = version
    # Re-check after any query/lock delay immediately before persistence.
    accepted_at = timezone.now()
    reconcile_locked(attempt, accepted_at)
    accepted_phase = current_phase(attempt.mock_test, accepted_at)
    if (
        attempt.status != "IN_PROGRESS"
        or not accepted_phase
        or accepted_phase.pk != question.phase_id
    ):
        return ExamConflict("The response arrived after its phase deadline.", "phase_closed")
    response.save()
    return {
        "response": response_data(response),
        "acknowledgement": "saved",
        "server_time": accepted_at,
    }


@committed
def submit_attempt(student, attempt_id):
    attempt = own_attempt(student, attempt_id, lock=True)
    now = timezone.now()
    reconcile_locked(attempt, now)
    if attempt.status == "IN_PROGRESS":
        denied = writable(attempt, now)
        if denied:
            return denied
        phase = current_phase(attempt.mock_test, now)
        if phase.order != max(p.order for p in attempt.mock_test.phases.all()):
            return ExamConflict(
                "Final submission is available only in the final phase. "
                "Mathematics cannot unlock early.",
                "not_final_phase",
            )
        attempt.status, attempt.submitted_at = "SUBMITTED", now
        attempt.save(update_fields=["status", "submitted_at", "updated_at"])
        logger.info("attempt_submitted attempt=%s", attempt.pk)
    return state_data(attempt, now)


def heartbeat(student, attempt_id):
    attempt = load_attempt(student, attempt_id)
    now = timezone.now()
    if attempt.status == "IN_PROGRESS" and (
        not attempt.last_heartbeat_at or now - attempt.last_heartbeat_at >= timedelta(seconds=30)
    ):
        with transaction.atomic(), writing():
            attempt = own_attempt(student, attempt_id, lock=True)
            now = timezone.now()
            reconcile_locked(attempt, now)
            if attempt.status == "IN_PROGRESS" and (
                not attempt.last_heartbeat_at
                or now - attempt.last_heartbeat_at >= timedelta(seconds=30)
            ):
                attempt.last_heartbeat_at = now
                attempt.save(update_fields=["last_heartbeat_at", "updated_at"])
    return state_data(attempt, now)


def exam_info(student, mock_id):
    try:
        mock = MockTest.objects.prefetch_related("phases").get(pk=mock_id)
    except MockTest.DoesNotExist as exc:
        raise NotFound() from exc
    if mock.status == "DRAFT" or not has_access(student.pk, mock.pk):
        raise ExamDenied("Active paid access is required.", "access_denied")
    existing = Attempt.objects.filter(student=student, mock_test=mock).first()
    if existing:
        existing = load_attempt(student, existing.pk)
    now = timezone.now()
    return {
        "mock_id": str(mock.pk),
        "title": mock.title,
        "instructions_md": mock.instructions_md,
        "server_time": now,
        "starts_at": mock.starts_at,
        "ends_at": mock.ends_at,
        "can_start": mock.status in {"SCHEDULED", "LIVE"} and mock.starts_at <= now < mock.ends_at,
        "attempt_id": str(existing.pk) if existing else None,
        "attempt_status": existing.status if existing else None,
        "phases": [
            {
                "name": phase.name,
                "order": phase.order,
                "start_offset_minutes": phase.start_offset_minutes,
                "duration_minutes": phase.duration_minutes,
            }
            for phase in mock.phases.all()
        ],
    }


def reconcile_expired(*, batch_size=200):
    """Keyset scan, short row transactions; safe for a future worker to invoke."""
    count, after = 0, None
    while True:
        query = Attempt.objects.filter(
            models.Q(mock_test__ends_at__lte=timezone.now())
            | models.Q(mock_test__status="CANCELLED"),
            status="IN_PROGRESS",
        ).order_by("pk")
        if after:
            query = query.filter(pk__gt=after)
        ids = list(query.values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        for identity in ids:
            with transaction.atomic(), writing():
                attempt = (
                    Attempt.objects.select_for_update(of=("self",))
                    .select_related("mock_test")
                    .get(pk=identity)
                )
                before = attempt.status
                reconcile_locked(attempt, timezone.now())
                count += before == "IN_PROGRESS" and attempt.status != before
        after = ids[-1]
    return count
