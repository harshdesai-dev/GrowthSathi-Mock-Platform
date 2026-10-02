import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from .phone import normalize_indian_mobile


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    def _create_user(self, email: str, google_sub: str, **extra_fields):
        if not email:
            raise ValueError("The email address is required.")
        if not google_sub:
            raise ValueError("The Google subject is required.")
        user = self.model(
            email=self._normalize_email(email),
            google_sub=google_sub.strip(),
            **extra_fields,
        )
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, google_sub: str, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, google_sub, **extra_fields)

    def create_superuser(self, email: str, google_sub: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self._create_user(email, google_sub, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    google_sub = models.CharField(max_length=255, unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["google_sub"]

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs) -> None:
        self.email = UserManager._normalize_email(self.email)
        self.google_sub = self.google_sub.strip()
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()

    def get_short_name(self) -> str:
        return self.first_name or self.email

    def __str__(self) -> str:
        return self.email


class StudentProfile(models.Model):
    class ClassLevel(models.TextChoices):
        ELEVENTH = "11", "11th"
        TWELFTH = "12", "12th"
        DROPPER = "DROPPER", "Dropper"

    class TargetExam(models.TextChoices):
        JEE = "JEE", "JEE"
        CET = "CET", "MHT-CET"
        BOTH = "BOTH", "Both"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=13, blank=True)
    class_level = models.CharField(max_length=7, choices=ClassLevel.choices, blank=True)
    target_exam = models.CharField(max_length=4, choices=TargetExam.choices, blank=True)
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile for {self.user.email}"

    def save(self, *args, **kwargs) -> None:
        if self.phone:
            self.phone = normalize_indian_mobile(self.phone)
        super().save(*args, **kwargs)
