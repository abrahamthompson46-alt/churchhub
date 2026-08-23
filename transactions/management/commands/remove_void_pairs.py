"""Remove voided/reversed journals and legacy opposite-journal pairs for one church."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.db.models import Q

from organization.models import Church
from transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Delete reversed/voided transactions and legacy opposite-journal pairs "
        "for a church. Non-reversed journals are kept. Default is dry-run; "
        "pass --execute to delete."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--church",
            required=True,
            help='Church name (exact match preferred), e.g. "Bebianeha Maranatha"',
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete. Without this flag, only report what would be removed.",
        )

    def handle(self, *args, **options):
        name = (options["church"] or "").strip()
        if not name:
            raise CommandError("--church is required.")

        church = Church.objects.filter(name__iexact=name).first()
        if church is None:
            matches = list(Church.objects.filter(name__icontains=name).order_by("name")[:10])
            if len(matches) == 1:
                church = matches[0]
            elif not matches:
                raise CommandError(f'No church found matching "{name}".')
            else:
                names = ", ".join(f'"{c.name}"' for c in matches)
                raise CommandError(f'Multiple churches match "{name}": {names}. Use the exact name.')

        qs = Transaction.objects.filter(church=church).filter(
            Q(is_voided=True)
            | Q(approval_status="REVERSED")
            | Q(reversal_of__isnull=False)
            | Q(description__istartswith="VOID:")
        )
        delete_ids = list(qs.values_list("pk", flat=True))
        if not delete_ids:
            self.stdout.write(
                self.style.SUCCESS(
                    f'No reversed/voided journals for "{church.name}". Nothing to remove.'
                )
            )
            return

        to_delete = (
            Transaction.objects.filter(church=church, pk__in=delete_ids)
            .order_by("date", "created_at")
        )
        self.stdout.write(f'Church: {church.name} ({church.pk})')
        self.stdout.write(f"Total journals to remove: {to_delete.count()}")
        for txn in to_delete:
            if txn.is_voided or txn.approval_status == "REVERSED":
                kind = "REVERSED"
            elif txn.reversal_of_id or (txn.description or "").upper().startswith("VOID:"):
                kind = "LEGACY_OPPOSITE"
            else:
                kind = "OTHER"
            self.stdout.write(
                f"  - {txn.date} | {txn.reference} | {txn.transaction_type} | {kind}"
            )

        if not options["execute"]:
            self.stdout.write(
                self.style.WARNING("Dry-run only. Re-run with --execute to delete.")
            )
            return

        with db_transaction.atomic():
            try:
                from contributions.models import MemberContribution

                contrib_qs = MemberContribution.objects.filter(transaction_id__in=delete_ids)
                contrib_count = contrib_qs.count()
                if contrib_count:
                    contrib_qs.delete()
                    self.stdout.write(f"Removed {contrib_count} linked member contribution row(s).")
            except Exception as exc:
                raise CommandError(f"Could not clear contribution links: {exc}") from exc

            deleted_count, detail = Transaction.objects.filter(
                church=church, pk__in=delete_ids
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Removed reversed/voided journals for "{church.name}": '
                f"deleted {deleted_count} DB object(s). {detail}"
            )
        )
