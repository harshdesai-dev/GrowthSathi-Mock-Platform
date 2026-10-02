from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exams.models import ExamScheme, ExamType, SchemePhase, SchemeRule
from apps.exams.validation import validate_scheme


class Command(BaseCommand):
    help = "Seed SPEC baselines. These are NOT official 2027 rules; revalidate before every mock."

    @transaction.atomic
    def handle(self, *args, **options):
        definitions = (
            (
                "JEE_MAIN",
                "JEE Main",
                75,
                300,
                [("All subjects", 180, False, ("PHYSICS", "CHEMISTRY", "MATHEMATICS"))],
            ),
            (
                "MHT_CET_PCM",
                "MHT-CET PCM",
                150,
                200,
                [
                    ("Physics and Chemistry", 90, True, ("PHYSICS", "CHEMISTRY")),
                    ("Mathematics", 90, True, ("MATHEMATICS",)),
                ],
            ),
        )
        for code, name, count, marks, phases in definitions:
            exam, _ = ExamType.objects.get_or_create(code=code, defaults={"name": name})
            scheme, created = ExamScheme.objects.get_or_create(
                exam_type=exam,
                version="spec-v1.1-baseline",
                defaults={
                    "name": f"{name} SPEC baseline (revalidation required)",
                    "effective_from": date(2026, 10, 2),
                    "source_reference": (
                        "docs/SPEC.md v1.1 sections 9-10. Unverified seed baseline; "
                        "NOT an official 2027 claim. Admin must check latest NTA JEE Main / "
                        "Maharashtra CET Cell rules before each mock and record the "
                        "official source/edition/date."
                    ),
                    "total_duration_minutes": 180,
                    "maximum_marks": marks,
                    "total_question_count": count,
                },
            )
            if not created:
                if not validate_scheme(scheme).valid:
                    raise CommandError(
                        f"Existing {code} baseline is invalid; refusing to overwrite it."
                    )
                self.stdout.write(f"Unchanged: {scheme}")
                continue
            offset = 0
            for order, (phase_name, duration, locked, subjects) in enumerate(phases, 1):
                phase = SchemePhase.objects.create(
                    scheme=scheme,
                    name=phase_name,
                    order=order,
                    start_offset_minutes=offset,
                    duration_minutes=duration,
                    sequence_locked=locked,
                )
                offset += duration
                for subject in subjects:
                    kinds = (
                        [("MCQ_SINGLE", 20), ("NUMERICAL", 5)]
                        if code == "JEE_MAIN"
                        else [("MCQ_SINGLE", 50)]
                    )
                    for kind, question_count in kinds:
                        SchemeRule.objects.create(
                            phase=phase,
                            subject=subject,
                            question_type=kind,
                            question_count=question_count,
                            positive_marks=4
                            if code == "JEE_MAIN"
                            else (2 if subject == "MATHEMATICS" else 1),
                            negative_marks=1 if code == "JEE_MAIN" else 0,
                        )
            validate_scheme(scheme).require_valid()
            self.stdout.write(self.style.SUCCESS(f"Created: {scheme}"))
