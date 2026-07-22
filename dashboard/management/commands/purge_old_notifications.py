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
        result = repo.purge_aged_notifications(
            read_days=options["read_days"],
            unread_days=options["unread_days"],
            dry_run=options["dry_run"],
        )
        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {result} notification(s) "
                f"(read >{options['read_days']}d, unread >{options['unread_days']}d)."
            )
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {result} notification(s)."))
