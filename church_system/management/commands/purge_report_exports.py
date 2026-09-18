from django.core.management.base import BaseCommand

from reports.services import DEFAULT_EXPORT_RETENTION_DAYS, purge_old_export_files


class Command(BaseCommand):
    help = (
        "Delete stored report export files older than --days. Job and audit rows stay."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_EXPORT_RETENTION_DAYS,
            help=f"Remove files not updated in this many days (default {DEFAULT_EXPORT_RETENTION_DAYS}).",
        )

    def handle(self, *args, **options):
        removed = purge_old_export_files(days=options["days"])
        self.stdout.write(self.style.SUCCESS(f"Report export files removed: {removed}"))
