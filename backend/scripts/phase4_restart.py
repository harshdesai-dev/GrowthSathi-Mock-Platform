"""Two separate process invocations verify recovery without application memory."""

import argparse
import os
from datetime import timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.attempts.models import Attempt  # noqa: E402
from apps.attempts.services import save_response, start_attempt, submit_attempt  # noqa: E402
from apps.attempts.student_payload import student_paper  # noqa: E402
from apps.exams.models import ExamScheme  # noqa: E402
from apps.exams.services import transition_mock  # noqa: E402
from tests.attempt_helpers import mutation, paid_student  # noqa: E402
from tests.test_exam_administration import make_mock, populate, verify  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "recover"])
    stage = parser.parse_args().stage
    if connection.vendor != "postgresql" or not settings.DATABASES["default"]["NAME"].endswith(
        "phase4_restart"
    ):
        raise SystemExit("Use only a dedicated PostgreSQL database ending in phase4_restart.")
    if stage == "prepare":
        from django.core.management import call_command

        from apps.accounts.models import User

        if User.objects.exists():
            raise SystemExit("Use an empty migrated database.")
        call_command("seed_exam_schemes")
        owner = User.objects.create_superuser(email="restart@test.invalid", google_sub="restart")
        mock = make_mock(ExamScheme.objects.get(exam_type__code="JEE_MAIN"))
        mock.starts_at = timezone.now() - timedelta(minutes=5)
        mock.ends_at = mock.starts_at + timedelta(minutes=180)
        mock.result_release_at = mock.ends_at + timedelta(minutes=10)
        mock.save()
        populate(mock, owner)
        verify(mock, owner)
        transition_mock(mock.pk, "SCHEDULED", actor=owner)
        student = paid_student(mock)
        identity = start_attempt(student, mock.pk)["attempt_id"]
        question = mock.questions.filter(question_type="MCQ_SINGLE").first()
        save_response(
            student,
            identity,
            question.pk,
            mutation(question, 7, option=question.options.first().pk),
        )
        print("PREPARE PASS: active attempt and version-7 response committed; process now exits.")
    else:
        attempt = Attempt.objects.select_related("student", "mock_test").get()
        original_start, original_end = attempt.started_at, attempt.mock_test.ends_at
        resumed = start_attempt(attempt.student, attempt.mock_test_id)
        assert resumed["attempt_id"] == str(attempt.pk)
        assert resumed["started_at"] == original_start and resumed["mock_ends_at"] == original_end
        paper = student_paper(attempt.student, attempt.pk)
        assert (
            len(paper["questions"]) == 75
            and paper["state"]["responses"][0]["mutation_version"] == 7
        )
        assert submit_attempt(attempt.student, attempt.pk)["status"] == "SUBMITTED"
        print(
            "RECOVER PASS: fresh process resumed same attempt/deadline/response and submitted once."
        )


if __name__ == "__main__":
    main()
