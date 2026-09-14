from django.core.management.base import BaseCommand

from announcements.birthday_services import remind_all_church_birthday_desks


class Command(BaseCommand):
    help = (
        "Notify church secretaries and local pastors when members have a birthday today "
        "so they can prepare WhatsApp-group flyers. Does not send to WhatsApp."
    )

    def handle(self, *args, **options):
        stats = remind_all_church_birthday_desks()
        self.stdout.write(
            self.style.SUCCESS(
                f"Churches notified: {stats['churches']}; "
                f"notifications: {stats['notifications']}"
            )
        )
