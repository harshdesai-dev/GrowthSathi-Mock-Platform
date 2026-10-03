"""Auditable calculation snapshots and one current published Result per attempt."""

import uuid
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.exams.models import GuardedQuerySet

service_write = ContextVar("result_service_write", default=False)


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not service_write.get():
            raise ValidationError("Results are writable only through result operations.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Result history cannot be deleted.")


class ResultCalculationRun(Record):
    class Status(models.TextChoices):
        VERIFIED = "VERIFIED"
        CALCULATING = "CALCULATING"
        COMPLETE = "COMPLETE"
        PUBLISHED = "PUBLISHED"
        INVALIDATED = "INVALIDATED"
        WITHDRAWN = "WITHDRAWN"
        FAILED = "FAILED"

    mock_test = models.ForeignKey(
        "exams.MockTest", on_delete=models.PROTECT, related_name="result_runs"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="result_runs"
    )
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    key_verified_at = models.DateTimeField()
    source_revision = models.CharField(max_length=64)
    input_digest = models.CharField(max_length=64, blank=True)
    output_digest = models.CharField(max_length=64, blank=True)
    scorer_version = models.CharField(max_length=30, default="decimal-v1")
    paper_snapshot = models.JSONField()
    participant_count = models.PositiveIntegerField(default=0)
    excluded_attempts = models.JSONField(default=list)
    notes = models.TextField()
    errors = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="published_result_runs",
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="withdrawn_result_runs",
    )
    withdrawal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "VERIFIED",
                        "CALCULATING",
                        "COMPLETE",
                        "PUBLISHED",
                        "INVALIDATED",
                        "WITHDRAWN",
                        "FAILED",
                    ]
                ),
                name="result_run_status_valid",
            ),
            models.UniqueConstraint(
                fields=["mock_test"],
                condition=models.Q(status__in=["VERIFIED", "CALCULATING", "COMPLETE"]),
                name="one_current_result_draft",
            ),
            models.UniqueConstraint(
                fields=["mock_test"],
                condition=models.Q(status="PUBLISHED"),
                name="one_published_result_run",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="PUBLISHED")
                | models.Q(
                    published_at__isnull=False,
                    published_by__isnull=False,
                    completed_at__isnull=False,
                ),
                name="published_run_has_audit",
            ),
        ]

    def __str__(self):
        return f"{self.pk}: {self.status}"


class Metrics(Record):
    score = models.DecimalField(max_digits=18, decimal_places=2)
    correct_count = models.PositiveIntegerField()
    incorrect_count = models.PositiveIntegerField()
    attempted_count = models.PositiveIntegerField()
    unattempted_count = models.PositiveIntegerField()
    rank = models.PositiveIntegerField()
    percentile = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(condition=models.Q(rank__gte=1), name="%(class)s_rank_positive"),
            models.CheckConstraint(
                condition=models.Q(percentile__gte=0, percentile__lte=100),
                name="%(class)s_percentile_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    attempted_count=models.F("correct_count") + models.F("incorrect_count")
                ),
                name="%(class)s_counts_consistent",
            ),
        ]


class ResultCalculationEntry(Metrics):
    """Immutable batch member; retained even when a newer run is published."""

    calculation_run = models.ForeignKey(
        ResultCalculationRun, on_delete=models.PROTECT, related_name="entries"
    )
    attempt = models.ForeignKey(
        "attempts.Attempt", on_delete=models.PROTECT, related_name="result_entries"
    )
    response_snapshot = models.JSONField()

    class Meta(Metrics.Meta):
        abstract = False
        constraints = Metrics.Meta.constraints + [
            models.UniqueConstraint(
                fields=["calculation_run", "attempt"], name="one_entry_per_run_attempt"
            )
        ]
        indexes = [models.Index(fields=["calculation_run", "rank"])]

    def __str__(self):
        return f"{self.calculation_run_id}: {self.attempt_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Calculation entries are immutable.")
        return super().save(*args, **kwargs)


class Result(Metrics):
    attempt = models.OneToOneField(
        "attempts.Attempt", on_delete=models.PROTECT, related_name="result"
    )
    calculation_run = models.ForeignKey(
        ResultCalculationRun, on_delete=models.PROTECT, related_name="results"
    )
    entry = models.OneToOneField(
        ResultCalculationEntry, on_delete=models.PROTECT, related_name="current_result"
    )
    published_at = models.DateTimeField()

    def __str__(self):
        return f"{self.attempt_id}: {self.score}"
