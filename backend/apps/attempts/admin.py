from django.contrib import admin

from apps.commerce.admin import ReadOnlyAdmin

from .models import Attempt, StudentResponse
from .services import reconcile_expired


@admin.register(Attempt)
class AttemptAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "student",
        "mock_test",
        "status",
        "started_at",
        "submitted_at",
        "last_heartbeat_at",
    )
    list_filter = ("status", "mock_test", "started_at")
    search_fields = ("id", "student__email")

    def get_queryset(self, request):
        # Stored status can lag while nobody is connected; Admin must not display
        # an expired attempt as active. Use the same idempotent domain operation.
        reconcile_expired()
        return super().get_queryset(request).select_related("student", "mock_test")


@admin.register(StudentResponse)
class ResponseAdmin(ReadOnlyAdmin):
    list_display = ("attempt", "question_id", "mutation_version", "marked_for_review", "updated_at")
    list_filter = ("attempt__mock_test", "marked_for_review")
    search_fields = ("attempt__id",)
