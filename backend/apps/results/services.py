"""Owner-only atomic result batches. All result/correction operations lock the mock first."""

import hashlib
import json
from contextlib import contextmanager
from functools import wraps

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone

from apps.attempts.models import Attempt, StudentResponse
from apps.exams.models import AnswerKeyAuditEvent, MockTest, QuestionOption, SchemeRule
from apps.exams.services import require_owner
from apps.exams.services import service_write as exam_writing
from apps.exams.validation import validate_paper

from .models import Result, ResultCalculationEntry, ResultCalculationRun, service_write
from .scoring import METRICS, participant_reason, rank_scores, score_attempt


@contextmanager
def writing():
    token = service_write.set(True)
    try:
        yield
    finally:
        service_write.reset(token)


def operation(function):
    @wraps(function)
    def wrapped(*args, actor, **kwargs):
        require_owner(actor)
        with transaction.atomic(), writing():
            result = function(*args, actor=actor, **kwargs)
        # A rejected operation may intentionally commit reconciliation/invalidation.
        if isinstance(result, ValidationError):
            raise result
        return result

    return wrapped


def fingerprint(value):
    encoded = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def locked_mock(mock_id):
    return (
        MockTest.objects.select_related("exam_scheme", "exam_type")
        .select_for_update(of=("self",))
        .get(pk=mock_id)
    )


def require_closed(mock):
    if mock.status != "CLOSED" or timezone.now() < mock.ends_at:
        raise ValidationError("Results require a CLOSED mock whose global exam window has ended.")


def paper_snapshot(mock):
    """Private allowlisted reproducibility snapshot, NEVER a live/student serializer."""
    validate_paper(mock, persisted=False).require_valid()
    phases = list(
        mock.phases.values(
            "id",
            "scheme_phase_id",
            "name",
            "order",
            "start_offset_minutes",
            "duration_minutes",
            "sequence_locked",
        )
    )
    rules = list(
        SchemeRule.objects.filter(phase__scheme_id=mock.exam_scheme_id)
        .order_by("phase_id", "subject", "question_type")
        .values(
            "phase_id",
            "subject",
            "question_type",
            "question_count",
            "positive_marks",
            "negative_marks",
            "unanswered_marks",
        )
    )
    rule_map = {(str(r["phase_id"]), r["subject"], r["question_type"]): r for r in rules}
    phase_map = {p["id"]: str(p["scheme_phase_id"]) for p in phases}
    options = {}
    for option in (
        QuestionOption.objects.filter(question__mock_test=mock)
        .order_by("order")
        .values("id", "question_id", "label", "option_text_md", "option_image_url", "is_correct")
    ):
        options.setdefault(option.pop("question_id"), []).append(option)
    questions = list(
        mock.questions.values(
            "id",
            "phase_id",
            "subject",
            "question_number",
            "question_type",
            "question_text_md",
            "question_image_url",
            "positive_marks",
            "negative_marks",
            "correct_numeric_answer",
            "numeric_tolerance",
            "explanation_md",
        )
    )
    for question in questions:
        question["options"] = options.get(question["id"], [])
        question["correct_option"] = next(
            (o["id"] for o in question["options"] if o["is_correct"]), None
        )
        question["unanswered_marks"] = rule_map[
            (phase_map[question["phase_id"]], question["subject"], question["question_type"])
        ]["unanswered_marks"]
    scheme = mock.exam_scheme
    snapshot = {
        "mock_id": mock.pk,
        "mock_title": mock.title,
        "starts_at": mock.starts_at,
        "ends_at": mock.ends_at,
        "result_release_at": mock.result_release_at,
        "exam": {"id": mock.exam_type_id, "code": mock.exam_type.code, "name": mock.exam_type.name},
        "scheme": {
            "id": scheme.pk,
            "version": scheme.version,
            "total_question_count": scheme.total_question_count,
            "maximum_marks": scheme.maximum_marks,
            "total_duration_minutes": scheme.total_duration_minutes,
        },
        "phases": phases,
        "rules": rules,
        "questions": questions,
        "answer_key_audit_ids": list(
            AnswerKeyAuditEvent.objects.filter(question__mock_test=mock)
            .order_by("id")
            .values_list("id", flat=True)
        ),
    }
    return json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))


def reconcile_and_inputs(mock):
    """Caller holds mock lock and requires closed/end. Lock attempts before reading responses.

    Terminal attempts cannot be edited by the engine. A stale IN_PROGRESS attempt
    is reconciled in one validated bulk write, avoiding 500 per-student UPDATEs.
    """
    require_closed(mock)
    attempts = list(Attempt.objects.select_for_update().filter(mock_test=mock).order_by("id"))
    expired = [attempt.pk for attempt in attempts if attempt.status == "IN_PROGRESS"]
    if expired:
        models.QuerySet.update(
            Attempt.objects.filter(pk__in=expired, status="IN_PROGRESS"),
            status="AUTO_SUBMITTED",
            submitted_at=mock.ends_at,
            updated_at=timezone.now(),
        )
        for attempt in attempts:
            if attempt.status == "IN_PROGRESS":
                attempt.status, attempt.submitted_at = "AUTO_SUBMITTED", mock.ends_at
    responses = {str(attempt.pk): {} for attempt in attempts}
    for aid, qid, option, numeric, version in (
        StudentResponse.objects.filter(attempt__mock_test=mock)
        .order_by("attempt_id", "question_id")
        .values_list(
            "attempt_id", "question_id", "selected_option_id", "numeric_answer", "mutation_version"
        )
    ):
        responses[str(aid)][str(qid)] = {
            "selected_option": str(option) if option else None,
            "numeric_answer": numeric,
            "mutation_version": version,
        }
    eligible, excluded = [], []
    for attempt in attempts:
        reason = participant_reason(attempt.status, bool(responses[str(attempt.pk)]))
        if reason:
            excluded.append(
                {"attempt_id": str(attempt.pk), "status": attempt.status, "reason": reason}
            )
        else:
            eligible.append(attempt)
    digest = fingerprint(
        {
            "attempts": [
                {"id": str(a.pk), "status": a.status, "submitted_at": a.submitted_at}
                for a in attempts
            ],
            "responses": responses,
        }
    )
    return eligible, excluded, responses, digest


def invalidate_drafts(mock_id, reason):
    """Called under the shared mock lock, including from audited key correction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Draft invalidation requires the mock transaction.")
    models.QuerySet.update(
        ResultCalculationRun.objects.filter(
            mock_test_id=mock_id, status__in=["VERIFIED", "CALCULATING", "COMPLETE"]
        ),
        status="INVALIDATED",
        errors=reason,
        updated_at=timezone.now(),
    )


@operation
def reconcile_for_results(mock_id, *, actor):
    mock = locked_mock(mock_id)
    eligible, excluded, _, _ = reconcile_and_inputs(mock)
    return {"participant_count": len(eligible), "excluded_attempts": excluded}


@operation
def verify_answer_key(mock_id, *, actor, notes):
    if not notes.strip():
        raise ValidationError("Record what was checked against the verified answer key.")
    mock = locked_mock(mock_id)
    require_closed(mock)
    _, _, _, digest = reconcile_and_inputs(mock)
    snapshot = paper_snapshot(mock)
    revision = fingerprint(snapshot)
    current = ResultCalculationRun.objects.filter(
        mock_test=mock, status__in=["VERIFIED", "COMPLETE"]
    ).first()
    if (
        current
        and current.source_revision == revision
        and (current.status == "VERIFIED" or current.input_digest == digest)
    ):
        return current
    invalidate_drafts(mock.pk, "Superseded by a new explicit key verification.")
    now = timezone.now()
    return ResultCalculationRun.objects.create(
        mock_test=mock,
        status="VERIFIED",
        started_by=actor,
        started_at=now,
        key_verified_at=now,
        source_revision=revision,
        paper_snapshot=snapshot,
        notes=notes.strip(),
    )


def metric_values(entry):
    return {
        name: format(getattr(entry, name), ".2f")
        if name in {"score", "percentile"}
        else getattr(entry, name)
        for name in METRICS
    }


def output_digest(entries):
    return fingerprint(
        [
            {
                "attempt_id": str(entry.attempt_id),
                "responses": entry.response_snapshot,
                **metric_values(entry),
            }
            for entry in sorted(entries, key=lambda item: str(item.attempt_id))
        ]
    )


def lock_run(run_id):
    identity = ResultCalculationRun.objects.only("mock_test_id").get(pk=run_id)
    mock = locked_mock(identity.mock_test_id)
    return mock, ResultCalculationRun.objects.get(pk=run_id)


@operation
def calculate_results(run_id, *, actor):
    mock, run = lock_run(run_id)
    require_closed(mock)
    if run.status not in {"VERIFIED", "COMPLETE"}:
        raise ValidationError("Select a current verified calculation run.")
    eligible, excluded, responses, digest = reconcile_and_inputs(mock)
    if (
        fingerprint(paper_snapshot(mock)) != run.source_revision
        or fingerprint(run.paper_snapshot) != run.source_revision
    ):
        invalidate_drafts(mock.pk, "Paper/key changed; verify the answer key again.")
        return ValidationError("Paper/key changed; verify the answer key again.")
    if run.status == "COMPLETE":
        if digest != run.input_digest:
            invalidate_drafts(mock.pk, "Attempt inputs changed; a new calculation is required.")
            return ValidationError("Attempt inputs changed; verify and recalculate.")
        return run
    run.status = "CALCULATING"
    run.save(update_fields=["status", "updated_at"])
    try:
        rows = [
            (attempt, score_attempt(run.paper_snapshot["questions"], responses[str(attempt.pk)]))
            for attempt in eligible
        ]
    except ValueError as exc:
        run.status, run.errors = "FAILED", str(exc)
        run.save(update_fields=["status", "errors", "updated_at"])
        return ValidationError(str(exc))
    rankings = rank_scores([values["score"] for _, values in rows])
    entries = [
        ResultCalculationEntry(
            calculation_run=run,
            attempt=attempt,
            response_snapshot=responses[str(attempt.pk)],
            **values,
            **rankings[values["score"]],
        )
        for attempt, values in rows
    ]
    # Validated rows, one transaction; deliberately bypass public bulk-write guards.
    models.QuerySet(model=ResultCalculationEntry).bulk_create(entries, batch_size=200)
    run.status, run.completed_at = "COMPLETE", timezone.now()
    run.participant_count, run.excluded_attempts = len(entries), excluded
    run.input_digest, run.output_digest = digest, output_digest(entries)
    run.save()
    return run


@operation
def publish_results(run_id, *, actor):
    mock, run = lock_run(run_id)
    if mock.status == "RESULTS_PUBLISHED" and run.status == "PUBLISHED":
        return run  # Same generation/timestamp; a duplicate cannot publish a draft.
    require_closed(mock)
    if timezone.now() < mock.result_release_at:
        raise ValidationError("Earliest result-publication time has not arrived.")
    if run.status != "COMPLETE" or not run.completed_at:
        raise ValidationError("A complete verified calculation is required before publication.")
    eligible, _, _, digest = reconcile_and_inputs(mock)
    if (
        fingerprint(paper_snapshot(mock)) != run.source_revision
        or fingerprint(run.paper_snapshot) != run.source_revision
        or digest != run.input_digest
    ):
        invalidate_drafts(mock.pk, "Calculation sources changed; verify and recalculate.")
        return ValidationError("Calculation sources changed; verify and recalculate.")
    entries = list(run.entries.all())
    if (
        len(entries) != run.participant_count
        or {e.attempt_id for e in entries} != {a.pk for a in eligible}
        or output_digest(entries) != run.output_digest
    ):
        invalidate_drafts(mock.pk, "Incomplete or inconsistent calculation batch.")
        return ValidationError("Incomplete or inconsistent calculation batch; recalculate.")
    now = timezone.now()
    rows = [
        Result(
            attempt_id=entry.attempt_id,
            calculation_run=run,
            entry=entry,
            published_at=now,
            **{name: getattr(entry, name) for name in METRICS},
        )
        for entry in entries
    ]
    models.QuerySet(model=Result).bulk_create(
        rows,
        batch_size=200,
        update_conflicts=True,
        unique_fields=["attempt"],
        update_fields=[*METRICS, "calculation_run", "entry", "published_at", "updated_at"],
    )
    run.status, run.published_at, run.published_by = "PUBLISHED", now, actor
    run.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    with exam_writing():
        mock.status = "RESULTS_PUBLISHED"
        mock.save()
    return run


@operation
def withdraw_results(run_id, *, actor, reason):
    if not reason.strip():
        raise ValidationError("An explicit withdrawal/correction reason is required.")
    mock, run = lock_run(run_id)
    if run.status == "WITHDRAWN" and mock.status == "CLOSED":
        return run
    if mock.status != "RESULTS_PUBLISHED" or run.status != "PUBLISHED":
        raise ValidationError("Only the currently published batch may be withdrawn.")
    run.status, run.withdrawn_at, run.withdrawn_by = "WITHDRAWN", timezone.now(), actor
    run.withdrawal_reason = reason.strip()
    run.save(
        update_fields=["status", "withdrawn_at", "withdrawn_by", "withdrawal_reason", "updated_at"]
    )
    with exam_writing():
        mock.status = "CLOSED"
        mock.save()
    return run
