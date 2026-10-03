"""Pure deterministic scoring: Decimal arithmetic, no clock, database or exam-name branch."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

METRICS = (
    "score",
    "correct_count",
    "incorrect_count",
    "attempted_count",
    "unattempted_count",
    "rank",
    "percentile",
)


def participant_reason(status, has_saved_response):
    """One central eligibility definition, including visited-but-blank saved rows."""
    if status == "SUBMITTED" or (status == "AUTO_SUBMITTED" and has_saved_response):
        return None
    return "No saved responses" if status == "AUTO_SUBMITTED" else f"Attempt is {status}"


def decimal(value):
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise ValueError("Scoring requires exact decimal text, not floating-point values.")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal in scoring input.") from exc
    if not result.is_finite():
        raise ValueError("Scoring values must be finite.")
    return result


def score_question(question, response=None):
    response = response or {}
    option, numeric = response.get("selected_option"), response.get("numeric_answer", "")
    if not option and numeric == "":
        return {"outcome": "Unattempted", "marks": decimal(question["unanswered_marks"])}
    if question["question_type"] == "MCQ_SINGLE":
        if numeric or option not in {item["id"] for item in question["options"]}:
            raise ValueError("Saved response has an invalid MCQ answer shape.")
        correct = option == question["correct_option"]
    elif question["question_type"] == "NUMERICAL":
        if option:
            raise ValueError("Numerical responses cannot contain an option.")
        with localcontext() as context:
            context.prec = 50
            # Absolute inclusive tolerance, without rounding either operand.
            correct = abs(
                decimal(numeric) - decimal(question["correct_numeric_answer"])
            ) <= decimal(question["numeric_tolerance"])
    else:
        raise ValueError("Unsupported configured question type.")
    return {
        "outcome": "Correct" if correct else "Incorrect",
        "marks": decimal(question["positive_marks"])
        if correct
        else -decimal(question["negative_marks"]),
    }


def score_attempt(questions, responses):
    if set(responses) - {question["id"] for question in questions}:
        raise ValueError("Saved response references a question outside this paper.")
    counts, total = Counter(), Decimal(0)
    with localcontext() as context:
        context.prec = 50
        for question in questions:
            outcome = score_question(question, responses.get(question["id"]))
            counts[outcome["outcome"]] += 1
            total += outcome["marks"]
    return {
        "score": total,
        "correct_count": counts["Correct"],
        "incorrect_count": counts["Incorrect"],
        "attempted_count": counts["Correct"] + counts["Incorrect"],
        "unattempted_count": counts["Unattempted"],
    }


def rank_scores(scores):
    """Competition rank and inclusive empirical mock percentile; no speed tie-break."""
    counts = Counter(scores)
    total, below, result = len(scores), 0, {}
    for score in sorted(counts):
        at_or_below = below + counts[score]
        with localcontext() as context:
            context.prec = 50
            percentile = (Decimal(100) * at_or_below / total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        result[score] = {"rank": 1 + total - at_or_below, "percentile": percentile}
        below = at_or_below
    return result
