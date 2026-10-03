from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path

from apps.commerce.admin import ReadOnlyAdmin
from apps.exams.models import MockTest
from apps.exams.services import require_owner

from .models import Result, ResultCalculationEntry, ResultCalculationRun
from .services import (
    calculate_results,
    publish_results,
    reconcile_for_results,
    verify_answer_key,
    withdraw_results,
)


class OperationsForm(forms.Form):
    operation = forms.ChoiceField(
        choices=[
            ("reconcile", "Reconcile expired attempts"),
            ("verify", "Verify answer key / prepare run"),
            ("calculate", "Calculate selected run"),
            ("publish", "Publish inspected run"),
            ("withdraw", "Withdraw published run for correction"),
        ]
    )
    run = forms.ModelChoiceField(queryset=ResultCalculationRun.objects.none(), required=False)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Required verification notes or withdrawal reason. "
        "Inspect the selected run before publishing.",
    )
    confirm = forms.BooleanField(
        label="I confirm this operation on this mock and selected generation."
    )

    def __init__(self, *args, mock, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["run"].queryset = mock.result_runs.all()

    def clean(self):
        data = super().clean()
        if data.get("operation") in {"calculate", "publish", "withdraw"} and not data.get("run"):
            self.add_error("run", "Select a calculation run.")
        return data


@admin.register(ResultCalculationRun)
class RunAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "mock_test",
        "status",
        "participant_count",
        "started_at",
        "completed_at",
        "published_at",
    )
    list_filter = ("status", "mock_test")
    list_select_related = ("mock_test",)

    def get_urls(self):
        return [
            path(
                "mock/<uuid:mock_id>/operations/",
                self.admin_site.admin_view(self.operations_view),
                name="results_operations",
            )
        ] + super().get_urls()

    def operations_view(self, request, mock_id):
        require_owner(request.user)
        mock = get_object_or_404(MockTest, pk=mock_id)
        form = OperationsForm(request.POST or None, mock=mock)
        outcome = None
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                operation = data["operation"]
                if operation == "reconcile":
                    outcome = reconcile_for_results(mock.pk, actor=request.user)
                elif operation == "verify":
                    verify_answer_key(mock.pk, actor=request.user, notes=data["notes"])
                elif operation == "withdraw":
                    withdraw_results(data["run"].pk, actor=request.user, reason=data["notes"])
                else:
                    {"calculate": calculate_results, "publish": publish_results}[operation](
                        data["run"].pk, actor=request.user
                    )
                if operation != "reconcile":
                    self.message_user(
                        request,
                        "Result operation completed. Inspect the generation below.",
                        messages.SUCCESS,
                    )
                    return HttpResponseRedirect(request.path)
            except ValidationError as exc:
                form.add_error(None, exc)
        return TemplateResponse(
            request,
            "admin/results/operations.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Result operations: {mock.title}",
                "mock": mock,
                "form": form,
                "outcome": outcome,
                "runs": mock.result_runs.all(),
            },
        )


@admin.register(ResultCalculationEntry)
class EntryAdmin(ReadOnlyAdmin):
    list_display = (
        "attempt",
        "calculation_run",
        "score",
        "rank",
        "percentile",
        "correct_count",
        "incorrect_count",
    )
    list_filter = ("calculation_run",)
    list_select_related = ("attempt", "calculation_run")


@admin.register(Result)
class ResultAdmin(ReadOnlyAdmin):
    list_display = ("attempt", "score", "rank", "percentile", "calculation_run", "published_at")
    list_filter = ("calculation_run",)
    list_select_related = ("attempt", "calculation_run")
