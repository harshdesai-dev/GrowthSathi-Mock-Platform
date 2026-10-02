import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Set or reset the internal Django Admin password for the bootstrapped owner."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--google-sub", required=True)
        parser.add_argument(
            "--password-env",
            help="Read the password from this environment variable instead of prompting.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        email = options["email"].strip().lower()
        google_sub = options["google_sub"].strip()
        user = User.objects.select_for_update().filter(email=email, google_sub=google_sub).first()
        if user is None:
            raise CommandError("No user matches the supplied email and Google subject.")
        if not user.is_active or not user.is_staff or not user.is_superuser:
            raise CommandError(
                "Only an active, explicitly bootstrapped staff superuser may receive an admin "
                "password."
            )

        password_env = options.get("password_env")
        if password_env:
            password = os.getenv(password_env, "")
            if not password:
                raise CommandError(f"Environment variable {password_env!r} is empty or missing.")
        else:
            password = getpass.getpass("Admin password: ")
            confirmation = getpass.getpass("Admin password (again): ")
            if password != confirmation:
                raise CommandError("Passwords do not match; no changes made.")

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Updated Django Admin password for {user.email}."))
