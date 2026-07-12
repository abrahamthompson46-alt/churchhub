"""Expire due tenant subscriptions past their expires_at date."""

from django.core.management.base import BaseCommand

from sitecontrol.services import expire_due_subscriptions


class Command(BaseCommand):
    help = "Mark ACTIVE/TRIAL subscriptions past expires_at as EXPIRED."

    def handle(self, *args, **options):
        count = expire_due_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} subscription(s)."))
