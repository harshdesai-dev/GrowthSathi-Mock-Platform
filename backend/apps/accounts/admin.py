from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import StudentProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("email", "google_sub", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "google_sub", "password")}),
        ("Name", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "google_sub", "first_name", "last_name", "is_staff"),
            },
        ),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "class_level", "target_exam", "onboarding_completed")
    search_fields = ("user__email", "full_name", "phone")
    list_filter = ("class_level", "target_exam", "onboarding_completed")
