from django.core.management.base import BaseCommand

from announcements.birthday_services import remind_all_church_birthday_desks


class Command(BaseCommand):
    help = (
        "Notify church secretaries and local pastors of birthdays so they can prepare "
        "WhatsApp-group flyers. Does not send to WhatsApp. Schedule daily at 06:00 local "
        "time; optionally Friday evening with --days-ahead 1 for Sabbath prep."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=0,
            help="Also notify for birthdays this many days ahead (1 = tomorrow).",
        )

    def handle(self, *args, **options):
        stats = remind_all_church_birthday_desks(days_ahead=options["days_ahead"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Churches notified: {stats['churches']}; "
                f"notifications: {stats['notifications']}"
            )
        )
