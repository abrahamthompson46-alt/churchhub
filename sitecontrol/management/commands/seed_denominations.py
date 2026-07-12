"""Seed and sync built-in denomination deployment profiles."""

from django.core.management.base import BaseCommand

from sitecontrol.denomination_services import assign_orphan_conferences_to_default, ensure_builtin_denominations


class Command(BaseCommand):
    help = "Create or update built-in denomination profiles (SDA, Methodist, CoP, generic)."

    def handle(self, *args, **options):
        created = ensure_builtin_denominations()
        assigned = assign_orphan_conferences_to_default()
        self.stdout.write(
            self.style.SUCCESS(
                f"Denominations synced. New: {len(created)}, orphan conferences assigned: {assigned}"
            )
        )
