"""
Seed end-to-end demo data and validate ledger integrity + URL access.

Usage:
    python manage.py qa_seed_and_validate
    python manage.py qa_seed_and_validate --validate-only
    python manage.py qa_seed_and_validate --seed-only
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

User = get_user_model()
QA_ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]


class Command(BaseCommand):
    help = "Seed full demo data and validate ledger balance, permissions, and routes."

    def add_arguments(self, parser):
        parser.add_argument("--seed-only", action="store_true")
        parser.add_argument("--validate-only", action="store_true")
        parser.add_argument("--no-input", action="store_true")

    def handle(self, *args, **options):
        self.issues = []
        self.passes = []

        if not options["validate_only"]:
            self._seed(options)

        if not options["seed_only"]:
            self._validate_ledger()
            self._validate_reports()
            self._validate_permissions()
            self._validate_urls()
            self._validate_payroll_exports()
            self._print_report()

    def _seed(self, options):
        self.stdout.write(self.style.MIGRATE_HEADING("Running base setup..."))
        call_command(
            "setup_churchhub",
            no_input=True,
            verbosity=0,
        )

        from organization.models import Church
        from accounts.models import UserRole

        church = Church.objects.get(code="TC01")
        treasurer = User.objects.get(username="treasury")
        pastor = User.objects.get(username="pastor")
        member = church.member_set.filter(is_active=True).first()

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding extended financial flows..."))
        self._seed_remittance_welfare(church, treasurer, pastor, member)
        self._seed_ledger(church, treasurer, pastor, member)
        self._seed_budget(church)
        self._seed_payroll(church, treasurer, pastor, member)
        self._seed_org_extras()
        self.passes.append("Full demo data seeded")

    def _seed_remittance_welfare(self, church, treasurer, pastor, member):
        from remittance.services import (
            approve_welfare_case,
            create_settlement_draft,
            create_welfare_case,
            disburse_welfare_case,
            post_settlement_batch,
        )
        from transactions.services import approve_transaction, record_receipt

        if not church.transactions.filter(description__icontains="Welfare offering").exists():
            welfare_txn = record_receipt(
                church=church,
                created_by=treasurer,
                special_offerings={"WELFARE": Decimal("300.00")},
                member=member,
                description="Welfare offering seed",
            )
            approve_transaction(welfare_txn, pastor)

        if member and not church.welfare_cases.exists():
            case = create_welfare_case(
                church=church,
                member=member,
                amount_requested=Decimal("50.00"),
                reason="QA seed assistance",
                user=treasurer,
            )
            approve_welfare_case(case, pastor, amount_approved=Decimal("50.00"))
            disburse_welfare_case(case, treasurer)

        today = timezone.now().date()
        try:
            batch = create_settlement_draft(
                from_unit_type="CHURCH",
                from_unit_id=church.pk,
                offering_type="COMBINED",
                period_start=today.replace(day=1),
                period_end=today,
                user=treasurer,
                church=church,
            )
            post_settlement_batch(batch, pastor)
        except Exception as exc:
            self.issues.append(f"Settlement seed skipped: {exc}")

    def _seed_ledger(self, church, treasurer, pastor, member):
        from ledger.models import LedgerCategory
        from ledger.services import build_entry_draft, post_ledger_entry
        from transactions.services import approve_transaction, open_working_day

        open_working_day(church, timezone.now().date(), pastor)

        cat = LedgerCategory.objects.filter(church=church, code="REC_TITHE_CASH").first()
        if cat and not Transaction_exists_ledger(church, "QA ledger tithe"):
            draft = build_entry_draft(cat, Decimal("120.00"), "QA ledger tithe", timezone.now().date(), member=member)
            txn = post_ledger_entry(church, treasurer, draft)
            approve_transaction(txn, pastor)

        exp = LedgerCategory.objects.filter(church=church, code="EXP_UTIL_CASH").first()
        if exp and not Transaction_exists_ledger(church, "QA ledger utility"):
            draft = build_entry_draft(exp, Decimal("45.00"), "QA ledger utility", timezone.now().date())
            post_ledger_entry(church, treasurer, draft)

    def _seed_budget(self, church):
        from transactions.models import Account, Budget

        account = Account.objects.filter(church=church, account_type="SALARY_EXPENSE").first()
        if account:
            Budget.objects.get_or_create(
                church=church,
                year=timezone.now().year,
                account=account,
                defaults={"amount": Decimal("50000.00"), "level": "CHURCH"},
            )

    def _seed_payroll(self, church, treasurer, pastor, member):
        from payroll.models import Employee, EmployeeCompensation, EmployeeCompensationLine, PayComponentType, PayrollRun
        from payroll.services import (
            approve_payroll_run,
            calculate_payroll_run,
            create_payroll_run,
            ensure_payroll_defaults_for_church,
            pay_payroll_run,
            post_payroll_run,
            treasury_approve_payroll_run,
        )

        ensure_payroll_defaults_for_church(church)
        employee, _ = Employee.objects.get_or_create(
            host_church=church,
            employee_number="EMP-QA01",
            defaults={
                "paying_unit_type": "CHURCH",
                "paying_unit_id": church.pk,
                "first_name": "Grace",
                "last_name": "Staff",
                "employment_type": "FULL_TIME",
                "date_joined": date(2022, 1, 1),
                "status": "ACTIVE",
                "user": treasurer,
            },
        )
        if member and not employee.member_id:
            employee.member = member
            employee.save(update_fields=["member"])

        basic = PayComponentType.objects.get(host_church=church, code="BASIC")
        if not employee.compensations.filter(is_active=True).exists():
            comp = EmployeeCompensation.objects.create(
                employee=employee,
                effective_from=date(2022, 1, 1),
                is_active=True,
            )
            EmployeeCompensationLine.objects.create(
                compensation=comp,
                line_type="EARNING",
                pay_component=basic,
                amount=Decimal("2500.00"),
            )

        today = timezone.now()
        if not PayrollRun.objects.filter(host_church=church, year=today.year, month=today.month).exclude(status="VOID").exists():
            run = create_payroll_run(
                host_church=church,
                year=today.year,
                month=today.month,
                user=treasurer,
            )
            calculate_payroll_run(run, treasurer)
            approve_payroll_run(run, pastor)
            treasury_approve_payroll_run(run, treasurer)
            post_payroll_run(run, treasurer)
            pay_payroll_run(run, treasurer)

    def _seed_org_extras(self):
        from organization.models import GeneralConference, Union
        from organization.models import Conference

        gc, _ = GeneralConference.objects.get_or_create(
            code="GGC",
            defaults={"name": "General Conference of Ghana"},
        )
        union, _ = Union.objects.get_or_create(
            code="GU",
            defaults={"name": "Ghana Union", "general_conference": gc},
        )
        conf = Conference.objects.get(code="GAC")
        if not conf.union_id:
            conf.union = union
            conf.save(update_fields=["union"])

    def _validate_ledger(self):
        from transactions.models import Account, Transaction, TransactionLine
        from transactions.services import validate_transaction_balance
        from organization.models import Church

        self.stdout.write(self.style.MIGRATE_HEADING("Validating ledger integrity..."))

        unbalanced = []
        for txn in Transaction.objects.filter(is_voided=False).iterator():
            try:
                validate_transaction_balance(txn)
            except Exception as exc:
                unbalanced.append(f"{txn.reference}: {exc}")

        if unbalanced:
            self.issues.extend(unbalanced)
        else:
            self.passes.append(f"All {Transaction.objects.filter(is_voided=False).count()} transactions balanced")

        for church in Church.objects.all():
            total = TransactionLine.objects.filter(
                transaction__church=church,
                transaction__is_voided=False,
            ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
            from transactions.services import _quantize_currency
            if _quantize_currency(total) != Decimal("0.00"):
                self.issues.append(f"Church {church.name} trial balance ≠ 0: {total}")
            else:
                self.passes.append(f"Trial balance zero for {church.name}")

            cash = self._account_balance(church, "CASH")
            bank = self._account_balance(church, "BANK")
            self.passes.append(f"{church.name} Cash=GHS {cash} Bank=GHS {bank}")

    def _account_balance(self, church, account_type):
        from transactions.models import TransactionLine

        total = TransactionLine.objects.filter(
            transaction__church=church,
            transaction__approval_status="APPROVED",
            transaction__is_voided=False,
            account__account_type=account_type,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        return total

    def _validate_reports(self):
        from reports.registry import REPORT_CATALOG
        from reports.services import build_report

        self.stdout.write(self.style.MIGRATE_HEADING("Validating report builders..."))
        treasurer = User.objects.filter(username="treasury").first()
        if not treasurer:
            self.issues.append("Treasury user missing for report validation")
            return
        request = type("Req", (), {"user": treasurer})()
        for key in REPORT_CATALOG:
            try:
                result = build_report(key, request, period="monthly")
                if result is None:
                    self.issues.append(f"Report {key} returned None")
                else:
                    self.passes.append(f"Report builder {key} OK")
            except Exception as exc:
                self.issues.append(f"Report {key} failed: {exc}")

    def _validate_permissions(self):
        from permissions.registry import PERMISSION_REGISTRY

        self.stdout.write(self.style.MIGRATE_HEADING("Validating permission registry..."))
        required = {
            "manage_finances", "manage_members", "manage_payroll",
            "approve_payroll", "post_payroll", "manage_remittance_policy",
        }
        missing = required - set(PERMISSION_REGISTRY.keys())
        if missing:
            self.issues.append(f"Missing permission keys: {missing}")
        else:
            self.passes.append("Core permission keys present")

        if User.objects.filter(username="secretary").exists():
            with override_settings(ALLOWED_HOSTS=QA_ALLOWED_HOSTS):
                client = Client()
                client.login(username="secretary", password="secretary123")
                resp = client.get(reverse("payroll:index"))
            if resp.status_code == 200:
                self.issues.append("Secretary can access payroll:index (expected deny)")
            else:
                self.passes.append("Secretary denied payroll access")

    def _validate_payroll_exports(self):
        from payroll.models import PayrollLine, PayrollRun

        run = PayrollRun.objects.filter(status="PAID").order_by("-created_at").first()
        if not run:
            return
        line = PayrollLine.objects.filter(payroll_run=run).first()
        with override_settings(ALLOWED_HOSTS=QA_ALLOWED_HOSTS):
            client = Client()
            client.login(username="treasury", password="treasury123")
            exports = [
                ("payroll:run_export_csv", [run.pk]),
                ("payroll:run_export_register", [run.pk]),
                ("payroll:run_paye_pdf", [run.pk]),
                ("payroll:run_ssnit_pdf", [run.pk]),
            ]
            if line:
                exports.append(("payroll:payslip_pdf", [line.pk]))
            for name, args in exports:
                try:
                    resp = client.get(reverse(name, args=args))
                    if resp.status_code != 200:
                        self.issues.append(f"Export {name} → {resp.status_code}")
                    else:
                        self.passes.append(f"Export {name} → OK")
                except Exception as exc:
                    self.issues.append(f"Export {name} failed: {exc}")

    def _validate_urls(self):
        self.stdout.write(self.style.MIGRATE_HEADING("Smoke-testing routes..."))
        client = Client()
        routes = [
            ("treasury", "treasury123", [
                ("dashboard:home", []),
                ("ledger:index", []),
                ("ledger:categories", []),
                ("ledger:entries", []),
                ("ledger:entry", []),
                ("transactions:transaction_list", []),
                ("transactions:pending_approvals", []),
                ("transactions:financial_dashboard", []),
                ("transactions:record_receipt", []),
                ("transactions:record_expense", []),
                ("transactions:budget_report", []),
                ("transactions:audit_log", []),
                ("transactions:period_list", []),
                ("transactions:reconciliation_list", []),
                ("remittance:index", []),
                ("remittance:settlements", []),
                ("remittance:welfare", []),
                ("payroll:index", []),
                ("payroll:employee_list", []),
                ("payroll:run_list", []),
                ("payroll:my_payslips", []),
                ("reports:index", []),
                ("budgets:list", []),
                ("giving:index", []),
                ("members:list", []),
                ("meetings:list", []),
                ("announcements:announcement_list", []),
                ("reports:run", ["financial_summary"]),
                ("reports:run", ["tithe_report"]),
                ("reports:run", ["payroll_summary"]),
            ]),
            ("pastor", "pastor123", [
                ("dashboard:home", []),
                ("transactions:pending_approvals", []),
                ("members:list", []),
                ("meetings:list", []),
            ]),
            ("secretary", "secretary123", [
                ("dashboard:home", []),
                ("members:list", []),
                ("members:department_list", []),
                ("meetings:list", []),
                ("announcements:announcement_list", []),
            ]),
            ("admin", "admin12345", [
                ("permissions:index", []),
                ("permissions:matrix", []),
                ("permissions:audit_log", []),
                ("organization:hierarchy", []),
                ("payroll:hierarchy", []),
                ("payroll:policy_index", []),
                ("accounts:user_list", []),
            ]),
        ]
        for username, password, urls in routes:
            if not User.objects.filter(username=username).exists():
                continue
            with override_settings(ALLOWED_HOSTS=QA_ALLOWED_HOSTS):
                client.logout()
                assert client.login(username=username, password=password)
                for name, args in urls:
                    try:
                        url = reverse(name, args=args)
                        resp = client.get(url)
                        if resp.status_code not in (200, 302):
                            self.issues.append(f"{username} GET {name} → {resp.status_code}")
                        else:
                            self.passes.append(f"{username} GET {name} → OK")
                    except Exception as exc:
                        self.issues.append(f"{username} GET {name} failed: {exc}")

    def _print_report(self):
        def _safe(text):
            return str(text).encode("ascii", errors="replace").decode("ascii")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(" QA VALIDATION REPORT"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"  PASSED: {len(self.passes)}"))
        for p in self.passes[:15]:
            self.stdout.write(f"    [OK] {_safe(p)}")
        if len(self.passes) > 15:
            self.stdout.write(f"    ... and {len(self.passes) - 15} more")

        if self.issues:
            self.stdout.write(self.style.ERROR(f"  ISSUES: {len(self.issues)}"))
            for issue in self.issues:
                self.stdout.write(self.style.ERROR(f"    [FAIL] {_safe(issue)}"))
        else:
            self.stdout.write(self.style.SUCCESS("  No issues found."))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        if self.issues:
            raise SystemExit(1)


def Transaction_exists_ledger(church, snippet):
    from transactions.models import Transaction
    return Transaction.objects.filter(church=church, description__icontains=snippet).exists()
