import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, models, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.accounts.models import User
from apps.exams.imports import COLUMNS, SALT, commit_import, preview_import, template_bytes
from apps.exams.models import (
    AnswerKeyAuditEvent,
    ExamScheme,
    ExamType,
    MockTest,
    Question,
    QuestionOption,
    SchemePhase,
    SchemeRule,
)
from apps.exams.services import (
    correct_answer_key,
    generate_phases,
    transition_mock,
    verify_official_rules,
)
from apps.exams.validation import validate_paper, validate_scheme

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_superuser(email="exam-owner@example.com", google_sub="exam-owner")


@pytest.fixture
def schemes():
    call_command("seed_exam_schemes", stdout=io.StringIO())
    return {s.exam_type.code: s for s in ExamScheme.objects.select_related("exam_type")}


def make_mock(scheme, slug="sample"):
    start = timezone.now() + timedelta(days=2)
    mock = MockTest.objects.create(
        exam_type=scheme.exam_type,
        exam_scheme=scheme,
        title="Sample mock",
        slug=slug,
        starts_at=start,
        ends_at=start + timedelta(minutes=180),
        result_release_at=start + timedelta(minutes=190),
    )
    generate_phases(mock)
    return mock


@pytest.fixture
def mock(schemes):
    return make_mock(schemes["JEE_MAIN"])


def paper_rows(mock):
    rows = []
    for phase in mock.phases.select_related("scheme_phase"):
        for rule in phase.scheme_phase.rules.order_by("subject", "question_type"):
            for _ in range(rule.question_count):
                number = len(rows) + 1
                row = dict.fromkeys(COLUMNS, "")
                row.update(
                    question_number=str(number),
                    phase=str(phase.order),
                    subject=rule.subject,
                    question_type=rule.question_type,
                    question_text_md=f"Question {number}: solve $x+1=2$.",
                    positive_marks=str(rule.positive_marks),
                    negative_marks=str(rule.negative_marks),
                    numeric_tolerance="0",
                    explanation_md="Subtract one: $x=1$.",
                )
                if rule.question_type == "MCQ_SINGLE":
                    row.update(
                        option_a="1", option_b="2", option_c="3", option_d="4", correct_option="A"
                    )
                else:
                    row["numeric_answer"] = "1"
                rows.append(row)
    return rows


def upload(rows, format="csv"):
    if format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append([row.get(c, "") for c in COLUMNS])
        stream = io.BytesIO()
        workbook.save(stream)
        data = stream.getvalue()
    else:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        data = stream.getvalue().encode()
    return SimpleUploadedFile(f"paper.{format}", data)


def populate(mock, owner):
    preview = preview_import(mock.pk, upload(paper_rows(mock)), actor=owner)
    assert preview.errors == []
    commit_import(mock.pk, preview.token, actor=owner)


def verify(mock, owner):
    verify_official_rules(
        mock.pk,
        actor=owner,
        source_notes="Test-only verification fixture, not a real official-rule review.",
    )


def close_mock(mock, owner):
    populate(mock, owner)
    verify(mock, owner)
    for status in ("SCHEDULED", "LIVE", "CLOSED"):
        transition_mock(mock.pk, status, actor=owner)
    mock.refresh_from_db()


def corrupt(instance, **values):
    """Simulate legacy/broken DB data to prove validation derives every result."""
    models.QuerySet.update(type(instance).objects.filter(pk=instance.pk), **values)


@pytest.mark.parametrize(
    "code,count,marks,phases", [("JEE_MAIN", 75, 300, 1), ("MHT_CET_PCM", 150, 200, 2)]
)
def test_seed_scheme_valid(schemes, code, count, marks, phases):
    scheme = schemes[code]
    assert validate_scheme(scheme).valid
    assert scheme.total_question_count == count
    assert scheme.maximum_marks == marks
    assert scheme.phases.count() == phases
    assert "NOT an official 2027" in scheme.source_reference


def test_seed_is_idempotent(schemes):
    before = list(ExamScheme.objects.values_list("pk", "updated_at"))
    call_command("seed_exam_schemes", stdout=io.StringIO())
    assert list(ExamScheme.objects.values_list("pk", "updated_at")) == before
    assert ExamType.objects.count() == 2
    assert SchemePhase.objects.count() == 3
    assert SchemeRule.objects.count() == 9


def test_scheme_version_unique(schemes):
    scheme = schemes["JEE_MAIN"]
    clone = ExamScheme(
        exam_type=scheme.exam_type,
        version=scheme.version,
        name="Duplicate",
        effective_from=scheme.effective_from,
        source_reference="test",
        total_duration_minutes=180,
        maximum_marks=300,
        total_question_count=75,
    )
    with pytest.raises(ValidationError):
        clone.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        models.Model.save(clone, force_insert=True)


def test_scheme_and_children_immutable_even_for_draft(mock):
    scheme = mock.exam_scheme
    scheme.maximum_marks = 500
    with pytest.raises(ValidationError, match="immutable"):
        scheme.save()
    rule = scheme.phases.first().rules.first()
    rule.positive_marks = 5
    with pytest.raises(ValidationError, match="immutable"):
        rule.save()
    with pytest.raises(ValidationError, match="immutable"):
        rule.delete()
    phase = scheme.phases.first()
    phase.duration_minutes = 120
    with pytest.raises(ValidationError, match="immutable"):
        phase.save()
    with pytest.raises(ValidationError):
        ExamScheme.objects.filter(pk=scheme.pk).update(maximum_marks=500)
    scheme.refresh_from_db()
    assert scheme.maximum_marks == 300


@pytest.mark.parametrize(
    "field,value",
    [("total_question_count", 76), ("maximum_marks", 301), ("total_duration_minutes", 170)],
)
def test_invalid_scheme_totals(schemes, field, value):
    scheme = schemes["JEE_MAIN"]
    setattr(scheme, field, value)
    scheme.save()
    assert not validate_scheme(scheme).valid


def test_invalid_rule_rejected(schemes):
    rule = schemes["JEE_MAIN"].phases.first().rules.first()
    rule.negative_marks = -1
    with pytest.raises(ValidationError):
        rule.save()


@pytest.mark.parametrize("field", ["exam_type", "ends_at", "result_release_at"])
def test_mock_configuration_rejected(schemes, field):
    scheme = schemes["JEE_MAIN"]
    start = timezone.now()
    values = dict(
        exam_type=scheme.exam_type,
        exam_scheme=scheme,
        title="bad",
        slug="bad",
        starts_at=start,
        ends_at=start + timedelta(hours=3),
        result_release_at=start + timedelta(hours=4),
    )
    values[field] = (
        schemes["MHT_CET_PCM"].exam_type if field == "exam_type" else start - timedelta(minutes=1)
    )
    with pytest.raises(ValidationError):
        MockTest.objects.create(**values)


def test_phases_generated_from_scheme(schemes):
    jee = make_mock(schemes["JEE_MAIN"], "jee")
    cet = make_mock(schemes["MHT_CET_PCM"], "cet")
    assert list(jee.phases.values_list("order", "start_offset_minutes", "duration_minutes")) == [
        (1, 0, 180)
    ]
    assert list(
        cet.phases.values_list(
            "order", "start_offset_minutes", "duration_minutes", "sequence_locked"
        )
    ) == [(1, 0, 90, True), (2, 90, 90, True)]
    generate_phases(cet)
    assert cet.phases.count() == 2


@pytest.mark.parametrize(
    "field,value", [("order", 2), ("duration_minutes", 90), ("start_offset_minutes", 90)]
)
def test_phase_edits_must_match_scheme(mock, field, value):
    phase = mock.phases.first()
    setattr(phase, field, value)
    with pytest.raises(ValidationError):
        phase.save()


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_valid_preview_never_persists(mock, owner, format):
    preview = preview_import(mock.pk, upload(paper_rows(mock), format), actor=owner)
    assert preview.valid and preview.token and not preview.warnings
    assert Question.objects.count() == 0
    assert QuestionOption.objects.count() == 0


@pytest.mark.parametrize("code", ["JEE_MAIN", "MHT_CET_PCM"])
def test_full_import_and_complete_paper(schemes, owner, code):
    mock = make_mock(schemes[code])
    populate(mock, owner)
    result = validate_paper(mock)
    assert result.errors == []
    assert mock.questions.count() == mock.exam_scheme.total_question_count
    assert QuestionOption.objects.count() == (240 if code == "JEE_MAIN" else 600)


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"question_number": ""}, "Question number"),
        ({"subject": "BIOLOGY"}, "Row 2"),
        ({"phase": "9"}, "phase"),
        ({"question_type": "MULTIPLE"}, "Row 2"),
        ({"correct_option": ""}, "correct_option"),
        ({"correct_option": "E"}, "correct_option"),
        ({"correct_option": "A,B"}, "correct_option"),
        ({"option_d": ""}, "Option text"),
        ({"positive_marks": "3"}, "Marks"),
        ({"negative_marks": "0"}, "Marks"),
        ({"numeric_answer": "1"}, "MCQ"),
        ({"numeric_tolerance": "-1"}, "Row 2"),
        ({"positive_marks": "NaN"}, "finite"),
        ({"question_text_md": ""}, "blank"),
        ({"explanation_md": ""}, "explanation"),
    ],
)
def test_invalid_import_reports_row(mock, owner, changes, expected):
    rows = paper_rows(mock)[:1]
    rows[0].update(changes)
    result = preview_import(mock.pk, upload(rows), actor=owner)
    assert not result.valid and not result.token
    assert all(error.startswith("Row 2:") for error in result.errors)
    assert expected.lower() in " ".join(result.errors).lower()


@pytest.mark.parametrize(
    "changes", [{"numeric_answer": ""}, {"correct_option": "A"}, {"option_a": "1"}]
)
def test_invalid_numerical_rows(mock, owner, changes):
    row = next(r for r in paper_rows(mock) if r["question_type"] == "NUMERICAL")
    row.update(changes)
    result = preview_import(mock.pk, upload([row]), actor=owner)
    assert not result.valid


@pytest.mark.parametrize("duplicate", ["question_number", "question_text_md"])
def test_duplicate_import_rejected(mock, owner, duplicate):
    rows = paper_rows(mock)[:2]
    rows[1][duplicate] = rows[0][duplicate]
    result = preview_import(mock.pk, upload(rows), actor=owner)
    assert not result.valid
    assert "Row 3" in " ".join(result.errors)


@pytest.mark.parametrize("data", [b"bad,header\n1,2", (",".join(COLUMNS) + "\n1,2\n").encode()])
def test_malformed_csv(mock, owner, data):
    result = preview_import(mock.pk, SimpleUploadedFile("bad.csv", data), actor=owner)
    assert not result.valid


def test_xlsx_formula_rejected(mock, owner):
    rows = paper_rows(mock)[:1]
    rows[0]["option_a"] = "=1+1"
    result = preview_import(mock.pk, upload(rows, "xlsx"), actor=owner)
    assert not result.valid and "Row 2" in result.errors[0]


def test_cet_subject_phase_mismatch(schemes, owner):
    mock = make_mock(schemes["MHT_CET_PCM"])
    rows = paper_rows(mock)[:1]
    rows[0]["subject"] = "MATHEMATICS"
    assert not preview_import(mock.pk, upload(rows), actor=owner).valid


def test_import_exceeding_subject_count(mock, owner):
    rows = paper_rows(mock)
    rows[20] = {**rows[0], "question_number": "21", "question_text_md": "Extra MCQ"}
    result = preview_import(mock.pk, upload(rows), actor=owner)
    assert any("exceeds" in error for error in result.errors)


def test_failed_insert_rolls_back_every_question(mock, owner, monkeypatch):
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:2]), actor=owner)

    def fail_after_question_insert(options):
        assert Question.objects.count() == 2
        raise ValidationError("Simulated insertion failure")

    monkeypatch.setattr("apps.exams.imports._insert_options", fail_after_question_insert)
    with pytest.raises(ValidationError):
        commit_import(mock.pk, preview.token, actor=owner)
    assert Question.objects.count() == QuestionOption.objects.count() == 0


def test_commit_revalidates_and_prevents_replay(mock, owner):
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:1]), actor=owner)
    assert commit_import(mock.pk, preview.token, actor=owner) == 1
    with pytest.raises(ValidationError):
        commit_import(mock.pk, preview.token, actor=owner)
    assert mock.questions.count() == 1


def test_tampered_or_wrong_mock_preview_rejected(mock, owner, schemes):
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:1]), actor=owner)
    with pytest.raises(ValidationError):
        commit_import(mock.pk, preview.token + "x", actor=owner)
    other = make_mock(schemes["JEE_MAIN"], "other")
    with pytest.raises(ValidationError):
        commit_import(other.pk, preview.token, actor=owner)
    assert Question.objects.count() == 0


@pytest.mark.parametrize(
    "mutation",
    ["missing", "excess", "subject", "type", "answer", "marks", "explanation", "duration", "phase"],
)
def test_paper_validator_detects_invalid_stored_data(mock, owner, mutation):
    populate(mock, owner)
    q = mock.questions.first()
    if mutation == "missing":
        q.delete()
    elif mutation == "excess":
        q.pk = None
        q.id = __import__("uuid").uuid4()
        q._state.adding = True
        q.question_number = 76
        q.save()
    elif mutation == "answer":
        corrupt(q.options.get(is_correct=True), is_correct=False)
    elif mutation == "duration":
        corrupt(mock, ends_at=mock.ends_at - timedelta(minutes=1))
        mock.refresh_from_db()
    elif mutation == "phase":
        corrupt(mock.phases.first(), duration_minutes=10)
    else:
        values = {
            "subject": {"subject": "PHYSICS"},
            "type": {"question_type": "NUMERICAL", "correct_numeric_answer": Decimal(1)},
            "marks": {"positive_marks": 3},
            "explanation": {"explanation_md": ""},
        }
        corrupt(q, **values[mutation])
    assert not validate_paper(mock).valid


@pytest.mark.parametrize("correct_count", [0, 2])
def test_mcq_zero_or_multiple_correct_rejected(mock, owner, correct_count):
    populate(mock, owner)
    q = mock.questions.filter(question_type="MCQ_SINGLE").first()
    for index, option in enumerate(q.options.all()):
        corrupt(option, is_correct=index < correct_count)
    assert any("exactly one" in error for error in validate_paper(mock).errors)


def test_operational_transitions_validate_and_freeze(mock, owner):
    with pytest.raises(ValidationError):
        transition_mock(mock.pk, "SCHEDULED", actor=owner)
    populate(mock, owner)
    with pytest.raises(ValidationError, match="official"):
        transition_mock(mock.pk, "SCHEDULED", actor=owner)
    verify(mock, owner)
    for status in ("REGISTRATION_OPEN", "SCHEDULED", "LIVE", "CLOSED"):
        transition_mock(mock.pk, status, actor=owner)
    mock.refresh_from_db()
    assert mock.status == "CLOSED"
    assert not mock.questions.exclude(status="LOCKED").exists()
    q = mock.questions.first()
    q.question_text_md = "Changed"
    with pytest.raises(ValidationError):
        q.save()
    rule = mock.exam_scheme.phases.first().rules.first()
    with pytest.raises(ValidationError):
        rule.delete()
    with pytest.raises(ValidationError):
        transition_mock(mock.pk, "RESULTS_PUBLISHED", actor=owner)


def test_illegal_and_direct_status_changes_rejected(mock, owner):
    with pytest.raises(ValidationError, match="Illegal"):
        transition_mock(mock.pk, "LIVE", actor=owner)
    mock.status = "SCHEDULED"
    with pytest.raises(ValidationError, match="transition"):
        mock.save()
    with pytest.raises(ValidationError):
        MockTest.objects.filter(pk=mock.pk).update(status="LIVE")


def test_cancel_draft(mock, owner):
    result = transition_mock(mock.pk, "CANCELLED", actor=owner)
    assert result.status == "CANCELLED"
    with pytest.raises(ValidationError):
        transition_mock(mock.pk, "DRAFT", actor=owner)


def test_answer_key_correction_audited(mock, owner):
    close_mock(mock, owner)
    q = mock.questions.filter(question_type="MCQ_SINGLE").first()
    correct_answer_key(q.pk, actor=owner, reason="Verified solution shows B", correct_option="B")
    assert q.options.get(is_correct=True).label == "B"
    event = AnswerKeyAuditEvent.objects.get(question=q)
    assert (event.old_value, event.new_value, event.changed_by) == ("A", "B", owner)
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(ValidationError):
        event.save()


def test_numeric_key_correction_and_tolerance_audited(mock, owner):
    close_mock(mock, owner)
    q = mock.questions.filter(question_type="NUMERICAL").first()
    correct_answer_key(
        q.pk,
        actor=owner,
        reason="Corrected verified key",
        numeric_answer=Decimal("2.5"),
        numeric_tolerance=Decimal("0.01"),
    )
    q.refresh_from_db()
    assert q.correct_numeric_answer == Decimal("2.5")
    assert q.answer_key_audit.count() == 2


def test_unauthorized_correction_and_import_rejected(mock, owner):
    populate(mock, owner)
    student = User.objects.create_user(email="student@example.com", google_sub="student")
    q = mock.questions.first()
    with pytest.raises(PermissionDenied):
        correct_answer_key(q.pk, actor=student, reason="attempt", correct_option="B")
    with pytest.raises(PermissionDenied):
        preview_import(mock.pk, upload(paper_rows(mock)), actor=student)
    with pytest.raises(PermissionDenied):
        transition_mock(mock.pk, "CANCELLED", actor=student)
    with pytest.raises(ValidationError):
        correct_answer_key(q.pk, actor=owner, reason="too early", correct_option="B")
    assert AnswerKeyAuditEvent.objects.count() == 0


def test_admin_workflows_require_owner_and_render(client, mock, owner):
    url = reverse("admin:exams_mock_import", args=[mock.pk])
    assert client.get(url).status_code == 302
    client.force_login(owner)
    assert client.get(url).status_code == 200
    for format in ("csv", "xlsx"):
        response = client.get(reverse("admin:exams_import_template", args=[format]))
        assert response.status_code == 200
        assert (
            response.content == template_bytes(format)
            if format == "csv"
            else response.content[:2] == b"PK"
        )
    response = client.post(url, {"file": upload(paper_rows(mock)[:1])})
    assert response.status_code == 200 and response.context["preview"].valid
    token = response.context["preview"].token
    assert Question.objects.count() == 0
    assert client.post(url, {"token": token, "confirm": "on"}).status_code == 302
    assert mock.questions.count() == 1
    url = reverse("admin:exams_mock_operations", args=[mock.pk])
    response = client.post(url, {"operation": "validate"})
    assert response.context["result"].status == "INVALID"
    assert client.get(reverse("admin:exams_question_changelist")).status_code == 200


def test_admin_manual_mcq_inline_validation(client, mock, owner):
    client.force_login(owner)
    phase = mock.phases.first()
    data = {
        "mock_test": str(mock.pk),
        "phase": str(phase.pk),
        "subject": "PHYSICS",
        "question_number": "1",
        "question_type": "MCQ_SINGLE",
        "question_text_md": "Manual question",
        "positive_marks": "4",
        "negative_marks": "1",
        "numeric_tolerance": "0",
        "explanation_md": "Explanation",
        "status": "READY",
        "options-TOTAL_FORMS": "4",
        "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "0",
        "options-MAX_NUM_FORMS": "4",
        "_save": "Save",
    }
    for index, label in enumerate("ABCD"):
        data.update(
            {
                f"options-{index}-label": label,
                f"options-{index}-order": str(index + 1),
                f"options-{index}-option_text_md": label,
            }
        )
    url = reverse("admin:exams_question_add")
    response = client.post(url, data)
    assert response.status_code == 200
    assert Question.objects.count() == 0
    assert b"exactly one correct" in response.content
    data["options-0-is_correct"] = "on"
    response = client.post(url, data)
    assert response.status_code == 302
    assert Question.objects.count() == 1
    assert QuestionOption.objects.count() == 4


def test_preview_expiry(mock, owner, monkeypatch):
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:1]), actor=owner)
    payload = signing.loads(preview.token, salt=SALT)
    assert payload["actor"] == str(owner.pk)
    monkeypatch.setattr("django.core.signing.time.time", lambda: timezone.now().timestamp() + 1801)
    with pytest.raises(ValidationError, match="expired"):
        commit_import(mock.pk, preview.token, actor=owner)


def test_full_cet_validation_and_preview_avoid_n_plus_one(schemes, owner):
    mock = make_mock(schemes["MHT_CET_PCM"])
    file = upload(paper_rows(mock), "xlsx")
    with CaptureQueriesContext(connection) as queries:
        preview = preview_import(mock.pk, file, actor=owner)
    assert preview.valid and len(queries) < 25
    commit_import(mock.pk, preview.token, actor=owner)
    with CaptureQueriesContext(connection) as queries:
        assert validate_paper(mock).valid
    assert len(queries) < 60


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_imports_serialize(schemes, owner):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency integration test")
    mock = make_mock(schemes["JEE_MAIN"])
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:1]), actor=owner)

    def run():
        close_old_connections()
        try:
            return commit_import(mock.pk, preview.token, actor=owner)
        except ValidationError:
            return "duplicate rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert sorted(results, key=str) == [1, "duplicate rejected"]
    assert mock.questions.count() == 1
    assert QuestionOption.objects.count() == 4


def test_admin_manual_numerical_question(client, mock, owner):
    client.force_login(owner)
    data = {
        "mock_test": str(mock.pk),
        "phase": str(mock.phases.first().pk),
        "subject": "PHYSICS",
        "question_number": "1",
        "question_type": "NUMERICAL",
        "question_text_md": "Solve $x=2$",
        "positive_marks": "4",
        "negative_marks": "1",
        "correct_numeric_answer": "2",
        "numeric_tolerance": "0",
        "explanation_md": "Given",
        "status": "READY",
        "options-TOTAL_FORMS": "0",
        "options-INITIAL_FORMS": "0",
        "options-MIN_NUM_FORMS": "0",
        "options-MAX_NUM_FORMS": "4",
        "_save": "Save",
    }
    response = client.post(reverse("admin:exams_question_add"), data)
    assert response.status_code == 302
    assert Question.objects.get().correct_numeric_answer == 2
    assert QuestionOption.objects.count() == 0


def test_admin_csrf_and_non_owner_staff_rejected(mock, owner):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    url = reverse("admin:exams_mock_operations", args=[mock.pk])
    assert client.post(url, {"operation": "CANCELLED"}).status_code == 403
    staff = User.objects.create_user(email="staff@example.com", google_sub="staff", is_staff=True)
    client.force_login(staff)
    assert client.get(url).status_code == 403
    assert client.get(reverse("admin:exams_import_template", args=["csv"])).status_code == 403


def test_invalid_signed_batch_commit_has_no_partial_rows(mock, owner):
    rows = paper_rows(mock)[:2]
    rows[1]["correct_option"] = "A,B"
    # Signed by a trusted older producer: commit must still validate every row.
    token = signing.dumps(
        {
            "mock": str(mock.pk),
            "actor": str(owner.pk),
            "rows": [{"row": i, "values": row} for i, row in enumerate(rows, 2)],
        },
        salt=SALT,
    )
    with pytest.raises(ValidationError, match="Row 3"):
        commit_import(mock.pk, token, actor=owner)
    assert Question.objects.count() == QuestionOption.objects.count() == 0


def test_correction_requires_reason_and_valid_shape(mock, owner):
    close_mock(mock, owner)
    q = mock.questions.filter(question_type="MCQ_SINGLE").first()
    for reason, option in [("", "B"), ("Review", None), ("Review", "AB")]:
        with pytest.raises(ValidationError):
            correct_answer_key(q.pk, actor=owner, reason=reason, correct_option=option)
    assert AnswerKeyAuditEvent.objects.count() == 0
    assert q.options.get(is_correct=True).label == "A"


def test_malformed_rows_all_reported(mock, owner):
    data = (",".join(COLUMNS) + "\n1,2\n3,4\n").encode()
    result = preview_import(mock.pk, SimpleUploadedFile("bad.csv", data), actor=owner)
    assert len(result.errors) == 2
    assert result.errors[0].startswith("Row 2:")
    assert result.errors[1].startswith("Row 3:")


def test_malformed_xlsx_returns_validation_error(mock, owner):
    result = preview_import(mock.pk, SimpleUploadedFile("bad.xlsx", b"invalid zip"), actor=owner)
    assert not result.valid


def test_owner_can_remove_draft_question_through_admin(client, mock, owner):
    preview = preview_import(mock.pk, upload(paper_rows(mock)[:1]), actor=owner)
    commit_import(mock.pk, preview.token, actor=owner)
    question = mock.questions.get()
    client.force_login(owner)
    url = reverse("admin:exams_question_delete", args=[question.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"post": "yes"}).status_code == 302
    assert Question.objects.count() == QuestionOption.objects.count() == 0


def test_paper_without_scheme_is_invalid():
    assert validate_paper(MockTest()).status == "INVALID"
