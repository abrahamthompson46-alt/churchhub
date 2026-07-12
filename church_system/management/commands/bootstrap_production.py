"""
Idempotent production bootstrap for fresh deployments (Render, Docker, VPS).

Creates platform owner, default plans, payment methods, and denominations.
Does NOT create demo users, sample transactions, or weak default passwords
unless CHURCHHUB_BOOTSTRAP_DEMO=1.

Usage:
    python manage.py bootstrap_production
    python manage.py bootstrap_production --no-input
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand

User = get_user_model()

WEAK_PASSWORDS = frozenset({
    "admin12345",
    "password",
    "changeme",
    "churchhub",
})


class Command(BaseCommand):
    help = "Bootstrap a production ChurchHub instance (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip interactive prompts.",
        )

    def handle(self, *args, **options):
        from permissions.services import ensure_permission_matrix
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.services import ensure_default_payment_methods, ensure_default_plans

        self.stdout.write(self.style.MIGRATE_HEADING("Syncing permission matrix..."))
        ensure_permission_matrix()

        self.stdout.write(self.style.MIGRATE_HEADING("Ensuring subscription plans..."))
        ensure_default_plans()

        self.stdout.write(self.style.MIGRATE_HEADING("Ensuring payment methods..."))
        ensure_default_payment_methods()

        self.stdout.write(self.style.MIGRATE_HEADING("Ensuring denominations..."))
        ensure_builtin_denominations()

        self.stdout.write(self.style.MIGRATE_HEADING("Ensuring platform owner..."))
        owner = self._ensure_platform_owner(options["no_input"])

        if os.environ.get("CHURCHHUB_BOOTSTRAP_DEMO", "").lower() in ("1", "true", "yes"):
            from django.core.management import call_command

            self.stdout.write(self.style.WARNING("CHURCHHUB_BOOTSTRAP_DEMO=1 — seeding demo hierarchy..."))
            call_command("setup_churchhub", "--no-input", "--skip-demo-data")

        self.stdout.write(self.style.SUCCESS("Production bootstrap complete."))
        self.stdout.write(f"  Platform owner: {owner.username}")
        self.stdout.write(f"  Control room: {settings.CHURCHHUB_PUBLIC_URL.rstrip('/')}/platform/")

    def _ensure_platform_owner(self, no_input):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip() or "platform"
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip() or f"{username}@churchhub.local"
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()

        if not settings.DEBUG:
            if not password:
                raise ImproperlyConfigured(
                    "Set DJANGO_SUPERUSER_PASSWORD before bootstrapping production."
                )
            if password.lower() in WEAK_PASSWORDS:
                raise ImproperlyConfigured(
                    "DJANGO_SUPERUSER_PASSWORD is too weak for production."
                )

        if not password:
            password = "admin12345"
            self.stdout.write(self.style.WARNING("  Using development default password for platform owner."))

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": "Platform",
                "last_name": "Owner",
                "is_platform_user": True,
                "is_superuser": True,
                "is_staff": True,
                "church": None,
                "platform_role": "OWNER",
            },
        )
        if created or not user.check_password(password):
            user.set_password(password)
        user.is_platform_user = True
        user.is_superuser = True
        user.is_staff = True
        user.church = None
        user.platform_role = "OWNER"
        user.is_active = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"  Created platform owner: {username}"))
        else:
            self.stdout.write(f"  Platform owner '{username}' ready.")
        return user
