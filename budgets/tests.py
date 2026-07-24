"""Tests for budgets app — CRUD, variance, audit, permissions, and exports."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.client import ContextList
from django.urls import reverse
from django.utils import timezone

from members.models import Department
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import SiteSettings
from transactions.models import Account, Budget, FinancialAuditLog

User = get_user_model()


class BudgetsTestMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        cls.conference = Conference.objects.create(code="BC", name="Budget Conf")
        cls.zone = Zone.objects.create(conference=cls.conference, code="BZ", name="Budget Zone")
        cls.district = District.objects.create(zone=cls.zone, code="BD", name="Budget District")
        cls.church = Church.objects.create(district=cls.district, code="BCH", name="Budget Church")
        cls.income_account = Account.objects.get(church=cls.church, name="General Income")
        cls.expense_account, _ = Account.objects.get_or_create(
            church=cls.church,
            name="Budget Operations",
            defaults={"account_type": "EXPENSE"},
        )
        cls.department = Department.objects.create(church=cls.church, name="Youth")
        ensure_permission_matrix()


class BudgetViewTests(BudgetsTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.treasury = User.objects.create_user(
            username="budget_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.member = User.objects.create_user(
            username="budget_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="budget_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )

    def test_budget_list_requires_finance_role(self):
        self.client.login(username="budget_member", password="pass12345")
        response = self.client.get(reverse("budgets:list"))
        self.assertEqual(response.status_code, 403)

    def test_budget_list_renders_for_treasury(self):
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.get(reverse("budgets:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual Budget")
        self.assertContains(response, "Total Budgeted")

    def test_create_church_budget(self):
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.post(reverse("budgets:create"), {
            "level": "CHURCH",
            "year": 2026,
            "account": self.income_account.pk,
            "amount": "12000.00",
            "notes": "Annual income target",
        })
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(account=self.income_account, year=2026, level="CHURCH")
        self.assertEqual(budget.amount, Decimal("12000.00"))
        self.assertTrue(
            FinancialAuditLog.objects.filter(church=self.church, action="BUDGET_CREATE").exists()
        )

    def test_duplicate_budget_rejected(self):
        Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=2026,
            account=self.income_account,
            amount=Decimal("1000.00"),
        )
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.post(reverse("budgets:create"), {
            "level": "CHURCH",
            "year": 2026,
            "account": self.income_account.pk,
            "amount": "2000.00",
            "notes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Budget.objects.filter(account=self.income_account, year=2026).count(), 1)

    def test_edit_and_delete_budget(self):
        budget = Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=2026,
            account=self.expense_account,
            amount=Decimal("5000.00"),
        )
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.post(reverse("budgets:edit", args=[budget.pk]), {
            "level": "CHURCH",
            "year": 2026,
            "account": self.expense_account.pk,
            "amount": "4500.00",
            "notes": "Revised",
        })
        self.assertEqual(response.status_code, 302)
        budget.refresh_from_db()
        self.assertEqual(budget.amount, Decimal("4500.00"))
        self.assertTrue(
            FinancialAuditLog.objects.filter(church=self.church, action="BUDGET_UPDATE").exists()
        )

        response = self.client.post(reverse("budgets:delete", args=[budget.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Budget.objects.filter(pk=budget.pk).exists())
        self.assertTrue(
            FinancialAuditLog.objects.filter(church=self.church, action="BUDGET_DELETE").exists()
        )

    def test_department_budget_allocation(self):
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.post(
            reverse("budgets:create") + "?level=DEPARTMENT",
            {
                "level": "DEPARTMENT",
                "year": 2026,
                "department": self.department.pk,
                "account": self.expense_account.pk,
                "amount": "1500.00",
                "notes": "Youth programs",
            },
        )
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(level="DEPARTMENT", department=self.department)
        self.assertEqual(budget.amount, Decimal("1500.00"))

    def test_variance_shows_on_list(self):
        from transactions.services import approve_transaction, open_working_day, record_expense

        open_working_day(self.church, timezone.localdate(), self.pastor)
        expense_account = Account.objects.filter(church=self.church, account_type="EXPENSE").first()
        year = timezone.now().year
        Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=year,
            account=expense_account,
            amount=Decimal("1000.00"),
        )
        txn = record_expense(
            church=self.church,
            created_by=self.treasury,
            amount=Decimal("400.00"),
            description="Budget test expense",
        )
        approve_transaction(txn, self.pastor)
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.get(reverse("budgets:list"), {"year": year})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "On track")
        self.assertContains(response, expense_account.name)

    def test_csv_export(self):
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.get(reverse("budgets:list"), {"export": "csv", "year": 2026})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_legacy_budget_report_redirects(self):
        self.client.login(username="budget_treasury", password="pass12345")
        response = self.client.get(reverse("transactions:budget_report"), {"year": 2026})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/budgets/", response.url)


class BudgetServiceTests(BudgetsTestMixin, TestCase):
    def test_income_variance_favorable_when_actual_exceeds_budget(self):
        from budgets.services import _variance_meta

        meta = _variance_meta("INCOME", Decimal("1000"), Decimal("1200"))
        self.assertTrue(meta["favorable"])
        self.assertEqual(meta["variance"], Decimal("200.00"))

    def test_expense_variance_favorable_when_under_budget(self):
        from budgets.services import _variance_meta

        meta = _variance_meta("EXPENSE", Decimal("1000"), Decimal("800"))
        self.assertTrue(meta["favorable"])
        self.assertEqual(meta["variance"], Decimal("200.00"))

    def test_attach_forecast_extrapolates_ytd(self):
        from budgets.services import attach_forecast
        from unittest.mock import patch
        from datetime import date

        rows = [
            {
                "account": "Income",
                "account_type": "INCOME",
                "budgeted": Decimal("1200.00"),
                "actual": Decimal("300.00"),
                "tracks_actual": True,
                "variance": Decimal("-900.00"),
                "favorable": False,
            }
        ]
        with patch("django.utils.timezone.localdate", return_value=date(2026, 3, 15)):
            enriched = attach_forecast(rows, 2026)
        # March → 3/12 progress; 300 / 0.25 = 1200
        self.assertEqual(enriched[0]["forecast"], Decimal("1200.00"))

    def test_clone_budgets_copies_lines(self):
        from budgets.services import clone_budgets

        user = User.objects.create_user(
            username="budget_clone_user",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=2026,
            account=self.income_account,
            amount=Decimal("5000.00"),
            notes="Source",
        )
        result = clone_budgets(
            source_year=2026,
            target_year=2027,
            level="CHURCH",
            church=self.church,
            user=user,
        )
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["skipped"], 0)
        clone = Budget.objects.get(
            church=self.church, year=2027, account=self.income_account, level="CHURCH"
        )
        self.assertEqual(clone.amount, Decimal("5000.00"))
