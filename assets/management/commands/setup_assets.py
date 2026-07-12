"""Backfill asset categories, policies, and GL accounts for existing churches."""

from django.core.management.base import BaseCommand

from assets.services import ensure_asset_defaults_for_church
from organization.models import Church
from transactions.services import create_default_accounts


class Command(BaseCommand):
    help = "Seed asset categories, depreciation policies, and GL accounts for all churches."

    def handle(self, *args, **options):
        for church in Church.objects.all():
            create_default_accounts(church)
            ensure_asset_defaults_for_church(church)
            self.stdout.write(f"Seeded assets for {church.code}")
