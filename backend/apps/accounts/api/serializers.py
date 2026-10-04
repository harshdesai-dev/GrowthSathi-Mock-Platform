from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import StudentProfile, User
from apps.accounts.phone import normalize_indian_mobile
from apps.exams.models import ExamScheme, ExamType, MockTest
from apps.exams.services import create_draft_mock, update_draft_mock


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
    exam_type_id = serializers.UUIDField(read_only=True)
    exam_scheme_id = serializers.UUIDField(read_only=True)
    rules_source_notes = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    instructions_md = serializers.CharField(read_only=True)
    phases = OwnerMockPhaseSerializer(many=True, read_only=True)
    operational_warnings = serializers.SerializerMethodField()

    class Meta(OwnerMockSummarySerializer.Meta):
        fields = OwnerMockSummarySerializer.Meta.fields + (
            "exam_type_id",
            "exam_scheme_id",
            "rules_source_notes",
            "description",
            "instructions_md",
            "phases",
            "operational_warnings",
        )

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


class OwnerMockOptionExamTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamType
        fields = ("id", "code", "name", "active")


class OwnerMockOptionExamSchemeSerializer(serializers.ModelSerializer):
    exam_type_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ExamScheme
        fields = (
            "id",
            "exam_type_id",
            "name",
            "version",
            "active",
            "total_question_count",
            "total_duration_minutes",
            "maximum_marks",
        )


class OwnerMockOptionsSerializer(serializers.Serializer):
    exam_types = OwnerMockOptionExamTypeSerializer(many=True)
    exam_schemes = OwnerMockOptionExamSchemeSerializer(many=True)


class OwnerMockWriteSerializer(serializers.ModelSerializer):
    exam_type = serializers.PrimaryKeyRelatedField(queryset=ExamType.objects.all())
    exam_scheme = serializers.PrimaryKeyRelatedField(queryset=ExamScheme.objects.all())
    starts_at = serializers.DateTimeField(default_timezone=ZoneInfo("Asia/Kolkata"))
    ends_at = serializers.DateTimeField(default_timezone=ZoneInfo("Asia/Kolkata"))
    result_release_at = serializers.DateTimeField(default_timezone=ZoneInfo("Asia/Kolkata"))
    price_paise = serializers.IntegerField()

    class Meta:
        model = MockTest
        fields = (
            "exam_type",
            "exam_scheme",
            "title",
            "slug",
            "description",
            "starts_at",
            "ends_at",
            "result_release_at",
            "price_paise",
            "instructions_md",
        )

    def validate(self, attrs):
        allowed_fields = set(self.fields)
        unexpected = set(self.initial_data) - allowed_fields
        if unexpected:
            raise serializers.ValidationError(
                {
                    field: "This field cannot be set through the owner draft API."
                    for field in sorted(unexpected)
                }
            )

        exam_type = attrs.get("exam_type", getattr(self.instance, "exam_type", None))
        exam_scheme = attrs.get("exam_scheme", getattr(self.instance, "exam_scheme", None))
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        release_at = attrs.get(
            "result_release_at", getattr(self.instance, "result_release_at", None)
        )
        price_paise = attrs.get("price_paise", getattr(self.instance, "price_paise", None))
        if exam_type and exam_scheme and starts_at and ends_at and release_at:
            candidate = MockTest(
                exam_type=exam_type,
                exam_scheme=exam_scheme,
                title=attrs.get("title", getattr(self.instance, "title", "")),
                slug=attrs.get("slug", getattr(self.instance, "slug", "")),
                starts_at=starts_at,
                ends_at=ends_at,
                result_release_at=release_at,
                price_paise=price_paise,
                status=MockTest.Status.DRAFT,
            )
            try:
                candidate.clean()
            except DjangoValidationError as exc:
                self._raise_domain_validation(exc)
        return attrs

    @staticmethod
    def _raise_domain_validation(exc: DjangoValidationError):
        if hasattr(exc, "message_dict"):
            raise serializers.ValidationError(exc.message_dict) from exc
        raise serializers.ValidationError({"non_field_errors": exc.messages}) from exc

    def create(self, validated_data):
        try:
            return create_draft_mock(**validated_data)
        except DjangoValidationError as exc:
            self._raise_domain_validation(exc)

    def update(self, instance, validated_data):
        try:
            return update_draft_mock(instance.pk, **validated_data)
        except DjangoValidationError as exc:
            self._raise_domain_validation(exc)


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
