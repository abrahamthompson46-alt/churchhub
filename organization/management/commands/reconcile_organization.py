from django.core.management.base import BaseCommand

from organization.services import reconcile_organization


class Command(BaseCommand):
    help = "Report organization integrity issues (missing subscriptions, unprovisioned churches, orphan conferences)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--denomination-id",
            dest="denomination_id",
            help="Optional denomination UUID to scope the reconciliation.",
        )

    def handle(self, *args, **options):
        denomination = None
        if options.get("denomination_id"):
            from sitecontrol.models import Denomination

            denomination = Denomination.objects.filter(pk=options["denomination_id"]).first()
            if not denomination:
                self.stderr.write("Denomination not found.")
                return

        issues = reconcile_organization(denomination=denomination)
        if not issues:
            self.stdout.write(self.style.SUCCESS("No organization issues found."))
            return

        for issue in issues:
            self.stdout.write(f"[{issue['kind']}] {issue}")
        self.stdout.write(self.style.WARNING(f"Total issues: {len(issues)}"))
