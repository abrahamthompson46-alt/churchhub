"""Remove voided originals and their linked reversal journals for one church.

User-approved corrective cleanup when accidental voids litter the books.
Keeps all non-voided transactions untouched.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.db.models import Q

from organization.models import Church
from transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Delete voided transactions and their reversal pairs for a church. "
        "Non-voided journals are kept. Use --execute to apply; default is dry-run."
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

        voided = list(
            Transaction.objects.filter(church=church, is_voided=True)
            .prefetch_related("reversals")
            .order_by("date", "created_at")
        )
        reversal_ids = set()
        for txn in voided:
            for rev in txn.reversals.all():
                reversal_ids.add(rev.pk)

        # Orphan reversals that still point at a voided original (already covered),
        # plus any reversal whose original was already missing.
        orphan_reversals = list(
            Transaction.objects.filter(church=church, reversal_of__isnull=False)
            .filter(Q(reversal_of__is_voided=True) | Q(pk__in=reversal_ids))
            .distinct()
        )
        for rev in orphan_reversals:
            reversal_ids.add(rev.pk)

        delete_ids = {t.pk for t in voided} | reversal_ids
        if not delete_ids:
            self.stdout.write(
                self.style.SUCCESS(
                    f'No void pairs for "{church.name}". Nothing to remove.'
                )
            )
            return

        to_delete = (
            Transaction.objects.filter(church=church, pk__in=delete_ids)
            .order_by("date", "created_at")
        )
        self.stdout.write(f'Church: {church.name} ({church.pk})')
        self.stdout.write(f"Voided originals: {len(voided)}")
        self.stdout.write(f"Reversals: {len(reversal_ids)}")
        self.stdout.write(f"Total journals to remove: {to_delete.count()}")
        for txn in to_delete:
            kind = "VOIDED" if txn.is_voided else ("REVERSAL" if txn.reversal_of_id else "OTHER")
            self.stdout.write(
                f"  - {txn.date} | {txn.reference} | {txn.transaction_type} | {kind}"
            )

        if not options["execute"]:
            self.stdout.write(
                self.style.WARNING("Dry-run only. Re-run with --execute to delete.")
            )
            return

        with db_transaction.atomic():
            # PROTECT: campaign contributions cannot leave dangling transaction FKs.
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
                f'Removed void pairs for "{church.name}": deleted {deleted_count} DB object(s). {detail}'
            )
        )
