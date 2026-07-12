from django.core.management.base import BaseCommand

from permissions.services import ensure_permission_matrix


class Command(BaseCommand):
    help = "Sync permission definitions and role-permission matrix from the registry."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all matrix cells to registry defaults.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            from permissions.services import reset_matrix_to_defaults

            reset_matrix_to_defaults()
            self.stdout.write(self.style.SUCCESS("Permission matrix reset to defaults."))
        else:
            ensure_permission_matrix(force_defaults=False)
            self.stdout.write(self.style.SUCCESS("Permission matrix synced."))
