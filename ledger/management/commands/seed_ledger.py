from django.core.management.base import BaseCommand

from ledger.services import seed_ledger
from organization.models import Church


class Command(BaseCommand):
    help = "Seed ledger accounts and posting categories for all churches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing ledger categories before re-seeding.",
        )
        parser.add_argument(
            "--church",
            type=str,
            help="Church code to seed (default: all churches).",
        )

    def handle(self, *args, **options):
        churches = Church.objects.all()
        if options["church"]:
            churches = churches.filter(code=options["church"])
        if not churches.exists():
            self.stderr.write("No churches found.")
            return

        for church in churches:
            seed_ledger(church, reset=options["reset"])
            count = church.ledger_categories.filter(is_active=True).count()
            self.stdout.write(
                self.style.SUCCESS(f"{church.code}: {count} ledger categories seeded.")
            )
