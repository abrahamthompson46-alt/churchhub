"""Tests for accounting reports."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from reports.services import build_report
from transactions.models import Account, Transaction, TransactionLine
from transactions.services import validate_transaction_balance

User = get_user_model()


class AccountingReportTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="C", code="C1")
        zone = Zone.objects.create(name="Z", code="Z1", conference=conf)
        district = District.objects.create(name="D", code="D1", zone=zone)
        self.church = Church.objects.create(name="Ch", code="CH1", district=district)
        self.treasury = User.objects.create_user(
            username="treasury_r",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        cash = Account.objects.filter(church=self.church, account_type="CASH").first()
        if not cash:
            cash = Account.objects.create(name="Cash", account_type="CASH", church=self.church)
        income = Account.objects.filter(church=self.church, account_type="INCOME").first()
        if not income:
            income = Account.objects.create(name="Income", account_type="INCOME", church=self.church)
        txn = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=self.church,
            created_by=self.treasury,
            description="Seed receipt",
            approval_status="APPROVED",
        )
        TransactionLine.objects.create(transaction=txn, account=cash, amount=Decimal("100.00"))
        TransactionLine.objects.create(transaction=txn, account=income, amount=Decimal("-100.00"))
        validate_transaction_balance(txn)
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.get("/")
        request.user = self.treasury
        return request

    def test_trial_balance_balanced(self):
        data = build_report("trial_balance", self._request(), period="monthly")
        self.assertEqual(data["title"], "Trial Balance")
        self.assertEqual(data["summary"]["total_debit"], data["summary"]["total_credit"])
        self.assertTrue(data["statement"]["balanced"])
        self.assertTrue(data["statement"]["sections"])

    def test_balance_sheet_builds(self):
        data = build_report("balance_sheet", self._request(), period="monthly")
        self.assertEqual(data["title"], "Balance Sheet")
        self.assertTrue(len(data["rows"]) >= 1)
        titles = [section["title"] for section in data["statement"]["sections"]]
        self.assertEqual(titles, ["Assets", "Liabilities", "Funds & Equity"])

    def test_income_statement_builds(self):
        data = build_report("income_statement", self._request(), period="monthly")
        self.assertEqual(data["title"], "Income Statement")
        self.assertIn("income", data["summary"])
        self.assertEqual(len(data["statement"]["sections"]), 2)
        self.assertEqual(data["statement"]["kpis"][0]["value"], data["summary"]["income"])

    def test_cash_position_builds(self):
        data = build_report("cash_position", self._request(), period="monthly")
        self.assertEqual(data["summary"]["total"], Decimal("100.00"))

    def test_general_ledger_lists_each_line_with_narration(self):
        data = build_report("general_ledger", self._request(), period="monthly")
        self.assertEqual(data["title"], "Detailed Financial Report")
        self.assertEqual(data["summary"]["journal_count"], 1)
        self.assertEqual(data["summary"]["line_count"], 2)
        self.assertEqual(data["summary"]["total_debit"], data["summary"]["total_credit"])
        narrations = [row[4] for row in data["rows"]]
        self.assertTrue(all(n == "Seed receipt" for n in narrations))
        self.assertEqual(len(data["ledger"]["journals"]), 1)
        self.assertEqual(data["ledger"]["journals"][0]["narration"], "Seed receipt")
        self.assertEqual(len(data["ledger"]["journals"][0]["lines"]), 2)

    def test_general_ledger_excludes_other_church_and_pending(self):
        other = Church.objects.create(
            name="Other",
            code="CH2",
            district=self.church.district,
        )
        cash = Account.objects.filter(church=other, account_type="CASH").first()
        if not cash:
            cash = Account.objects.create(name="Cash", account_type="CASH", church=other)
        income = Account.objects.filter(church=other, account_type="INCOME").first()
        if not income:
            income = Account.objects.create(name="Income", account_type="INCOME", church=other)
        foreign = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=other,
            created_by=self.treasury,
            description="Foreign receipt",
            approval_status="APPROVED",
        )
        TransactionLine.objects.create(transaction=foreign, account=cash, amount=Decimal("50.00"))
        TransactionLine.objects.create(transaction=foreign, account=income, amount=Decimal("-50.00"))
        pending = Transaction.objects.create(
            transaction_type="EXPENSE",
            church=self.church,
            created_by=self.treasury,
            description="Pending expense",
            approval_status="PENDING",
        )
        own_cash = Account.objects.filter(church=self.church, account_type="CASH").first()
        own_income = Account.objects.filter(church=self.church, account_type="INCOME").first()
        TransactionLine.objects.create(transaction=pending, account=own_cash, amount=Decimal("-10.00"))
        TransactionLine.objects.create(transaction=pending, account=own_income, amount=Decimal("10.00"))

        data = build_report("general_ledger", self._request(), period="monthly")
        narrations = [row[4] for row in data["rows"]]
        self.assertIn("Seed receipt", narrations)
        self.assertNotIn("Foreign receipt", narrations)
        self.assertNotIn("Pending expense", narrations)
