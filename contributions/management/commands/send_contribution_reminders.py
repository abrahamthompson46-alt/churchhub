from django.core.management.base import BaseCommand

from contributions.reminder_services import send_all_deadline_reminders


class Command(BaseCommand):
    help = "Send contribution campaign deadline reminders (in-app and optional email)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-email",
            action="store_true",
            help="Skip email reminders; send in-app notifications only.",
        )

    def handle(self, *args, **options):
        stats = send_all_deadline_reminders(include_email=not options["no_email"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Campaigns scanned: {stats['campaigns']}; "
                f"notifications: {stats['notifications']}; emails: {stats['emails']}"
            )
        )
