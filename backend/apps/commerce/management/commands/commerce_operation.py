"""Explicit owner-operated reconciliation; no automatic refunds or gateway writes."""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.commerce.services import reconcile_gateway_order, record_manual_refund, revoke_access


class Command(BaseCommand):
    help = "Record an already verified full-order refund, revoke access, or link a gateway receipt."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["link-order", "record-refund", "revoke-access"])
        parser.add_argument("record_id")
        parser.add_argument("--owner", required=True, help="Active superuser email")
        parser.add_argument("--reference", default="")
        parser.add_argument("--reason", default="")

    def handle(self, *args, **options):
        try:
            actor = User.objects.get(email=options["owner"])
            record_id = options["record_id"]
            if options["operation"] == "link-order":
                result = reconcile_gateway_order(record_id, options["reference"], actor=actor)
            elif options["operation"] == "record-refund":
                result = record_manual_refund(
                    record_id, actor=actor, reason=options["reason"], reference=options["reference"]
                )
            else:
                result = revoke_access(record_id, actor=actor, note=options["reason"])
        except Exception as exc:
            raise CommandError(
                "Operation rejected; check owner, record state and verified reference."
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Recorded {options['operation']}: {result.pk}"))
