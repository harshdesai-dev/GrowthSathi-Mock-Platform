"""Read-only operational mock queries for the owner dashboard."""

from django.db.models import Case, Count, DateTimeField, F, IntegerField, Prefetch, When

from apps.exams.models import MockPhase, MockTest, SchemePhase


def _mock_queryset():
    return (
        MockTest.objects.select_related("exam_type", "exam_scheme")
        .defer("description", "instructions_md", "rules_source_notes")
        .annotate(question_count=Count("questions", distinct=True))
    )


def owner_mock_list_queryset(*, status="", exam_type="", search="", now):
    queryset = _mock_queryset()
    if status:
        queryset = queryset.filter(status=status)
    if exam_type:
        queryset = queryset.filter(exam_type__code=exam_type)
    if search:
        queryset = queryset.filter(title__icontains=search)

    return queryset.annotate(
        _schedule_group=Case(
            When(starts_at__gt=now, then=0),
            default=1,
            output_field=IntegerField(),
        ),
        _future_start=Case(
            When(starts_at__gt=now, then=F("starts_at")),
            output_field=DateTimeField(),
        ),
        _past_start=Case(
            When(starts_at__lte=now, then=F("starts_at")),
            output_field=DateTimeField(),
        ),
    ).order_by(
        "_schedule_group",
        "_future_start",
        F("_past_start").desc(nulls_last=True),
        "title",
        "pk",
    )


def owner_mock_detail_queryset():
    phases = (
        MockPhase.objects.select_related("scheme_phase")
        .annotate(question_count=Count("questions"))
        .order_by("order")
    )
    scheme_phases = SchemePhase.objects.order_by("order")
    return _mock_queryset().prefetch_related(
        Prefetch("phases", queryset=phases),
        Prefetch("exam_scheme__phases", queryset=scheme_phases),
    )
