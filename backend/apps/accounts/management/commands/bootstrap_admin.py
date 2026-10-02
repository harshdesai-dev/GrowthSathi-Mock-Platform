from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create or safely promote the initial Google-authenticated platform owner."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--google-sub", required=True)
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        email = options["email"].strip().lower()
        google_sub = options["google_sub"].strip()
        if not email or not google_sub:
            raise CommandError("Both --email and --google-sub must be non-empty.")

        by_email = User.objects.select_for_update().filter(email=email).first()
        by_sub = User.objects.select_for_update().filter(google_sub=google_sub).first()
        if by_email and by_sub and by_email.pk != by_sub.pk:
            raise CommandError(
                "Email and Google subject belong to different users; no changes made."
            )
        user = by_email or by_sub
        if user and (user.email != email or user.google_sub != google_sub):
            raise CommandError(
                "The supplied identity conflicts with an existing user; no changes made."
            )

        if user is None:
            user = User.objects.create_superuser(
                email=email,
                google_sub=google_sub,
                first_name=options["first_name"].strip(),
                last_name=options["last_name"].strip(),
            )
            action = "Created"
        else:
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            if options["first_name"]:
                user.first_name = options["first_name"].strip()
            if options["last_name"]:
                user.last_name = options["last_name"].strip()
            user.save()
            action = "Promoted"

        self.stdout.write(self.style.SUCCESS(f"{action} platform owner {user.email}."))
