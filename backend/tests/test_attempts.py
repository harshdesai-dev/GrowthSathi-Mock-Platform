import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection, connections, models, transaction
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attempts.models import Attempt, StudentResponse
from apps.attempts.services import (
    ExamConflict,
    ExamDenied,
    attempt_state,
    canonical_numeric,
    exam_info,
    heartbeat,
    reconcile_expired,
    save_response,
    start_attempt,
    submit_attempt,
)
from apps.attempts.student_payload import student_paper
from tests.attempt_helpers import exam_fixture, mutation, paid_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def exam():
    mock = exam_fixture()
    return mock, paid_student(mock)


def started(mock, student):
    return start_attempt(student, mock.pk)["attempt_id"]


def test_access_start_late_resume_and_no_restart(exam):
    mock, student = exam
    with pytest.raises(ExamConflict, match="not started"):
        started(mock, student)
    stranger = User.objects.create_user(email="no-access@test.invalid", google_sub="no-access")
    with patch("django.utils.timezone.now", return_value=mock.starts_at + timedelta(minutes=45)):
        with pytest.raises(ExamDenied):
            started(mock, stranger)
        identity = started(mock, student)
        state = attempt_state(student, identity)
        assert state["mock_ends_at"] == mock.ends_at
        assert state["started_at"] == mock.starts_at + timedelta(minutes=45)
        assert started(mock, student) == identity
        assert len(student_paper(student, identity)["questions"]) == 75
        assert submit_attempt(student, identity)["status"] == "SUBMITTED"
        assert started(mock, student) == identity
        assert submit_attempt(student, identity)["status"] == "SUBMITTED"
    assert Attempt.objects.count() == 1


@pytest.mark.parametrize(
    "reason", ["unpaid", "revoked", "onboarding", "draft", "invalid", "unverified", "cancelled"]
)
def test_start_denial(exam, reason):
    mock, student = exam
    if reason == "unpaid":
        models.QuerySet.update(student.orders.all(), status="PENDING")
    elif reason == "revoked":
        models.QuerySet.update(student.mock_access.all(), status="REVOKED")
    elif reason == "onboarding":
        student.profile.onboarding_completed = False
        student.profile.save()
    elif reason in {"draft", "cancelled"}:
        models.QuerySet.update(type(mock).objects.filter(pk=mock.pk), status=reason.upper())
    elif reason == "invalid":
        models.QuerySet.update(mock.questions.all(), question_text_md="")
    else:
        models.QuerySet.update(type(mock).objects.filter(pk=mock.pk), rules_verified_at=None)
    with patch("django.utils.timezone.now", return_value=mock.starts_at), pytest.raises(ExamDenied):
        started(mock, student)
    assert not Attempt.objects.exists()


def test_versions_clear_review_and_canonical_numerical(exam):
    mock, student = exam
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student)
        question = mock.questions.filter(question_type="MCQ_SINGLE").first()
        option = question.options.first().pk
        first = mutation(question, 2, option=option, review=True)
        assert save_response(student, identity, question.pk, first)["acknowledgement"] == "saved"
        assert (
            save_response(student, identity, question.pk, first)["acknowledgement"] == "duplicate"
        )
        for version in [1, 2]:
            with pytest.raises(ExamConflict, match="newer or conflicting"):
                save_response(student, identity, question.pk, mutation(question, version))
        save_response(student, identity, question.pk, mutation(question, 3))
        saved = StudentResponse.objects.get(question=question)
        assert saved.selected_option_id is None and not saved.marked_for_review
        assert saved.mutation_version == 3
        numeric = mock.questions.filter(question_type="NUMERICAL").first()
        result = save_response(student, identity, numeric.pk, mutation(numeric, numeric="-01.2500"))
        assert result["response"]["numeric_answer"] == "-1.25"
        with pytest.raises(ExamConflict):
            save_response(student, identity, numeric.pk, mutation(numeric, 2, numeric="NaN"))
        with pytest.raises(ExamConflict):
            save_response(student, identity, numeric.pk, mutation(numeric, 2, option=option))
        with pytest.raises(ExamConflict):
            save_response(
                student,
                identity,
                question.pk,
                mutation(
                    question,
                    4,
                    option=mock.questions.filter(question_type="MCQ_SINGLE")
                    .last()
                    .options.first()
                    .pk,
                ),
            )


@pytest.mark.parametrize(
    "value,expected",
    [("", ""), ("-0", "0"), (".25", "0.25"), ("1.", "1"), ("+12", "12"), ("100", "100")],
)
def test_decimal_canonicalization(value, expected):
    assert canonical_numeric(value) == expected


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "1e4", "1,2", " 1", "1.000000001", "1234567890123", 1.2, "१"]
)
def test_decimal_rejects_invalid(value):
    with pytest.raises(ValueError):
        canonical_numeric(value)


def test_deadline_rejection_commits_auto_submission_and_no_late_answers(exam):
    mock, student = exam
    question = mock.questions.first()
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student)
    with patch("django.utils.timezone.now", return_value=mock.ends_at):
        with pytest.raises(ExamConflict):
            save_response(student, identity, question.pk, mutation(question))
        assert Attempt.objects.get(pk=identity).status == "AUTO_SUBMITTED"
        assert submit_attempt(student, identity)["submitted_at"] == mock.ends_at
        assert attempt_state(student, identity)["responses"] == []
        assert not StudentResponse.objects.exists()
        newcomer = paid_student(mock, 1)
        with pytest.raises(ExamConflict):
            started(mock, newcomer)
        assert not Attempt.objects.filter(student=newcomer).exists()


def test_save_checks_time_again_after_validation(exam):
    mock, student = exam
    question = mock.questions.first()
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student)
    with patch(
        "apps.attempts.services.timezone.now",
        side_effect=[mock.ends_at - timedelta(microseconds=1), mock.ends_at, mock.ends_at],
    ):
        with pytest.raises(ExamConflict):
            save_response(student, identity, question.pk, mutation(question))
    assert Attempt.objects.get(pk=identity).status == "AUTO_SUBMITTED"
    assert not StudentResponse.objects.exists()


def test_cet_global_transition_no_early_or_closed_phase_writes():
    mock = exam_fixture("MHT_CET_PCM")
    student = paid_student(mock)
    pc = mock.questions.filter(phase__order=1).first()
    maths = mock.questions.filter(phase__order=2).first()
    boundary = mock.starts_at + timedelta(minutes=90)
    with patch("django.utils.timezone.now", return_value=boundary - timedelta(seconds=1)):
        identity = started(mock, student)
        paper = student_paper(student, identity)
        assert len(paper["questions"]) == 100
        assert all(q["subject"] != "MATHEMATICS" for q in paper["questions"])
        assert paper["state"]["phase_ends_at"] == boundary
        with pytest.raises(ExamConflict):
            save_response(student, identity, maths.pk, mutation(maths))
        with pytest.raises(ExamConflict):
            submit_attempt(student, identity)
        save_response(student, identity, pc.pk, mutation(pc, review=True))
    with patch("django.utils.timezone.now", return_value=boundary):
        with pytest.raises(ExamConflict):
            save_response(student, identity, pc.pk, mutation(pc, 2))
        assert heartbeat(student, identity)["current_phase"]["order"] == 2
        paper = student_paper(student, identity)
        assert len(paper["questions"]) == 50
        assert paper["state"]["responses"] == []
        late = paid_student(mock, 1)
        assert start_attempt(late, mock.pk)["current_phase"]["order"] == 2
        save_response(student, identity, maths.pk, mutation(maths))
        assert submit_attempt(student, identity)["status"] == "SUBMITTED"


def test_reconciliation_command_batches_and_repeat(exam):
    mock, student = exam
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student)
        started(mock, paid_student(mock, 1))
    with patch("django.utils.timezone.now", return_value=mock.ends_at + timedelta(hours=4)):
        output = io.StringIO()
        call_command("reconcile_expired_attempts", batch_size=1, stdout=output)
        assert "2" in output.getvalue()
        assert reconcile_expired(batch_size=1) == 0
    assert Attempt.objects.get(pk=identity).submitted_at == mock.ends_at
    assert Attempt.objects.filter(status="AUTO_SUBMITTED").count() == 2


def test_payload_whitelist_ownership_api_input_and_readonly_records(exam):
    mock, student = exam
    client = APIClient()
    assert client.post(f"/api/v1/mocks/{mock.pk}/start/", {}, format="json").status_code == 401
    client.force_authenticate(student)
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        response = client.post(f"/api/v1/mocks/{mock.pk}/start/", {}, format="json")
        assert response.status_code == 200
        identity = response.data["attempt_id"]
        payload = client.get(f"/api/v1/attempts/{identity}/paper/")
        assert payload.status_code == 200 and "no-store" in payload["Cache-Control"]
        encoded = json.dumps(payload.data, default=str)
        for secret in [
            "correct",
            "explanation",
            "tolerance",
            "positive_marks",
            "negative_marks",
            "audit",
        ]:
            assert secret not in encoded
        assert set(payload.data["questions"][0]) == {
            "id",
            "question_number",
            "phase_id",
            "subject",
            "question_type",
            "question_text_md",
            "question_image_url",
            "options",
        }
        stranger = User.objects.create_user(email="other@test.invalid", google_sub="other")
        with pytest.raises(NotFound):
            student_paper(stranger, identity)
        question = mock.questions.first()
        for extra in [
            {"client_time": str(mock.starts_at)},
            {"mutation_version": 0},
            {"numeric_answer": 1.5},
            {"mutation_version": 9007199254740992},
        ]:
            data = mutation(question) | extra
            assert (
                client.put(
                    f"/api/v1/attempts/{identity}/responses/{question.pk}/", data, format="json"
                ).status_code
                == 400
            )
        with pytest.raises(ValidationError):
            Attempt.objects.get(pk=identity).save()
        with pytest.raises(ValidationError):
            Attempt.objects.filter(pk=identity).update(status="SUBMITTED")


def test_heartbeat_throttles_writes_and_cancelled_is_invalid(exam):
    mock, student = exam
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student)
    with patch("django.utils.timezone.now", return_value=mock.starts_at + timedelta(seconds=10)):
        heartbeat(student, identity)
        assert Attempt.objects.get(pk=identity).last_heartbeat_at == mock.starts_at
    with patch("django.utils.timezone.now", return_value=mock.starts_at + timedelta(seconds=31)):
        heartbeat(student, identity)
        assert (
            Attempt.objects.get(pk=identity).last_heartbeat_at.second
            == (mock.starts_at + timedelta(seconds=31)).second
        )
        models.QuerySet.update(type(mock).objects.filter(pk=mock.pk), status="CANCELLED")
        assert heartbeat(student, identity)["status"] == "INVALID"
        assert exam_info(student, mock.pk)["can_start"] is False


def concurrent(operations):
    barrier = Barrier(len(operations))

    def run(operation):
        close_old_connections()
        try:
            barrier.wait(timeout=20)
            try:
                return operation()
            except ExamConflict as exc:
                return exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        return list(executor.map(run, operations))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "race", ["start", "save_save", "save_submit", "submit_submit", "deadline", "cet_boundary"]
)
def test_postgresql_races(race):
    if connection.vendor != "postgresql":
        pytest.skip("Requires real PostgreSQL row locks")
    mock = exam_fixture("MHT_CET_PCM" if race == "cet_boundary" else "JEE_MAIN")
    student = paid_student(mock)
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        identity = started(mock, student) if race != "start" else None
        q = mock.questions.filter(question_type="MCQ_SINGLE").first()
        option = q.options.first().pk
        if race == "start":
            results = concurrent([lambda: started(mock, student)] * 8)
            assert len(set(results)) == 1 and Attempt.objects.count() == 1
        elif race == "save_save":
            concurrent(
                [
                    lambda: save_response(student, identity, q.pk, mutation(q, 1)),
                    lambda: save_response(student, identity, q.pk, mutation(q, 2, option=option)),
                ]
            )
            assert StudentResponse.objects.get().mutation_version == 2
        elif race == "save_submit":
            results = concurrent(
                [
                    lambda: save_response(student, identity, q.pk, mutation(q, option=option)),
                    lambda: submit_attempt(student, identity),
                ]
            )
            assert Attempt.objects.get().status == "SUBMITTED"
            assert StudentResponse.objects.count() == (not isinstance(results[0], ExamConflict))
        elif race == "submit_submit":
            results = concurrent([lambda: submit_attempt(student, identity)] * 8)
            assert {r["status"] for r in results} == {"SUBMITTED"}
            assert len({r["submitted_at"] for r in results}) == 1
    if race in {"deadline", "cet_boundary"}:
        at = mock.ends_at if race == "deadline" else mock.starts_at + timedelta(minutes=90)
        with patch("django.utils.timezone.now", return_value=at):
            results = concurrent(
                [
                    lambda: save_response(student, identity, q.pk, mutation(q)),
                    lambda: heartbeat(student, identity),
                    lambda: reconcile_expired(),
                ]
            )
            assert isinstance(results[0], ExamConflict)
            assert not StudentResponse.objects.exists()
            assert Attempt.objects.get().status == (
                "AUTO_SUBMITTED" if race == "deadline" else "IN_PROGRESS"
            )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("boundary", ["end", "cet_phase"])
def test_waiting_save_uses_time_after_postgresql_lock(boundary):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL lock wait introspection")
    mock = exam_fixture("MHT_CET_PCM" if boundary == "cet_phase" else "JEE_MAIN")
    student = paid_student(mock)
    deadline = mock.ends_at if boundary == "end" else mock.starts_at + timedelta(minutes=90)
    question = mock.questions.filter(phase__order=1).first()
    attempting = Event()

    def saving():
        close_old_connections()
        try:
            attempting.set()
            return save_response(student, identity, question.pk, mutation(question))
        except ExamConflict as exc:
            return exc
        finally:
            connections.close_all()

    with patch("django.utils.timezone.now", return_value=deadline - timedelta(seconds=1)) as clock:
        identity = started(mock, student)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Attempt.objects.select_for_update().get(pk=identity)
                future = pool.submit(saving)
                assert attempting.wait(timeout=10)
                # Wait for an actual DB lock waiter, not an arbitrary sleep.
                from time import monotonic

                until = monotonic() + 10
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() AND wait_event_type='Lock'"
                        )
                        waiting = cursor.fetchone()[0]
                    if waiting:
                        break
                    assert monotonic() < until, "Save never reached row-lock wait"
                clock.return_value = deadline
            assert isinstance(future.result(timeout=10), ExamConflict)
    assert not StudentResponse.objects.exists()
    assert Attempt.objects.get().status == (
        "AUTO_SUBMITTED" if boundary == "end" else "IN_PROGRESS"
    )


def test_admin_reconciles_and_cannot_edit(exam):
    from django.contrib import admin
    from django.test import RequestFactory

    from apps.attempts.admin import AttemptAdmin

    mock, student = exam
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        started(mock, student)
    request = RequestFactory().get("/admin/attempts/attempt/")
    request.user = User.objects.get(is_superuser=True)
    view = AttemptAdmin(Attempt, admin.site)
    with patch("django.utils.timezone.now", return_value=mock.ends_at):
        assert view.get_queryset(request).get().status == "AUTO_SUBMITTED"
    assert not view.has_add_permission(request)
    assert not view.has_delete_permission(request)
    assert "status" in view.get_readonly_fields(request)
