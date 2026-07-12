from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from transactions.models import FinancialIdempotencyKey


class Command(BaseCommand):
    help = "Remove stale financial idempotency keys older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete keys older than this many days (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many keys would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        qs = FinancialIdempotencyKey.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} idempotency key(s) older than {options['days']} days.")
            return
        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} stale idempotency key(s)."))
