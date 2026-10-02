from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import ExamScheme, MockTest, Question, QuestionOption, QuestionType, SchemeRule


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        return "VALID" if self.valid else "INVALID"

    def require_valid(self) -> None:
        if self.errors:
            raise ValidationError(self.errors)


def validate_scheme(scheme: ExamScheme) -> ValidationResult:
    result = ValidationResult()
    phases = list(scheme.phases.prefetch_related("rules").all())
    if not phases:
        result.errors.append("Scheme has no phases.")
    offset, count, marks = 0, 0, Decimal(0)
    subjects = set()
    for index, phase in enumerate(phases, 1):
        if phase.order != index or phase.start_offset_minutes != offset:
            result.errors.append("Scheme phases must be contiguous and ordered from 1, offset 0.")
        offset += phase.duration_minutes
        rules = list(phase.rules.all())
        if not rules:
            result.errors.append(f"Phase {phase.order} has no subject rules.")
        phase_subjects = {r.subject for r in rules}
        if subjects & phase_subjects:
            result.errors.append("A subject must belong to exactly one scheme phase.")
        subjects.update(phase_subjects)
        for rule in rules:
            try:
                rule.clean_fields(exclude=["phase"])
                if rule.unanswered_marks != 0:
                    raise ValidationError("Unanswered marks must be zero.")
            except ValidationError as exc:
                result.errors.extend(exc.messages)
            count += rule.question_count
            marks += rule.question_count * rule.positive_marks
    if offset != scheme.total_duration_minutes:
        result.errors.append("Phase durations do not equal scheme duration.")
    if count != scheme.total_question_count:
        result.errors.append("Rule question counts do not equal scheme total.")
    if marks != scheme.maximum_marks:
        result.errors.append("Rule marks do not equal scheme maximum marks.")
    return result


def validate_answers(question: Question, options: list[QuestionOption]) -> list[str]:
    errors = []
    for option in options:
        try:
            option.clean_fields(exclude=["question"])
        except ValidationError as exc:
            errors.extend(exc.messages)
    if question.question_type == QuestionType.MCQ_SINGLE:
        if len(options) != 4 or {o.label for o in options} != set("ABCD"):
            errors.append("MCQ requires exactly four options labelled A, B, C, D.")
        if sum(bool(o.is_correct) for o in options) != 1:
            errors.append("MCQ must have exactly one correct option.")
        if len({o.order for o in options}) != len(options):
            errors.append("Option order must be unique.")
        if any(not o.option_text_md.strip() and not o.option_image_url for o in options):
            errors.append("Every option needs text or an image.")
    elif options or question.correct_numeric_answer is None:
        errors.append("Numerical questions require an answer and no options.")
    return errors


def validate_question_data(question: Question, rule: SchemeRule | None) -> list[str]:
    """Pure row validation shared by paper checks and import; no per-question queries."""
    errors = []
    try:
        question.clean_fields(exclude=["mock_test", "phase"])
    except ValidationError as exc:
        errors.extend(exc.messages)
    if rule is None:
        errors.append("Subject/question type is not allowed in this phase.")
    elif (question.positive_marks, question.negative_marks) != (
        rule.positive_marks,
        rule.negative_marks,
    ):
        errors.append("Marks must match the scheme rule.")
    if question.question_type == QuestionType.NUMERICAL:
        if question.correct_numeric_answer is None:
            errors.append("Numerical answer is required.")
    elif question.correct_numeric_answer is not None or question.numeric_tolerance != 0:
        errors.append("MCQ cannot have numerical answer/tolerance fields.")
    if not question.question_text_md.strip():
        errors.append("Question text cannot be blank.")
    if not question.explanation_md.strip():
        errors.append("An explanation is required.")
    return errors


def validate_paper(mock: MockTest) -> ValidationResult:
    """Derive validity on demand, never trust a stored flag or a previous preview."""
    if not mock.exam_scheme_id:
        return ValidationResult(errors=["An exam scheme is required."])
    result = validate_scheme(mock.exam_scheme)
    try:
        mock.full_clean()
    except ValidationError as exc:
        result.errors.extend(exc.messages)
    if mock.ends_at - mock.starts_at != timedelta(minutes=mock.exam_scheme.total_duration_minutes):
        result.errors.append("Mock duration must exactly match the scheme duration.")
    actual_phases = list(mock.phases.select_related("scheme_phase").all())
    expected_phases = list(mock.exam_scheme.phases.prefetch_related("rules").all())
    if [p.scheme_phase_id for p in actual_phases] != [p.pk for p in expected_phases]:
        result.errors.append("Mock phases/order do not match the scheme.")
    for phase in actual_phases:
        try:
            phase.full_clean()
        except ValidationError as exc:
            result.errors.extend(exc.messages)
    questions = list(
        mock.questions.select_related("phase__scheme_phase", "mock_test")
        .prefetch_related("options")
        .all()
    )
    expected_count = mock.exam_scheme.total_question_count
    if len(questions) != expected_count:
        result.errors.append(f"Expected {expected_count} questions; found {len(questions)}.")
    if [q.question_number for q in questions] != list(range(1, expected_count + 1)):
        result.errors.append("Question numbers must be contiguous from 1 to the scheme total.")
    rules = {
        (r.phase_id, r.subject, r.question_type): r for p in expected_phases for r in p.rules.all()
    }
    expected = {key: rule.question_count for key, rule in rules.items()}
    actual = Counter((q.phase.scheme_phase_id, q.subject, q.question_type) for q in questions)
    if dict(actual) != expected:
        result.errors.append("Subject/type/phase question counts do not match scheme rules.")
    for q in questions:
        rule = rules.get((q.phase.scheme_phase_id, q.subject, q.question_type))
        result.errors.extend(f"Q{q.question_number}: {m}" for m in validate_question_data(q, rule))
        if q.phase.mock_test_id != mock.pk:
            result.errors.append(f"Q{q.question_number}: phase belongs to another mock.")
        result.errors.extend(
            f"Q{q.question_number}: {m}" for m in validate_answers(q, list(q.options.all()))
        )
    if sum((q.positive_marks for q in questions), Decimal(0)) != mock.exam_scheme.maximum_marks:
        result.errors.append("Paper maximum marks do not match the scheme.")
    return result
