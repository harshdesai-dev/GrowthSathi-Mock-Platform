"""Guarded 500-student PostgreSQL result benchmark. Creates fixtures, never deletes data.

Run on a new migrated empty database ending in phase5_results. No production data,
gateway calls, HTTP timing claims or real official-rule attestations are involved.
"""

import io
import json
import os
import time
from datetime import timedelta
from unittest.mock import patch

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection, models  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from apps.accounts.models import StudentProfile, User  # noqa: E402
from apps.attempts.models import Attempt, StudentResponse  # noqa: E402
from apps.exams.models import ExamScheme, MockTest  # noqa: E402
from apps.exams.validation import _row_field_errors  # noqa: E402
from apps.results.models import Result  # noqa: E402
from apps.results.services import (  # noqa: E402
    calculate_results,
    publish_results,
    verify_answer_key,
)
from tests.test_exam_administration import make_mock, populate, verify  # noqa: E402


def measured(operation):
    started = time.perf_counter()
    with CaptureQueriesContext(connection) as queries:
        value = operation()
    return value, {"seconds": round(time.perf_counter() - started, 3), "queries": len(queries)}


def main():
    if connection.vendor != "postgresql" or not settings.DATABASES["default"]["NAME"].endswith(
        "phase5_results"
    ):
        raise SystemExit("Refusing: use an isolated PostgreSQL database ending in phase5_results.")
    if User.objects.exists() or MockTest.objects.exists():
        raise SystemExit(
            "Refusing: fixture database must be empty; retained data is never deleted."
        )
    call_command("seed_exam_schemes", stdout=io.StringIO())
    owner = User.objects.create_superuser(
        email="result-owner@test.invalid", google_sub="result-owner"
    )
    users = [User(email=f"result-{i}@test.invalid", google_sub=f"result-{i}") for i in range(500)]
    User.objects.bulk_create(users)
    StudentProfile.objects.bulk_create(
        [
            StudentProfile(
                user=user, full_name=f"Synthetic Participant{i}", onboarding_completed=True
            )
            for i, user in enumerate(users)
        ],
        ignore_conflicts=True,
    )
    report = []
    for code, maximum, total_questions in [("JEE_MAIN", 300, 75), ("MHT_CET_PCM", 200, 150)]:
        mock = make_mock(
            ExamScheme.objects.get(exam_type__code=code), slug=f"benchmark-{code.lower()}"
        )
        populate(mock, owner)
        verify(mock, owner)
        models.QuerySet.update(MockTest.objects.filter(pk=mock.pk), status="CLOSED")
        mock.refresh_from_db()
        questions = list(mock.questions.prefetch_related("options").all())
        assert len(questions) == total_questions
        attempts = [
            Attempt(
                student=user,
                mock_test=mock,
                started_at=mock.starts_at,
                submitted_at=None if i < 5 else mock.ends_at,
                status="IN_PROGRESS" if i < 5 else "SUBMITTED",
            )
            for i, user in enumerate(users)
        ]
        models.QuerySet(model=Attempt).bulk_create(attempts, batch_size=500)
        responses = []
        expected_scores = []
        for i, attempt in enumerate(attempts):
            expected = 0
            for j, question in enumerate(questions):
                correct = i == 0 or (i + j) % 3 != 0
                blank = i != 0 and (i + j) % 10 == 0
                options = list(question.options.all())
                option = (
                    None
                    if blank or not options
                    else next(item for item in options if item.is_correct == correct)
                )
                numeric = "" if blank or options else "1" if correct else "999"
                responses.append(
                    StudentResponse(
                        attempt=attempt,
                        question=question,
                        selected_option=option,
                        numeric_answer=numeric,
                        first_visited_at=mock.starts_at,
                        mutation_version=1,
                    )
                )
                expected += (
                    0 if blank else question.positive_marks if correct else -question.negative_marks
                )
            expected_scores.append(expected)
        models.QuerySet(model=StudentResponse).bulk_create(responses, batch_size=1000)
        del responses
        _row_field_errors.cache_clear()
        with patch(
            "django.utils.timezone.now", return_value=mock.result_release_at + timedelta(seconds=1)
        ):
            run, verification = measured(
                lambda mock=mock: verify_answer_key(
                    mock.pk,
                    actor=owner,
                    notes="Synthetic benchmark keys checked, not official attestation.",
                )
            )
            _row_field_errors.cache_clear()
            run, calculation = measured(lambda run=run: calculate_results(run.pk, actor=owner))
            _, publication = measured(lambda run=run: publish_results(run.pk, actor=owner))
        scores = dict(
            Result.objects.filter(attempt__mock_test=mock).values_list("attempt_id", "score")
        )
        assert len(scores) == run.participant_count == 500
        assert scores[attempts[0].pk] == maximum
        assert all(
            scores[attempt.pk] == expected
            for attempt, expected in zip(attempts, expected_scores, strict=True)
        )
        assert Attempt.objects.filter(mock_test=mock, status="IN_PROGRESS").count() == 0
        assert calculation["queries"] < 60 and publication["queries"] < 60, (
            "Possible N+1 regression"
        )
        record = {
            "exam": code,
            "participants": 500,
            "questions": total_questions,
            "saved_responses": 500 * total_questions,
            "verification": verification,
            "calculation": calculation,
            "publication": publication,
            "assertions": "500 expected scores, maximum, membership and reconciliation passed",
        }
        report.append(record)
        print(json.dumps(record), flush=True)
    print(json.dumps({"result_batches": report}, indent=2), flush=True)


if __name__ == "__main__":
    main()
