from django.core.management.base import BaseCommand, CommandError

from apps.attempts.services import reconcile_expired


class Command(BaseCommand):
    help = "Idempotently auto-submit expired attempts using only backend-saved responses."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)

    def handle(self, *args, **options):
        if not 1 <= options["batch_size"] <= 1000:
            raise CommandError("Batch size must be between 1 and 1000.")
        count = reconcile_expired(batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"Reconciled {count} expired attempts."))
