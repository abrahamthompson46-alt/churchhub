"""
Bootstrap ChurchHub for development or fresh deployments.

Usage:
    python manage.py setup_churchhub --reset
    python manage.py setup_churchhub
    python manage.py setup_churchhub --no-input
"""

import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from accounts.models import UserRole
from accounts.services import sync_role_groups
from members.models import Gender, Member, MembershipStatus
from organization.models import Church, Conference, District, Zone
from transactions.services import (
    approve_transaction,
    create_default_accounts,
    create_default_offering_categories,
    record_expense,
    record_receipt,
)

User = get_user_model()

DEFAULT_SUPERUSER = {
    "username": "admin",
    "email": "admin@churchhub.local",
    "password": "admin12345",
}

DEMO_USERS = [
    {
        "username": "treasury",
        "email": "treasury@churchhub.local",
        "password": "treasury123",
        "role": UserRole.TREASURY,
        "first_name": "Grace",
        "last_name": "Treasury",
    },
    {
        "username": "pastor",
        "email": "pastor@churchhub.local",
        "password": "pastor123",
        "role": UserRole.LOCAL_PASTOR,
        "first_name": "John",
        "last_name": "Pastor",
    },
    {
        "username": "secretary",
        "email": "secretary@churchhub.local",
        "password": "secretary123",
        "role": UserRole.SECRETARY,
        "first_name": "Mary",
        "last_name": "Secretary",
    },
]

SAMPLE_MEMBERS = [
    ("Kwame", "Mensah", Gender.MALE),
    ("Ama", "Osei", Gender.FEMALE),
    ("Kofi", "Boateng", Gender.MALE),
    ("Abena", "Asante", Gender.FEMALE),
    ("Yaw", "Adom", Gender.MALE),
]

AUTH_GROUPS = ["Admins", "Managers", "superAdmin", "admin"]


class Command(BaseCommand):
    help = "Reset database (optional), migrate, and seed superuser + sample church data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete SQLite database and run fresh migrations.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Use default credentials without prompts.",
        )
        parser.add_argument(
            "--skip-demo-data",
            action="store_true",
            help="Only create superuser and hierarchy; skip members/transactions.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset_database()

        call_command("migrate", verbosity=options.get("verbosity", 1))

        self.stdout.write(self.style.MIGRATE_HEADING("Syncing permission matrix..."))
        from permissions.services import ensure_permission_matrix
        ensure_permission_matrix()

        self.stdout.write(self.style.MIGRATE_HEADING("Creating auth groups..."))
        self._ensure_groups()

        self.stdout.write(self.style.MIGRATE_HEADING("Creating organization hierarchy..."))
        church = self._ensure_hierarchy()

        self.stdout.write(self.style.MIGRATE_HEADING("Creating platform owner..."))
        platform_owner = self._ensure_platform_owner(options["no_input"])

        self.stdout.write(self.style.MIGRATE_HEADING("Creating institution admin..."))
        institution_admin = self._ensure_institution_admin(church, options["no_input"])

        self.stdout.write(self.style.MIGRATE_HEADING("Creating demo users..."))
        demo_users = self._ensure_demo_users(church)

        if not options["skip_demo_data"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Creating sample members..."))
            self._ensure_members(church, institution_admin)
            self.stdout.write(self.style.MIGRATE_HEADING("Creating sample transactions..."))
            self._ensure_transactions(church, demo_users)

        self._print_summary(platform_owner, institution_admin, church, demo_users)

    def _reset_database(self):
        engine = settings.DATABASES["default"]["ENGINE"]
        if "sqlite3" not in engine:
            self.stderr.write(
                self.style.ERROR(
                    "--reset only supports SQLite. "
                    "Drop and recreate your PostgreSQL database manually."
                )
            )
            return

        db_path = settings.DATABASES["default"]["NAME"]
        if connection.is_usable():
            connection.close()

        if os.path.exists(db_path):
            os.remove(db_path)
            self.stdout.write(self.style.WARNING(f"Deleted database: {db_path}"))
        else:
            self.stdout.write(f"No database file at {db_path}")

    def _ensure_groups(self):
        for name in AUTH_GROUPS:
            Group.objects.get_or_create(name=name)

    def _ensure_hierarchy(self):
        conference, _ = Conference.objects.get_or_create(
            code="GAC",
            defaults={"name": "Ghana Apostolic Conference"},
        )
        zone, _ = Zone.objects.get_or_create(
            conference=conference,
            code="CZ",
            defaults={"name": "Central Zone"},
        )
        district, _ = District.objects.get_or_create(
            zone=zone,
            code="KD",
            defaults={"name": "Kumasi District"},
        )
        church, created = Church.objects.get_or_create(
            district=district,
            code="TC01",
            defaults={
                "name": "Test Church - Accra Central",
                "address": "Ring Road Central, Accra, Ghana",
            },
        )
        if created or not church.accounts.exists():
            create_default_accounts(church)
            create_default_offering_categories(church)
            from ledger.services import seed_ledger
            seed_ledger(church)
        from remittance.services import (
            ensure_default_policies_for_church,
            ensure_hierarchy_settlement_policies,
        )
        ensure_default_policies_for_church(church)
        ensure_hierarchy_settlement_policies(church)
        from sitecontrol.services import (
            assign_subscription,
            ensure_default_payment_methods,
            ensure_default_plans,
            get_default_plan,
        )

        ensure_default_plans()
        ensure_default_payment_methods()
        plan = get_default_plan()
        if plan:
            assign_subscription(church, plan)

        from sitecontrol.denomination_services import ensure_builtin_denominations
        ensure_builtin_denominations()

        from members.lookups import ensure_member_form_catalogs
        ensure_member_form_catalogs(church)

        from assets.services import ensure_asset_defaults_for_church
        ensure_asset_defaults_for_church(church)

        return church

    def _ensure_platform_owner(self, no_input):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", DEFAULT_SUPERUSER["username"])
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", DEFAULT_SUPERUSER["email"])
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", DEFAULT_SUPERUSER["password"])

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
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"  Created platform owner: {username}"))
        else:
            user.is_platform_user = True
            user.is_superuser = True
            user.is_staff = True
            user.church = None
            user.save(update_fields=["is_platform_user", "is_superuser", "is_staff", "church"])
            self.stdout.write(f"  Platform owner '{username}' already exists (updated flags).")
        return user

    def _ensure_institution_admin(self, church, no_input):
        username = "instadmin"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": "instadmin@churchhub.local",
                "role": UserRole.SUPER_ADMIN,
                "church": church,
                "first_name": "Institution",
                "last_name": "Admin",
                "is_staff": False,
                "is_superuser": False,
                "is_platform_user": False,
            },
        )
        if created:
            user.set_password("instadmin123")
            user.save()
            sync_role_groups(user)
            self.stdout.write(self.style.SUCCESS(f"  Created institution admin: {username}"))
        else:
            sync_role_groups(user)
            self.stdout.write(f"  Institution admin '{username}' already exists.")
        return user

    def _ensure_superuser(self, church, no_input):
        """Legacy alias — use _ensure_platform_owner."""
        return self._ensure_platform_owner(no_input)

    def _ensure_demo_users(self, church):
        users = {}
        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "role": spec["role"],
                    "church": church,
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": False,
                    "is_superuser": False,
                    "is_platform_user": False,
                },
            )
            if created:
                user.set_password(spec["password"])
                user.save()
                sync_role_groups(user)
                self.stdout.write(self.style.SUCCESS(f"  Created user: {spec['username']}"))
            else:
                sync_role_groups(user)
                self.stdout.write(f"  User '{spec['username']}' already exists.")
            users[spec["username"]] = user
        return users

    def _ensure_members(self, church, creator):
        for first, last, gender in SAMPLE_MEMBERS:
            Member.objects.get_or_create(
                church=church,
                first_name=first,
                last_name=last,
                defaults={
                    "gender": gender,
                    "membership_status": MembershipStatus.ACTIVE,
                    "is_active": True,
                    "phone": "0200000000",
                    "created_by": creator,
                },
            )
        self.stdout.write(f"  {Member.objects.filter(church=church).count()} members in {church.name}")

    def _ensure_transactions(self, church, demo_users):
        treasurer = demo_users.get("treasury")
        pastor = demo_users.get("pastor")
        if not treasurer or not pastor:
            return

        if not church.transactions.exists():
            receipt = record_receipt(
                church=church,
                created_by=treasurer,
                tithe_amount=Decimal("500.00"),
                combined_amount=Decimal("200.00"),
                income_amount=Decimal("100.00"),
                description="Sunday service offering",
            )
            approve_transaction(receipt, pastor)

            pending = record_expense(
                church=church,
                created_by=treasurer,
                amount=Decimal("150.00"),
                description="Utility bill — pending approval",
            )
            self.stdout.write(
                f"  Sample transactions: 1 approved receipt, 1 pending expense ({pending.reference})"
            )

    def _print_summary(self, platform_owner, institution_admin, church, demo_users):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(" ChurchHub setup complete"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Church:     {church.name}")
        self.stdout.write(f"  District:   {church.district.name}")
        self.stdout.write(f"  Conference: {church.district.zone.conference.name}")
        self.stdout.write("")
        self.stdout.write("  Login credentials:")
        self.stdout.write(f"    Platform:   {platform_owner.username} / {DEFAULT_SUPERUSER['password']}  → /platform/")
        self.stdout.write(f"    Inst Admin: {institution_admin.username} / instadmin123  → /dashboard/")
        for spec in DEMO_USERS:
            self.stdout.write(f"    {spec['role']:14} {spec['username']} / {spec['password']}")
        self.stdout.write("")
        self.stdout.write("  URLs:")
        self.stdout.write("    Login:      /accounts/login/")
        self.stdout.write("    Dashboard:  /dashboard/")
        self.stdout.write("    Platform:   /platform/")
        self.stdout.write("    Admin:      /admin/  (break-glass platform owners only)")
        self.stdout.write(self.style.SUCCESS("=" * 60))
