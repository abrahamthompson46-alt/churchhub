"""Delete aged dashboard notifications to keep the inbox lean."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from dashboard.models import Notification


class Command(BaseCommand):
    help = (
        "Purge old notifications: read older than 90 days, "
        "and unread older than 180 days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--read-days",
            type=int,
            default=90,
            help="Delete read notifications older than this many days (default: 90).",
        )
        parser.add_argument(
            "--unread-days",
            type=int,
            default=180,
            help="Delete unread notifications older than this many days (default: 180).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many notifications would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        read_cutoff = now - timedelta(days=options["read_days"])
        unread_cutoff = now - timedelta(days=options["unread_days"])
        qs = Notification.objects.filter(
            Q(read=True, created_at__lt=read_cutoff)
            | Q(read=False, created_at__lt=unread_cutoff)
        )
        count = qs.count()
        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {count} notification(s) "
                f"(read >{options['read_days']}d, unread >{options['unread_days']}d)."
            )
            return
        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} notification(s)."))
