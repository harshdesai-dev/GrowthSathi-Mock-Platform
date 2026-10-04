from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import StudentProfile, User
from apps.accounts.phone import normalize_indian_mobile


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
