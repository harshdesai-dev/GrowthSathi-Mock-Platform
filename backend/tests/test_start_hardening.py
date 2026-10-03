"""Start-path performance changes must preserve fresh validation and row-lock safety."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from time import monotonic
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, connections, models, transaction
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.attempts.models import Attempt
from apps.attempts.services import ExamConflict, ExamDenied, start_attempt
from apps.exams.models import MockTest
from apps.exams.validation import _row_field_errors, validate_paper
from tests.attempt_helpers import exam_fixture, paid_student
from tests.test_attempts import concurrent

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("seconds_after", [0, 1])
def test_new_start_at_or_after_deadline_never_creates_attempt(seconds_after):
    mock = exam_fixture()
    student = paid_student(mock)
    with (
        patch(
            "django.utils.timezone.now",
            return_value=mock.ends_at + timedelta(seconds=seconds_after),
        ),
        pytest.raises(ExamConflict, match="window has ended"),
    ):
        start_attempt(student, mock.pk)
    assert not Attempt.objects.exists()


@pytest.mark.parametrize(
    "corruption", ["question", "option", "answer_shape", "rule", "phase", "scheme"]
)
def test_warm_validation_rechecks_current_content_without_timestamp_changes(corruption):
    mock = exam_fixture()
    student = paid_student(mock)
    _row_field_errors.cache_clear()
    assert validate_paper(mock, persisted=True).valid
    cold = _row_field_errors.cache_info()
    assert validate_paper(mock, persisted=True).valid
    assert _row_field_errors.cache_info().hits > cold.hits
    question = mock.questions.filter(question_type="MCQ_SINGLE").first()
    # Deliberately bypass authoring guards, as in the existing invalid-paper test.
    # No updated_at write: a version/timestamp-only validity cache would be unsafe.
    if corruption == "question":
        models.QuerySet.update(mock.questions.filter(pk=question.pk), question_image_url="invalid")
    elif corruption == "option":
        models.QuerySet.update(question.options.all(), option_text_md="", option_image_url="")
    elif corruption == "answer_shape":
        models.QuerySet.update(question.options.all(), is_correct=False)
    elif corruption == "rule":
        models.QuerySet.update(mock.exam_scheme.phases.first().rules.all(), positive_marks=5)
    elif corruption == "phase":
        models.QuerySet.update(mock.phases.all(), start_offset_minutes=1)
    else:
        models.QuerySet.update(type(mock.exam_scheme).objects.all(), total_question_count=76)
    mock.refresh_from_db()
    assert not validate_paper(mock, persisted=True).valid
    assert not validate_paper(mock).valid
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        with pytest.raises(ExamDenied, match="not valid"):
            start_attempt(student, mock.pk)
    assert not Attempt.objects.exists()


@pytest.mark.parametrize("code", ["JEE_MAIN", "MHT_CET_PCM"])
def test_cold_warm_evicted_validation_and_start_query_budget(code):
    mock = exam_fixture(code)
    student = paid_student(mock)
    _row_field_errors.cache_clear()
    assert validate_paper(mock, persisted=True).valid
    assert validate_paper(mock).valid
    _row_field_errors.cache_clear()  # Eviction/process restart cannot affect validity.
    assert validate_paper(mock, persisted=True).valid
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        first = start_attempt(student, mock.pk)
        other = paid_student(mock, 1)
        with CaptureQueriesContext(connection) as queries:
            second = start_attempt(other, mock.pk)
        # Includes transaction/savepoints; constant in paper size, no per-row queries.
        assert len(queries) <= 15, [query["sql"] for query in queries]
        assert first["attempt_id"] != second["attempt_id"]
        assert second["responses"] == []
        assert second["saved_response_count"] == second["answered_count"] == 0
        assert second["mock_ends_at"] == mock.ends_at


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "locked_row,boundary", [("student", "end"), ("mock", "end"), ("mock", "cet")]
)
def test_start_waiting_for_postgresql_lock_rechecks_global_time(locked_row, boundary):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL lock wait introspection")
    mock = exam_fixture("MHT_CET_PCM" if boundary == "cet" else "JEE_MAIN")
    student = paid_student(mock)
    deadline = mock.ends_at if boundary == "end" else mock.starts_at + timedelta(minutes=90)

    def starting():
        close_old_connections()
        try:
            return start_attempt(student, mock.pk)
        except ExamConflict as exc:
            return exc
        finally:
            connections.close_all()

    with patch("django.utils.timezone.now", return_value=deadline - timedelta(seconds=1)) as clock:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                if locked_row == "student":
                    User.objects.select_for_update().get(pk=student.pk)
                else:
                    MockTest.objects.select_for_update().get(pk=mock.pk)
                future = pool.submit(starting)
                until = monotonic() + 15
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
                    assert monotonic() < until, "Start never reached row-lock wait"
                clock.return_value = deadline
            result = future.result(timeout=15)
    if boundary == "end":
        assert isinstance(result, ExamConflict)
        assert not Attempt.objects.exists()
    else:
        assert result["current_phase"]["order"] == 2
        assert result["started_at"] == deadline
        assert result["mock_ends_at"] == mock.ends_at


@pytest.mark.django_db(transaction=True)
def test_distinct_students_and_duplicate_starts_with_cold_cache():
    if connection.vendor != "postgresql":
        pytest.skip("Requires real PostgreSQL row locks")
    mock = exam_fixture()
    students = [paid_student(mock, number) for number in range(8)]
    _row_field_errors.cache_clear()
    with patch("django.utils.timezone.now", return_value=mock.starts_at):
        results = concurrent(
            [lambda student=student: start_attempt(student, mock.pk) for student in students] * 2
        )
    assert all(isinstance(result, dict) for result in results)
    assert len({result["attempt_id"] for result in results}) == 8
    assert Attempt.objects.count() == 8
