"""Export member personal data as JSON."""

from django.core.management.base import BaseCommand, CommandError

from members.export import export_member_json
from members.models import Member


class Command(BaseCommand):
    help = "Export a member's personal data package (JSON) for subject access requests."

    def add_arguments(self, parser):
        parser.add_argument("--member", required=True, help="Member UUID")
        parser.add_argument("--output", default="", help="Output file path (stdout if omitted)")

    def handle(self, *args, **options):
        try:
            member = Member.objects.select_related("church", "department", "family").get(pk=options["member"])
        except Member.DoesNotExist as exc:
            raise CommandError("Member not found.") from exc

        data = export_member_json(member)
        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as fh:
                fh.write(data)
            self.stdout.write(self.style.SUCCESS(f"Exported {member.full_name} to {options['output']}"))
        else:
            self.stdout.write(data)
