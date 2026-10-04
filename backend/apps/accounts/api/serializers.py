from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import StudentProfile, User
from apps.accounts.phone import normalize_indian_mobile
from apps.exams.models import MockTest


class GoogleAuthSerializer(serializers.Serializer):
    credential = serializers.CharField(trim_whitespace=True, max_length=16384)


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    onboarding_completed = serializers.BooleanField(source="profile.onboarding_completed")

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "onboarding_completed",
            "is_staff",
            "is_superuser",
        )

    def get_full_name(self, obj: User) -> str:
        return obj.profile.full_name or obj.get_full_name()


class SessionSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    user = MeSerializer()


class RefreshSessionSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()


class OwnerAccessSerializer(serializers.Serializer):
    is_owner = serializers.BooleanField()


class OwnerOverviewSerializer(serializers.Serializer):
    total_students = serializers.IntegerField(min_value=0)
    upcoming_mocks = serializers.IntegerField(min_value=0)
    completed_mocks = serializers.IntegerField(min_value=0)
    paid_orders = serializers.IntegerField(min_value=0)
    failed_payments = serializers.IntegerField(min_value=0)
    total_revenue_paise = serializers.IntegerField(min_value=0)


class OwnerMockFiltersSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=MockTest.Status.choices, required=False)
    exam_type = serializers.CharField(required=False, allow_blank=True, max_length=40)
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=200,
    )


class OwnerMockExamTypeSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    active = serializers.BooleanField()


class OwnerMockExamSchemeSerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    active = serializers.BooleanField()
    total_question_count = serializers.IntegerField()
    total_duration_minutes = serializers.IntegerField()
    maximum_marks = serializers.IntegerField()


class OwnerMockPhaseSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    name = serializers.CharField()
    start_offset_minutes = serializers.IntegerField()
    duration_minutes = serializers.IntegerField()
    sequence_locked = serializers.BooleanField()
    question_count = serializers.IntegerField()


class OwnerMockSummarySerializer(serializers.ModelSerializer):
    exam_type = OwnerMockExamTypeSerializer(read_only=True)
    exam_scheme = OwnerMockExamSchemeSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = MockTest
        fields = (
            "id",
            "title",
            "slug",
            "exam_type",
            "exam_scheme",
            "status",
            "status_label",
            "starts_at",
            "ends_at",
            "result_release_at",
            "price_paise",
            "rules_verified_at",
            "question_count",
        )


class OwnerMockDetailSerializer(OwnerMockSummarySerializer):
    phases = OwnerMockPhaseSerializer(many=True, read_only=True)
    operational_warnings = serializers.SerializerMethodField()

    class Meta(OwnerMockSummarySerializer.Meta):
        fields = OwnerMockSummarySerializer.Meta.fields + ("phases", "operational_warnings")

    def get_operational_warnings(self, obj: MockTest) -> list[str]:
        warnings = []
        if not obj.rules_verified_at:
            warnings.append("Official rules have not been verified for this mock.")
        if not obj.exam_type.active:
            warnings.append("The mock's exam type is inactive.")
        if not obj.exam_scheme.active:
            warnings.append("The mock's exam scheme is inactive.")
        if obj.question_count != obj.exam_scheme.total_question_count:
            warnings.append(
                "The stored question count differs from the exam scheme's expected total."
            )

        actual_scheme_phase_ids = [phase.scheme_phase_id for phase in obj.phases.all()]
        expected_scheme_phase_ids = [phase.pk for phase in obj.exam_scheme.phases.all()]
        if actual_scheme_phase_ids != expected_scheme_phase_ids:
            warnings.append("Generated mock phases do not match the exam scheme phases.")
        return warnings


class OwnerMockListResponseSerializer(serializers.Serializer):
    results = OwnerMockSummarySerializer(many=True)


class CsrfTokenSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class StudentProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = StudentProfile
        fields = (
            "full_name",
            "email",
            "phone",
            "class_level",
            "target_exam",
            "onboarding_completed",
        )
        read_only_fields = ("email", "onboarding_completed")

    def validate_full_name(self, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Full name is required.")
        return value

    def validate_phone(self, value: str) -> str:
        try:
            return normalize_indian_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate(self, attrs):
        if self.instance and not self.instance.onboarding_completed:
            required = ("full_name", "phone", "class_level", "target_exam")
            missing = {
                field: ["This field is required to complete onboarding."]
                for field in required
                if not attrs.get(field, getattr(self.instance, field, ""))
            }
            if missing:
                raise serializers.ValidationError(missing)
        return attrs

    def update(self, instance: StudentProfile, validated_data):
        profile = super().update(instance, validated_data)
        if not profile.onboarding_completed:
            profile.onboarding_completed = True
            profile.save(update_fields=["onboarding_completed", "updated_at"])
        return profile
