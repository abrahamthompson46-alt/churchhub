"""Normalize user access scopes after platform control room upgrade."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Enforce platform vs institution user scopes (is_staff, church, is_platform_user)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--promote-admin",
            action="store_true",
            help="Promote username 'admin' to platform owner if no platform users exist.",
        )

    def handle(self, *args, **options):
        fixed = 0

        if options["promote_admin"] and not User.objects.filter(is_platform_user=True).exists():
            admin = User.objects.filter(username="admin").first()
            if admin:
                admin.is_platform_user = True
                admin.is_superuser = True
                admin.is_staff = True
                admin.church = None
                admin.save()
                self.stdout.write(self.style.SUCCESS("Promoted 'admin' to platform owner."))
                fixed += 1

        for user in User.objects.filter(is_platform_user=True):
            updates = []
            if user.church_id:
                user.church = None
                updates.append("church cleared")
            if not user.is_superuser:
                user.is_staff = False
            user.save()
            if updates:
                self.stdout.write(f"  Platform user {user.username}: {', '.join(updates)}")
                fixed += 1

        qs = User.objects.filter(is_platform_user=False)
        stripped = qs.filter(is_staff=True).update(is_staff=False)
        if stripped:
            self.stdout.write(f"  Removed is_staff from {stripped} institution user(s).")
            fixed += stripped

        self.stdout.write(self.style.SUCCESS(f"Done. {fixed} adjustment(s) made."))
