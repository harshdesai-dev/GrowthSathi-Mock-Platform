from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .imports import commit_import, preview_import, template_bytes
from .models import (
    AnswerKeyAuditEvent,
    ExamScheme,
    ExamType,
    MockPhase,
    MockTest,
    Question,
    QuestionOption,
    SchemePhase,
    SchemeRule,
)
from .services import (
    TRANSITIONS,
    correct_answer_key,
    generate_phases,
    require_owner,
    transition_mock,
    verify_official_rules,
)
from .validation import validate_answers, validate_paper, validate_scheme


class OwnerAdmin(admin.ModelAdmin):
    actions = None
    readonly_fields = ("created_at", "updated_at")
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)
            return HttpResponseRedirect(request.path)


class ProtectedInline(admin.TabularInline):
    extra = 0
    can_delete = True
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}

    def has_add_permission(self, request, obj):
        return request.user.is_superuser and not self.is_locked(obj)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and not self.is_locked(obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and not self.is_locked(obj)

    def is_locked(self, obj):
        return False


class SchemePhaseInline(ProtectedInline):
    model = SchemePhase
    show_change_link = True

    def is_locked(self, obj):
        return obj and (obj.locked or obj.mocks.exists())


class SchemeRuleInline(ProtectedInline):
    model = SchemeRule

    def is_locked(self, obj):
        return obj and (obj.scheme.locked or obj.scheme.mocks.exists())


@admin.register(ExamType)
class ExamTypeAdmin(OwnerAdmin):
    list_display = ("code", "name", "active")
    search_fields = ("code", "name")


@admin.register(ExamScheme)
class ExamSchemeAdmin(OwnerAdmin):
    list_display = ("exam_type", "version", "name", "active", "locked", "scheme_validation")
    list_filter = ("exam_type", "active", "locked")
    search_fields = ("name", "version")
    list_select_related = ("exam_type",)
    inlines = (SchemePhaseInline,)

    def scheme_validation(self, obj):
        return validate_scheme(obj).status

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (
            obj and (obj.locked or obj.mocks.exists())
        )


@admin.register(SchemePhase)
class SchemePhaseAdmin(OwnerAdmin):
    list_display = ("scheme", "name", "order", "duration_minutes", "sequence_locked")
    list_filter = ("scheme__exam_type", "scheme")
    list_select_related = ("scheme__exam_type",)
    inlines = (SchemeRuleInline,)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (
            obj and (obj.scheme.locked or obj.scheme.mocks.exists())
        )


class MockOperationsForm(forms.Form):
    operation = forms.ChoiceField(
        choices=[
            ("validate", "Validate paper"),
            ("verify", "Record latest official-rule verification"),
            ("phases", "Generate missing scheme phases"),
        ]
        + [(v, f"Transition to {v}") for v in MockTest.Status.values if v != "DRAFT"]
    )
    source_notes = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text=(
            "For verification: official source URL, edition/date "
            "and checks performed for this mock."
        ),
    )


class UploadForm(forms.Form):
    file = forms.FileField()


class ConfirmImportForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    confirm = forms.BooleanField(label="I reviewed this preview and confirm the atomic import")


class CorrectionForm(forms.Form):
    correct_option = forms.ChoiceField(
        required=False, choices=[("", "Numerical question")] + [(v, v) for v in "ABCD"]
    )
    numeric_answer = forms.DecimalField(required=False, max_digits=20, decimal_places=8)
    numeric_tolerance = forms.DecimalField(
        required=False, min_value=0, max_digits=20, decimal_places=8
    )
    reason = forms.CharField(widget=forms.Textarea)


@admin.register(MockTest)
class MockTestAdmin(OwnerAdmin):
    list_display = (
        "title",
        "exam_type",
        "exam_scheme",
        "starts_at",
        "status",
        "operations_link",
        "import_link",
        "results_link",
    )
    list_filter = ("exam_type", "status")
    search_fields = ("title", "slug")
    list_select_related = ("exam_type", "exam_scheme__exam_type")
    readonly_fields = OwnerAdmin.readonly_fields + (
        "status",
        "rules_verified_at",
        "rules_verified_by",
        "rules_source_notes",
        "operations_link",
        "import_link",
        "results_link",
    )

    def results_link(self, obj):
        if obj and not obj._state.adding:
            return format_html(
                '<a href="{}">Result operations</a>',
                reverse("admin:results_operations", args=[obj.pk]),
            )
        return "Save the draft first."

    def operations_link(self, obj):
        if obj and not obj._state.adding:
            return format_html(
                '<a href="{}">Validate / verify rules / transition</a>',
                reverse("admin:exams_mock_operations", args=[obj.pk]),
            )
        return "Save the draft first."

    def import_link(self, obj):
        if obj and not obj._state.adding:
            return format_html(
                '<a href="{}">Import questions</a>',
                reverse("admin:exams_mock_import", args=[obj.pk]),
            )
        return "Save the draft first."

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (obj and obj.status != "DRAFT")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            generate_phases(obj)

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/operations/",
                self.admin_site.admin_view(self.operations_view),
                name="exams_mock_operations",
            ),
            path(
                "<uuid:object_id>/import/",
                self.admin_site.admin_view(self.import_view),
                name="exams_mock_import",
            ),
            path(
                "template/<str:format>/",
                self.admin_site.admin_view(self.template_view),
                name="exams_import_template",
            ),
        ] + super().get_urls()

    def operations_view(self, request, object_id):
        require_owner(request.user)
        mock = get_object_or_404(MockTest, pk=object_id)
        form = MockOperationsForm(request.POST or None)
        result = None
        if request.method == "POST" and form.is_valid():
            operation = form.cleaned_data["operation"]
            try:
                if operation == "validate":
                    result = validate_paper(mock)
                elif operation == "verify":
                    verify_official_rules(
                        mock.pk, actor=request.user, source_notes=form.cleaned_data["source_notes"]
                    )
                elif operation == "phases":
                    generate_phases(mock)
                else:
                    transition_mock(mock.pk, operation, actor=request.user)
                if operation != "validate":
                    self.message_user(request, "Operation completed.", messages.SUCCESS)
                    return HttpResponseRedirect(request.path)
            except ValidationError as exc:
                form.add_error(None, exc)
        return TemplateResponse(
            request,
            "admin/exams/operations.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Manage {mock.title}",
                "mock": mock,
                "form": form,
                "result": result,
                "transitions": sorted(TRANSITIONS[mock.status]),
            },
        )

    def import_view(self, request, object_id):
        require_owner(request.user)
        mock = get_object_or_404(MockTest, pk=object_id)
        preview = None
        confirmation = None
        upload_form = UploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and "token" in request.POST:
            confirmation = ConfirmImportForm(request.POST)
            if confirmation.is_valid():
                try:
                    count = commit_import(
                        mock.pk, confirmation.cleaned_data["token"], actor=request.user
                    )
                    self.message_user(
                        request, f"Imported {count} questions atomically.", messages.SUCCESS
                    )
                    return HttpResponseRedirect(
                        reverse("admin:exams_mocktest_change", args=[mock.pk])
                    )
                except ValidationError as exc:
                    confirmation.add_error(None, exc)
        elif request.method == "POST" and upload_form.is_valid():
            preview = preview_import(mock.pk, upload_form.cleaned_data["file"], actor=request.user)
            if preview.valid:
                confirmation = ConfirmImportForm(initial={"token": preview.token})
        return TemplateResponse(
            request,
            "admin/exams/import.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Import into {mock.title}",
                "upload_form": upload_form,
                "preview": preview,
                "confirmation": confirmation,
            },
        )

    def template_view(self, request, format):
        require_owner(request.user)
        if format not in {"csv", "xlsx"}:
            from django.http import Http404

            raise Http404
        response = HttpResponse(
            template_bytes(format),
            content_type="text/csv"
            if format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="question-import.{format}"'
        return response


@admin.register(MockPhase)
class MockPhaseAdmin(OwnerAdmin):
    list_display = (
        "mock_test",
        "name",
        "order",
        "start_offset_minutes",
        "duration_minutes",
        "sequence_locked",
    )
    list_filter = ("mock_test",)
    list_select_related = ("mock_test", "scheme_phase")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OptionFormSet(forms.models.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        options = []
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                options.append(form.instance)
        errors = validate_answers(self.instance, options)
        if errors:
            raise ValidationError(errors)


class OptionInline(ProtectedInline):
    model = QuestionOption
    formset = OptionFormSet
    extra = 4
    max_num = 4

    def is_locked(self, obj):
        return obj and (obj.status == "LOCKED" or obj.mock_test.status != "DRAFT")


@admin.register(Question)
class QuestionAdmin(OwnerAdmin):
    list_display = (
        "question_number",
        "mock_test",
        "phase",
        "subject",
        "question_type",
        "status",
        "correction_link",
    )
    list_filter = (
        "mock_test__exam_type",
        "mock_test",
        "phase",
        "subject",
        "question_type",
        "status",
    )
    search_fields = ("question_text_md", "mock_test__title")
    list_select_related = ("mock_test", "phase")
    inlines = (OptionInline,)
    readonly_fields = OwnerAdmin.readonly_fields + ("correction_link",)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request) and bool(
            obj and obj.mock_test.status == "DRAFT" and obj.status != "LOCKED"
        )

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (
            obj and (obj.mock_test.status != "DRAFT" or obj.status == "LOCKED")
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "status" in form.base_fields:
            form.base_fields["status"].choices = [("DRAFT", "DRAFT"), ("READY", "READY")]
        return form

    def correction_link(self, obj):
        if obj and not obj._state.adding and obj.mock_test.status == "CLOSED":
            return format_html(
                '<a href="{}">Correct answer key with audit reason</a>',
                reverse("admin:exams_question_correct", args=[obj.pk]),
            )
        return "Available after exam close."

    def get_urls(self):
        return [
            path(
                "<uuid:object_id>/correct/",
                self.admin_site.admin_view(self.correction_view),
                name="exams_question_correct",
            )
        ] + super().get_urls()

    def correction_view(self, request, object_id):
        require_owner(request.user)
        question = get_object_or_404(Question, pk=object_id)
        form = CorrectionForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            values = form.cleaned_data
            try:
                correct_answer_key(
                    question.pk,
                    actor=request.user,
                    reason=values["reason"],
                    correct_option=values["correct_option"] or None,
                    numeric_answer=values["numeric_answer"],
                    numeric_tolerance=values["numeric_tolerance"],
                )
                self.message_user(
                    request,
                    "Answer key corrected and audited. Any draft was invalidated; "
                    "verify and recalculate results.",
                    messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    reverse("admin:exams_question_change", args=[question.pk])
                )
            except ValidationError as exc:
                form.add_error(None, exc)
        return TemplateResponse(
            request,
            "admin/exams/correction.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": f"Correct {question}",
                "form": form,
            },
        )


@admin.register(AnswerKeyAuditEvent)
class AnswerKeyAuditAdmin(OwnerAdmin):
    list_display = (
        "question",
        "changed_by",
        "created_at",
        "field_changed",
        "old_value",
        "new_value",
    )
    list_filter = ("field_changed", "question__mock_test")
    list_select_related = ("question__mock_test", "changed_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
