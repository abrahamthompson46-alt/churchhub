from django.core.management.base import BaseCommand

from announcements.birthday_services import (
    DEFAULT_FLYER_RETENTION_DAYS,
    purge_old_birthday_flyers,
)


class Command(BaseCommand):
    help = (
        "Delete stored birthday flyer PNG files older than --days while keeping dispatch "
        "rows and posted status. Portraits should not live in MEDIA forever."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_FLYER_RETENTION_DAYS,
            help=f"Remove flyer files not updated in this many days (default {DEFAULT_FLYER_RETENTION_DAYS}).",
        )

    def handle(self, *args, **options):
        removed = purge_old_birthday_flyers(days=options["days"])
        self.stdout.write(self.style.SUCCESS(f"Flyer files removed: {removed}"))
