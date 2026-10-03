import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, connections, models
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attempts.models import Attempt, StudentResponse
from apps.exams.models import ExamScheme, MockTest
from apps.exams.services import correct_answer_key
from apps.results.api import dashboard_lifecycle
from apps.results.models import Result, ResultCalculationEntry, ResultCalculationRun
from apps.results.scoring import participant_reason, rank_scores, score_attempt, score_question
from apps.results.services import (
    calculate_results,
    publish_results,
    reconcile_for_results,
    verify_answer_key,
    withdraw_results,
)
from tests.attempt_helpers import exam_fixture, paid_student
from tests.test_exam_administration import make_mock, populate


def question(kind="MCQ_SINGLE", positive="4", negative="1", tolerance="0"):
    return {
        "id": "q",
        "question_type": kind,
        "positive_marks": positive,
        "negative_marks": negative,
        "unanswered_marks": "0",
        "options": [{"id": "a"}, {"id": "b"}],
        "correct_option": "a",
        "correct_numeric_answer": "1",
        "numeric_tolerance": tolerance,
    }


@pytest.mark.parametrize(
    "response,outcome,marks",
    [
        ({}, "Unattempted", "0"),
        ({"selected_option": "a"}, "Correct", "4"),
        ({"selected_option": "b"}, "Incorrect", "-1"),
    ],
)
def test_jee_mcq(response, outcome, marks):
    assert score_question(question(), response) == {"outcome": outcome, "marks": Decimal(marks)}


@pytest.mark.parametrize(
    "answer,tolerance,correct",
    [
        ("1", "0", True),
        ("1.00000001", "0", False),
        ("1.10000000", ".1", True),
        (".9", ".1", True),
        ("1.10000001", ".1", False),
        (".89999999", ".1", False),
        ("-1", "2", True),
    ],
)
def test_numerical_boundaries(answer, tolerance, correct):
    outcome = score_question(question("NUMERICAL", tolerance=tolerance), {"numeric_answer": answer})
    assert outcome == {
        "outcome": "Correct" if correct else "Incorrect",
        "marks": Decimal(4 if correct else -1),
    }


@pytest.mark.parametrize("answer", [float("nan"), 1.0, "NaN", "Infinity", "not-decimal"])
def test_unsafe_numerical_rejected(answer):
    with pytest.raises(ValueError):
        score_question(question("NUMERICAL"), {"numeric_answer": answer})


@pytest.mark.parametrize(
    "subject,marks", [("PHYSICS", "1"), ("CHEMISTRY", "1"), ("MATHEMATICS", "2")]
)
def test_cet_rules(subject, marks):
    configured = {**question(positive=marks, negative="0"), "subject": subject}
    assert score_question(configured, {"selected_option": "a"})["marks"] == Decimal(marks)
    assert score_question(configured, {"selected_option": "b"})["marks"] == 0
    assert score_question(configured)["marks"] == 0


def test_counts_zero_maximum_and_determinism():
    paper = [{**question(), "id": str(i)} for i in range(75)]
    answers = {q["id"]: {"selected_option": "a"} for q in paper}
    before = copy.deepcopy((paper, answers))
    assert score_attempt(paper, answers) == {
        "score": Decimal(300),
        "correct_count": 75,
        "incorrect_count": 0,
        "attempted_count": 75,
        "unattempted_count": 0,
    }
    assert score_attempt(paper, {})["score"] == 0
    answers["0"] = {"selected_option": "b"}
    answers.pop("1")
    expected = {
        "score": Decimal(291),
        "correct_count": 73,
        "incorrect_count": 1,
        "attempted_count": 74,
        "unattempted_count": 1,
    }
    assert (
        score_attempt(paper, answers)
        == score_attempt(paper, dict(reversed(list(answers.items()))))
        == expected
    )
    assert paper == before[0]


@pytest.mark.parametrize(
    "status,saved,eligible",
    [
        ("SUBMITTED", False, True),
        ("SUBMITTED", True, True),
        ("AUTO_SUBMITTED", True, True),
        ("AUTO_SUBMITTED", False, False),
        ("INVALID", True, False),
        ("IN_PROGRESS", False, False),
    ],
)
def test_central_eligibility(status, saved, eligible):
    assert (participant_reason(status, saved) is None) is eligible


def test_ranking_percentile_ties_rounding():
    ranked = rank_scores([Decimal(s) for s in [200, 190, 190, 180]])
    assert [ranked[Decimal(s)]["rank"] for s in [200, 190, 190, 180]] == [1, 2, 2, 4]
    assert [ranked[Decimal(s)]["percentile"] for s in [200, 190, 180]] == [100, 75, 25]
    assert rank_scores([Decimal(0)])[Decimal(0)] == {"rank": 1, "percentile": Decimal("100.00")}
    assert rank_scores([Decimal(-1), Decimal(0), Decimal(4)])[Decimal(-1)]["percentile"] == Decimal(
        "33.33"
    )
    assert rank_scores([1, 2, 3])[2]["percentile"] == Decimal("66.67")
    assert rank_scores([]) == {}


def prepared(code="JEE_MAIN", participants=3):
    mock = exam_fixture(code)
    owner = User.objects.get(is_superuser=True)
    students = [paid_student(mock, i) for i in range(participants)]
    for i, student in enumerate(students):
        student.profile.full_name = ["Harsh Desai", "Rahul Patel", "Sneha More"][i % 3]
        student.profile.save()
    attempts = [
        Attempt(
            student=student,
            mock_test=mock,
            status="SUBMITTED",
            started_at=mock.starts_at,
            submitted_at=mock.ends_at - timedelta(seconds=1),
        )
        for student in students
    ]
    models.QuerySet(model=Attempt).bulk_create(attempts)
    q = mock.questions.filter(question_type="MCQ_SINGLE").first()
    options = list(q.options.order_by("label"))
    responses = [
        StudentResponse(
            attempt=a,
            question=q,
            selected_option=options[i % 2],
            first_visited_at=mock.starts_at,
            mutation_version=1,
        )
        for i, a in enumerate(attempts)
    ]
    models.QuerySet(model=StudentResponse).bulk_create(responses)
    models.QuerySet.update(MockTest.objects.filter(pk=mock.pk), status="CLOSED")
    mock.refresh_from_db()
    return mock, owner, students, attempts, q


@pytest.fixture
def batch(db):
    fixture = prepared()
    with patch("django.utils.timezone.now", return_value=fixture[0].result_release_at):
        yield fixture


def calculated(mock, owner):
    run = verify_answer_key(
        mock.pk, actor=owner, notes="Synthetic key checked question-by-question."
    )
    return calculate_results(run.pk, actor=owner)


def client(student):
    api = APIClient()
    api.force_authenticate(student)
    return api


def test_batch_publication_api_privacy_and_review(batch):
    mock, owner, students, attempts, q = batch
    api = client(students[0])
    for suffix in ["result", "review", "leaderboard"]:
        response = api.get(f"/api/v1/mocks/{mock.pk}/{suffix}/")
        assert response.status_code == 409
        assert "correct_option" not in str(response.data)
        assert response["Cache-Control"] == "private, no-store"
    run = calculated(mock, owner)
    assert run.participant_count == 3 and not Result.objects.exists()
    assert api.get("/api/v1/results/history/").data == []
    assert calculate_results(run.pk, actor=owner).pk == run.pk
    published = publish_results(run.pk, actor=owner)
    assert publish_results(run.pk, actor=owner).published_at == published.published_at
    assert Result.objects.count() == 3 and ResultCalculationEntry.objects.count() == 3
    report = api.get(f"/api/v1/mocks/{mock.pk}/result/").data
    assert report["score"] == "4.00" and report["rank"] == 1 and report["percentile"] == "100.00"
    assert report["student_name"] == "Harsh Desai" and report["previous_score"] is None
    assert report["maximum_score"] == "300.00" and report["unattempted_count"] == 74
    review = api.get(f"/api/v1/mocks/{mock.pk}/review/")
    assert review.status_code == 200
    first = next(item for item in review.data["questions"] if item["id"] == str(q.pk))
    assert first["outcome"] == "Correct" and first["explanation_md"]
    assert first["selected_option"] == first["correct_option"]
    assert "mutation_version" not in str(review.data) and "is_correct" not in str(review.data)
    board = api.get(f"/api/v1/mocks/{mock.pk}/leaderboard/").data
    assert {r["name"] for r in board["rows"]} == {"Harsh D.", "Rahul P.", "Sneha M."}
    assert all(set(row) == {"rank", "name", "score", "percentile"} for row in board["rows"])
    assert "Desai" not in str(board) and "@" not in str(board)
    other = client(students[1]).get(f"/api/v1/mocks/{mock.pk}/review/?student_id={students[0].pk}")
    assert (
        next(item for item in other.data["questions"] if item["id"] == str(q.pk))["outcome"]
        == "Incorrect"
    )
    stranger = User.objects.create_user(email="stranger@test.invalid", google_sub="stranger")
    for suffix in ["result", "review"]:
        assert client(stranger).get(f"/api/v1/mocks/{mock.pk}/{suffix}/").status_code == 404
        assert APIClient().get(f"/api/v1/mocks/{mock.pk}/{suffix}/").status_code == 401
    assert len(api.get("/api/v1/results/history/").data) == 1


def test_eligibility_and_reconciliation(batch):
    mock, owner, students, attempts, q = batch
    models.QuerySet.update(
        Attempt.objects.filter(pk=attempts[0].pk), status="IN_PROGRESS", submitted_at=None
    )
    models.QuerySet.update(Attempt.objects.filter(pk=attempts[1].pk), status="INVALID")
    # Saved blank still qualifies for auto-submission; never-started purchaser does not.
    models.QuerySet.update(
        StudentResponse.objects.filter(attempt=attempts[0]), selected_option=None
    )
    never = paid_student(mock, 99)
    zero = Attempt(student=never, mock_test=mock, started_at=mock.starts_at, status="IN_PROGRESS")
    models.QuerySet(model=Attempt).bulk_create([zero])
    paid_student(mock, 100)
    outcome = reconcile_for_results(mock.pk, actor=owner)
    assert outcome["participant_count"] == 2 and len(outcome["excluded_attempts"]) == 2
    run = calculated(mock, owner)
    publish_results(run.pk, actor=owner)
    assert Result.objects.count() == 2
    assert Result.objects.get(attempt=attempts[0]).score == 0
    assert client(never).get(f"/api/v1/mocks/{mock.pk}/result/").status_code == 409
    zero.refresh_from_db()
    assert zero.status == "AUTO_SUBMITTED" and zero.submitted_at == mock.ends_at


def test_publication_guards_owner_state_release_and_calculation(batch):
    mock, owner, students, _, _ = batch
    with pytest.raises(PermissionDenied):
        verify_answer_key(mock.pk, actor=students[0], notes="not owner")
    with pytest.raises(ValidationError):
        verify_answer_key(mock.pk, actor=owner, notes=" ")
    run = verify_answer_key(mock.pk, actor=owner, notes="Checked")
    with pytest.raises(ValidationError, match="complete"):
        publish_results(run.pk, actor=owner)
    run = calculate_results(run.pk, actor=owner)
    with (
        patch(
            "django.utils.timezone.now", return_value=mock.result_release_at - timedelta(seconds=1)
        ),
        pytest.raises(ValidationError, match="Earliest"),
    ):
        publish_results(run.pk, actor=owner)
    models.QuerySet.update(MockTest.objects.filter(pk=mock.pk), status="LIVE")
    with pytest.raises(ValidationError, match="CLOSED"):
        publish_results(run.pk, actor=owner)
    assert not Result.objects.exists()


@pytest.mark.parametrize("tamper", ["membership", "score", "source", "responses", "snapshot"])
def test_incomplete_or_changed_batch_rejected(batch, tamper):
    mock, owner, _, attempts, q = batch
    run = calculated(mock, owner)
    if tamper == "membership":
        models.QuerySet.update(ResultCalculationRun.objects.filter(pk=run.pk), participant_count=2)
    elif tamper == "score":
        models.QuerySet.update(run.entries.filter(attempt=attempts[0]), score=99)
    elif tamper == "source":
        models.QuerySet.update(type(q).objects.filter(pk=q.pk), explanation_md="Changed")
    elif tamper == "snapshot":
        corrupted = copy.deepcopy(run.paper_snapshot)
        corrupted["questions"][0]["correct_option"] = "tampered"
        models.QuerySet.update(
            ResultCalculationRun.objects.filter(pk=run.pk), paper_snapshot=corrupted
        )
    else:
        models.QuerySet.update(
            StudentResponse.objects.filter(attempt=attempts[0]), selected_option=None
        )
    with pytest.raises(ValidationError):
        publish_results(run.pk, actor=owner)
    assert not Result.objects.exists()
    run.refresh_from_db()
    assert run.status == "INVALIDATED"


def test_correction_invalidates_recalculates_ranks_and_controlled_republish(batch):
    mock, owner, students, _, q = batch
    old = calculated(mock, owner)
    correct_answer_key(q.pk, actor=owner, reason="Synthetic key correction", correct_option="B")
    old.refresh_from_db()
    assert old.status == "INVALIDATED"
    with pytest.raises(ValidationError):
        publish_results(old.pk, actor=owner)
    run = calculated(mock, owner)
    publish_results(run.pk, actor=owner)
    assert list(Result.objects.order_by("rank").values_list("score", "rank", "percentile")) == [
        (Decimal(4), 1, Decimal(100)),
        (Decimal(-1), 2, Decimal("66.67")),
        (Decimal(-1), 2, Decimal("66.67")),
    ]
    with pytest.raises(ValidationError):
        correct_answer_key(q.pk, actor=owner, reason="Must withdraw first", correct_option="A")
    with pytest.raises(ValidationError):
        withdraw_results(run.pk, actor=owner, reason="")
    withdraw_results(run.pk, actor=owner, reason="Confirmed key issue; retract before correcting")
    for suffix in ["result", "review", "leaderboard"]:
        assert client(students[0]).get(f"/api/v1/mocks/{mock.pk}/{suffix}/").status_code == 409
    assert client(students[0]).get("/api/v1/results/history/").data == []
    correct_answer_key(q.pk, actor=owner, reason="Restore checked answer", correct_option="A")
    new = calculated(mock, owner)
    with (
        patch.object(MockTest, "save", side_effect=RuntimeError("Republish rollback")),
        pytest.raises(RuntimeError),
    ):
        publish_results(new.pk, actor=owner)
    assert set(Result.objects.values_list("calculation_run_id", flat=True)) == {run.pk}
    assert client(students[0]).get(f"/api/v1/mocks/{mock.pk}/review/").status_code == 409
    publish_results(new.pk, actor=owner)
    assert Result.objects.count() == 3
    assert set(Result.objects.values_list("calculation_run_id", flat=True)) == {new.pk}
    run.refresh_from_db()
    assert run.status == "WITHDRAWN" and run.withdrawn_by == owner and run.withdrawal_reason
    assert old.entries.count() == run.entries.count() == new.entries.count() == 3
    assert Result.objects.get(attempt__student=students[0]).score == 4


def test_atomic_publication_rollback(batch):
    mock, owner, _, _, _ = batch
    run = calculated(mock, owner)
    with (
        patch.object(
            MockTest, "save", side_effect=RuntimeError("Simulated final status-write failure")
        ),
        pytest.raises(RuntimeError),
    ):
        publish_results(run.pk, actor=owner)
    assert not Result.objects.exists()
    run.refresh_from_db()
    assert run.status == "COMPLETE"
    publish_results(run.pk, actor=owner)
    assert Result.objects.count() == 3


def test_previous_score_only_earlier_published_same_exam(batch):
    current, owner, students, _, _ = batch
    for days, code, publish in [
        (4, "JEE_MAIN", True),
        (3, "JEE_MAIN", True),
        (2, "MHT_CET_PCM", True),
        (1, "JEE_MAIN", False),
    ]:
        earlier = make_mock(ExamScheme.objects.get(exam_type__code=code), slug=f"earlier-{days}")
        earlier.starts_at = current.starts_at - timedelta(days=days)
        earlier.ends_at = earlier.starts_at + timedelta(minutes=180)
        earlier.result_release_at = earlier.ends_at + timedelta(minutes=10)
        earlier.save()
        populate(earlier, owner)
        models.QuerySet.update(MockTest.objects.filter(pk=earlier.pk), status="CLOSED")
        attempt = Attempt(
            student=students[0],
            mock_test=earlier,
            started_at=earlier.starts_at,
            submitted_at=earlier.ends_at,
            status="SUBMITTED",
        )
        models.QuerySet(model=Attempt).bulk_create([attempt])
        if days == 4:
            q = earlier.questions.filter(question_type="MCQ_SINGLE").first()
            models.QuerySet(model=StudentResponse).bulk_create(
                [
                    StudentResponse(
                        attempt=attempt,
                        question=q,
                        selected_option=q.options.get(is_correct=True),
                        first_visited_at=earlier.starts_at,
                        mutation_version=1,
                    )
                ]
            )
        run = calculated(earlier, owner)
        if publish:
            publish_results(run.pk, actor=owner)
    run = calculated(current, owner)
    publish_results(run.pk, actor=owner)
    report = client(students[0]).get(f"/api/v1/mocks/{current.pk}/result/").data
    assert report["previous_score"] == "0.00" and report["score_difference"] == "4.00"
    assert len(client(students[0]).get("/api/v1/results/history/").data) == 4
    assert len(client(students[1]).get("/api/v1/results/history/").data) == 1


def test_blank_submission_included_and_empty_batch(batch):
    mock, owner, _, attempts, _ = batch
    # Clear answers without deleting accepted response history.
    models.QuerySet.update(StudentResponse.objects.all(), selected_option=None)
    run = calculated(mock, owner)
    assert {entry.score for entry in run.entries.all()} == {0}
    assert all(entry.unattempted_count == 75 for entry in run.entries.all())
    models.QuerySet.update(
        Attempt.objects.filter(pk__in=[a.pk for a in attempts]), status="INVALID"
    )
    with pytest.raises(ValidationError):
        publish_results(run.pk, actor=owner)
    empty = calculated(mock, owner)
    assert empty.participant_count == 0
    publish_results(empty.pk, actor=owner)
    assert not Result.objects.exists()


def test_failed_calculation_has_no_partial_entries_and_can_retry(batch):
    mock, owner, _, _, _ = batch
    run = verify_answer_key(mock.pk, actor=owner, notes="Checked")
    with (
        patch("apps.results.services.score_attempt", side_effect=ValueError("Malformed input")),
        pytest.raises(ValidationError),
    ):
        calculate_results(run.pk, actor=owner)
    run.refresh_from_db()
    assert run.status == "FAILED" and not run.entries.exists() and run.errors == "Malformed input"
    replacement = calculated(mock, owner)
    assert replacement.pk != run.pk and replacement.participant_count == 3


def test_early_close_cannot_release_keys_and_invalid_key_rejected(batch):
    mock, owner, _, _, q = batch
    with (
        patch("django.utils.timezone.now", return_value=mock.ends_at - timedelta(seconds=1)),
        pytest.raises(ValidationError, match="global exam window"),
    ):
        verify_answer_key(mock.pk, actor=owner, notes="Too early")
    models.QuerySet.update(q.options.all(), is_correct=False)
    with pytest.raises(ValidationError):
        verify_answer_key(mock.pk, actor=owner, notes="Invalid key")
    assert not ResultCalculationRun.objects.exists()


def test_direct_edits_blocked_and_admin_scope(batch, client):
    mock, owner, students, _, _ = batch
    run = calculated(mock, owner)
    for obj in [run, run.entries.first()]:
        with pytest.raises(ValidationError):
            obj.save()
        with pytest.raises(ValidationError):
            obj.delete()
    with pytest.raises(ValidationError):
        run.entries.update(score=100)
    url = reverse("admin:results_operations", args=[mock.pk])
    client.force_login(owner)
    assert client.get(url).status_code == 200
    assert (
        client.post(url, {"operation": "publish", "run": run.pk, "confirm": "on"}).status_code
        == 302
    )
    assert Result.objects.count() == 3
    students[0].is_staff = True
    students[0].save()
    client.force_login(students[0])
    assert client.get(url).status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("race", ["calculate", "publish", "correct_publish", "calculate_publish"])
def test_postgres_batch_races(race):
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row-lock test")
    mock, owner, _, _, q = prepared()
    with patch("django.utils.timezone.now", return_value=mock.result_release_at):
        run = verify_answer_key(mock.pk, actor=owner, notes="Concurrency fixture")
        if race != "calculate":
            calculate_results(run.pk, actor=owner)
        barrier = Barrier(2)

        def worker(index):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                if race == "calculate" or (race == "calculate_publish" and index == 0):
                    calculate_results(run.pk, actor=owner)
                elif race == "correct_publish" and index == 0:
                    correct_answer_key(
                        q.pk, actor=owner, reason="Racing correction", correct_option="B"
                    )
                else:
                    publish_results(run.pk, actor=owner)
                return "ok"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker, [0, 1]))
        assert "ok" in outcomes
        assert ResultCalculationRun.objects.count() == 1
        assert run.entries.count() == 3
        if race == "calculate":
            assert outcomes == ["ok", "ok"] and not Result.objects.exists()
        elif race == "publish":
            assert outcomes == ["ok", "ok"] and Result.objects.count() == 3
        elif race == "correct_publish":
            assert outcomes.count("rejected") == 1
            assert Result.objects.count() in {0, 3}
        else:
            assert Result.objects.count() == 3
        assert Result.objects.values("attempt_id").distinct().count() == Result.objects.count()


@pytest.mark.django_db(transaction=True)
def test_postgres_duplicate_verify_and_calculate_starts():
    if connection.vendor != "postgresql":
        pytest.skip("Real PostgreSQL row-lock test")
    mock, owner, _, _, _ = prepared()
    barrier = Barrier(2)

    def worker(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return calculated(mock, owner).pk
        finally:
            connections.close_all()

    with (
        patch("django.utils.timezone.now", return_value=mock.result_release_at),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        identities = list(pool.map(worker, [0, 1]))
    assert identities[0] == identities[1]
    assert ResultCalculationRun.objects.count() == 1
    assert ResultCalculationEntry.objects.count() == 3


def test_dashboard_is_authenticated_private_and_only_exposes_published_results(batch):
    mock, owner, students, _, _ = batch
    anonymous = APIClient().get("/api/v1/dashboard/")
    assert anonymous.status_code == 401

    before = client(students[0]).get("/api/v1/dashboard/")
    assert before.status_code == 200
    assert before.data["latest_result"] is None
    assert before.data["upcoming_mocks"][0]["lifecycle_state"] == "RESULT_PENDING"
    assert all("email" not in str(item) for item in before.data["upcoming_mocks"])
    assert set(before.data["upcoming_mocks"][0]) == {
        "id",
        "title",
        "exam",
        "starts_at",
        "ends_at",
        "access_state",
        "lifecycle_state",
        "can_start",
        "attempt_id",
        "attempt_status",
    }

    stranger = User.objects.create_user(
        email="dashboard-stranger@test.invalid", google_sub="dashboard-stranger"
    )
    stranger_data = client(stranger).get("/api/v1/dashboard/").data
    assert stranger_data["upcoming_mocks"][0]["access_state"] == "NOT_PURCHASED"
    assert stranger_data["upcoming_mocks"][0]["can_start"] is False
    assert stranger_data["upcoming_mocks"][0]["attempt_id"] is None

    run = calculated(mock, owner)
    publish_results(run.pk, actor=owner)
    published = client(students[0]).get("/api/v1/dashboard/")
    assert published.status_code == 200
    assert published["Cache-Control"] == "private, no-store"
    assert published.data["latest_result"]["mock_id"] == str(mock.pk)
    assert published.data["latest_result"]["score"] == "4.00"
    assert published.data["history"][0]["mock_id"] == str(mock.pk)
    assert "student_name" not in str(published.data)
    assert client(stranger).get(f"/api/v1/dashboard/?student_id={students[0].pk}").data == {
        "server_time": published.data["server_time"],
        "next_mock": None,
        "upcoming_mocks": [],
        "latest_result": None,
        "history": [],
    }


@pytest.mark.parametrize(
    ("status", "starts_offset", "ends_offset", "attempt_status", "expected"),
    [
        ("CANCELLED", -5, 5, None, "CANCELLED"),
        ("RESULTS_PUBLISHED", -5, 5, None, "RESULTS_PUBLISHED"),
        ("SCHEDULED", -5, 5, "IN_PROGRESS", "ATTEMPT_IN_PROGRESS"),
        ("SCHEDULED", -5, 5, "SUBMITTED", "SUBMITTED"),
        ("SCHEDULED", -5, 5, "AUTO_SUBMITTED", "RESULT_PENDING"),
        ("CLOSED", -5, 5, None, "RESULT_PENDING"),
        ("LIVE", -5, 5, None, "LIVE"),
        ("SCHEDULED", 10, 190, None, "STARTING_SOON"),
        ("SCHEDULED", 16, 196, None, "UPCOMING"),
        ("LIVE", -190, -10, "IN_PROGRESS", "RESULT_PENDING"),
    ],
)
def test_dashboard_lifecycle_uses_server_schedule_and_attempt_state(
    status, starts_offset, ends_offset, attempt_status, expected
):
    now = timezone.now()
    mock = SimpleNamespace(
        status=status,
        starts_at=now + timedelta(minutes=starts_offset),
        ends_at=now + timedelta(minutes=ends_offset),
    )
    info = {"attempt_status": attempt_status} if attempt_status else None
    assert dashboard_lifecycle(mock, info, now) == expected
