"""Characterization tests for budgets selectors / repositories layering."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from budgets import repositories as repo
from budgets import selectors
from budgets.services import (
    BudgetServiceError,
    budget_has_approved_actuals,
    budget_line_variance,
    delete_budget,
    get_editable_budget,
    save_budget,
)
from members.models import Department
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.models import Account, Budget, FinancialAuditLog, Transaction, TransactionLine
from transactions.services import create_default_accounts

User = get_user_model()


class BudgetsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(
            name="Bud Layer Denom A", code="blda", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Bud Layer Denom B", code="bldb", is_active=True
        )
        conf_a = Conference.objects.create(
            code="BLCA", name="Bud Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="BLCB", name="Bud Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="BLZA", name="Bud Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="BLZB", name="Bud Zone B")
        dist_a = District.objects.create(zone=zone_a, code="BLDA", name="Bud Dist A")
        dist_b = District.objects.create(zone=zone_b, code="BLDB", name="Bud Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="BLCHA", name="Bud Church A"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="BLCHB", name="Bud Church B"
        )
        create_default_accounts(cls.church_a)
        create_default_accounts(cls.church_b)
        cls.income_a = Account.objects.get(church=cls.church_a, name="General Income")
        cls.expense_a = Account.objects.get(church=cls.church_a, name="General Expense")
        cls.income_b = Account.objects.get(church=cls.church_b, name="General Income")
        cls.year = timezone.now().year
        cls.department = Department.objects.create(
            church=cls.church_a, name="Layer Youth"
        )

    def setUp(self):
        self.treasury_a = User.objects.create_user(
            username="bud_layer_t_a",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church_a,
            denomination=self.denom_a,
        )

    def test_selector_reads_scoped_lists(self):
        Budget.objects.create(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.income_a,
            amount=Decimal("1000.00"),
        )
        Budget.objects.create(
            church=self.church_b,
            level="CHURCH",
            year=self.year,
            account=self.income_b,
            amount=Decimal("2000.00"),
        )
        qs_a = selectors.budgets_for_scope_qs(
            church=self.church_a, year=self.year, level="CHURCH"
        )
        self.assertEqual(qs_a.count(), 1)
        self.assertEqual(qs_a.first().church_id, self.church_a.pk)
        self.assertTrue(
            selectors.accounts_for_church_qs(self.church_a)
            .filter(pk=self.income_a.pk)
            .exists()
        )

    def test_church_isolation_editable_budget(self):
        budget_b = Budget.objects.create(
            church=self.church_b,
            level="CHURCH",
            year=self.year,
            account=self.income_b,
            amount=Decimal("500.00"),
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.treasury_a
        request.session = {}
        with self.assertRaises(Http404):
            get_editable_budget(request, budget_b.pk)

        budget_a = Budget.objects.create(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.income_a,
            amount=Decimal("750.00"),
        )
        found, church = get_editable_budget(request, budget_a.pk)
        self.assertEqual(found.pk, budget_a.pk)
        self.assertEqual(church.pk, self.church_a.pk)

    def test_repository_writes_and_audit(self):
        budget = Budget(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.expense_a,
            amount=Decimal("300.00"),
        )
        save_budget(budget, self.treasury_a, self.church_a, is_new=True)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                church=self.church_a, action="BUDGET_CREATE"
            ).exists()
        )
        budget.amount = Decimal("350.00")
        save_budget(
            budget, self.treasury_a, self.church_a, is_new=False, old_amount=Decimal("300.00")
        )
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                church=self.church_a, action="BUDGET_UPDATE"
            ).exists()
        )

    def test_delete_blocked_when_approved_actuals(self):
        """Integrity lock: cannot delete church lines once approved actuals exist."""
        cash = Account.objects.get(church=self.church_a, name="Cash")
        budget = Budget.objects.create(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.expense_a,
            amount=Decimal("1000.00"),
        )
        txn = Transaction.objects.create(
            transaction_type="EXPENSE",
            church=self.church_a,
            date=date(self.year, 6, 15),
            description="Layer expense",
            approval_status="APPROVED",
            created_by=self.treasury_a,
        )
        TransactionLine.objects.create(
            transaction=txn, account=self.expense_a, amount=Decimal("100.00")
        )
        TransactionLine.objects.create(
            transaction=txn, account=cash, amount=Decimal("-100.00")
        )
        self.assertTrue(budget_has_approved_actuals(budget))
        with self.assertRaises(BudgetServiceError):
            delete_budget(budget, self.treasury_a, self.church_a)
        self.assertTrue(Budget.objects.filter(pk=budget.pk).exists())

    def test_variance_calculations(self):
        budget = Budget.objects.create(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.income_a,
            amount=Decimal("1000.00"),
        )
        row = budget_line_variance(budget)
        self.assertEqual(row["budgeted"], Decimal("1000.00"))
        self.assertEqual(row["actual"], Decimal("0.00"))
        self.assertTrue(row["tracks_actual"])

        dept_budget = Budget.objects.create(
            church=self.church_a,
            level="DEPARTMENT",
            year=self.year,
            department=self.department,
            account=self.expense_a,
            amount=Decimal("200.00"),
        )
        dept_row = budget_line_variance(dept_budget)
        self.assertFalse(dept_row["tracks_actual"])
        self.assertIsNone(dept_row["actual"])

    def test_duplicate_selector_and_repo_delete(self):
        budget = Budget.objects.create(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.income_a,
            amount=Decimal("100.00"),
        )
        twin = Budget(
            church=self.church_a,
            level="CHURCH",
            year=self.year,
            account=self.income_a,
            amount=Decimal("200.00"),
        )
        self.assertTrue(selectors.duplicate_budget_exists(twin))
        delete_budget(budget, self.treasury_a, self.church_a)
        self.assertFalse(Budget.objects.filter(pk=budget.pk).exists())
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                church=self.church_a, action="BUDGET_DELETE"
            ).exists()
        )
        # Direct repository write helper remains thin.
        other = Budget(
            church=self.church_a,
            level="CHURCH",
            year=self.year + 1,
            account=self.income_a,
            amount=Decimal("50.00"),
        )
        repo.save_budget(other)
        self.assertTrue(Budget.objects.filter(pk=other.pk).exists())
