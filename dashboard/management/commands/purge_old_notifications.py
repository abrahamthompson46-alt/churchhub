"""Delete aged dashboard notifications to keep the inbox lean."""

from django.core.management.base import BaseCommand

from dashboard import repositories as repo


class Command(BaseCommand):
    help = (
        "Purge old notifications: read older than 90 days, "
        "and unread older than 180 days."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--read-days",
            type=int,
            default=None,
            help="Delete read notifications older than this many days (default: institution setting or 90).",
        )
        parser.add_argument(
            "--unread-days",
            type=int,
            default=None,
            help="Delete unread notifications older than this many days (default: institution setting or 180).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many notifications would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        read_days = options["read_days"]
        unread_days = options["unread_days"]
        if read_days is None or unread_days is None:
            from sitecontrol.models import Denomination

            denomination = Denomination.get_default()
            if read_days is None:
                read_days = getattr(denomination, "notification_retention_read_days", 90) if denomination else 90
            if unread_days is None:
                unread_days = getattr(denomination, "notification_retention_unread_days", 180) if denomination else 180
        result = repo.purge_aged_notifications(
            read_days=read_days,
            unread_days=unread_days,
            dry_run=options["dry_run"],
        )
        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {result} notification(s) "
                f"(read >{options['read_days']}d, unread >{options['unread_days']}d)."
            )
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {result} notification(s)."))
