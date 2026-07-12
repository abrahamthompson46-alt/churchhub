"""Run monthly depreciation for churches with auto-run enabled."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from assets.models import DepreciationPolicy
from assets.services import run_monthly_depreciation
from organization.models import Church


class Command(BaseCommand):
    help = "Post monthly depreciation for churches with auto_run_monthly enabled."

    def add_arguments(self, parser):
        parser.add_argument("--church", type=str, help="Church code (optional)")
        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)

    def handle(self, *args, **options):
        now = timezone.now()
        year = options.get("year") or now.year
        month = options.get("month") or now.month
        day = now.day

        policies = DepreciationPolicy.objects.filter(auto_run_monthly=True).select_related("church")
        if options.get("church"):
            policies = policies.filter(church__code=options["church"])

        for policy in policies:
            if day < policy.run_day_of_month:
                continue
            church = policy.church
            result = run_monthly_depreciation(church, year, month, user=None)
            self.stdout.write(
                f"{church.code}: posted={result['posted']} skipped={result['skipped']} errors={len(result['errors'])}"
            )
