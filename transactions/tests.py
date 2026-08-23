"""Tests for financial integrity and services."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from transactions.models import Account, BankReconciliation, FinancialAuditLog, FinancialPeriod, Transaction
from transactions.services import (
    approve_transaction,
    close_working_day,
    create_bank_reconciliation,
    finalize_bank_reconciliation,
    generate_monthly_cutoff,
    lock_financial_period,
    open_working_day,
    record_district_remittance,
    record_expense,
    record_receipt,
    record_transfer,
    unlock_financial_period,
    update_reconciliation_matches,
    validate_transaction_balance,
    void_transaction,
    WorkingDayClosedError,
)

User = get_user_model()


class FinancialServicesTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Test Conf", code="TC")
        zone = Zone.objects.create(name="Zone 1", code="Z1", conference=conf)
        district = District.objects.create(name="District 1", code="D1", zone=zone)
        self.church = Church.objects.create(name="Church 1", code="C1", district=district)
        # Signal auto-creates accounts and offering categories on church save
        self.treasurer = User.objects.create_user(
            username="treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_receipt_is_balanced(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
            combined_amount=Decimal("50.00"),
            income_amount=Decimal("25.00"),
        )
        validate_transaction_balance(txn)
        total = sum(line.amount for line in txn.lines.all())
        self.assertEqual(total, Decimal("0.00"))
        lines_by_type = {
            line.account.account_type: line.amount
            for line in txn.lines.select_related("account")
        }
        self.assertEqual(lines_by_type["CASH"], Decimal("175.00"))
        self.assertEqual(lines_by_type["TITHE_REMIT_PAYABLE"], Decimal("-100.00"))
        self.assertEqual(lines_by_type["COMBINED_RETENTION"], Decimal("-25.00"))
        self.assertEqual(lines_by_type["COMBINED_REMIT_PAYABLE"], Decimal("-25.00"))
        self.assertEqual(lines_by_type["INCOME"], Decimal("-25.00"))

    def test_record_receipt_by_category_sets_accounts_and_description(self):
        from ledger.models import LedgerCategory
        from ledger.services import seed_ledger
        from members.models import Member
        from transactions.services import record_receipt_by_category

        seed_ledger(self.church)
        category = LedgerCategory.objects.get(church=self.church, code="REC_YOUTH_CASH")
        member = Member.objects.create(
            church=self.church,
            first_name="Ada",
            last_name="Youth",
            gender="F",
            membership_number="YH-1",
        )
        txn = record_receipt_by_category(
            church=self.church,
            created_by=self.treasurer,
            category=category,
            amount=Decimal("40.00"),
            description="Youth Sabbath offering",
            member=member,
        )
        validate_transaction_balance(txn)
        self.assertEqual(txn.ledger_category_id, category.pk)
        self.assertEqual(txn.description, "Youth Sabbath offering")
        self.assertEqual(txn.member_id, member.pk)
        debit = txn.lines.get(amount__gt=0)
        credit = txn.lines.get(amount__lt=0)
        self.assertEqual(debit.account_id, category.default_debit_account_id)
        self.assertEqual(credit.account_id, category.default_credit_account_id)

    def test_record_expense_by_category_sets_accounts_and_description(self):
        from ledger.models import LedgerCategory
        from ledger.services import seed_ledger
        from transactions.services import record_expense_by_category

        seed_ledger(self.church)
        category = LedgerCategory.objects.get(church=self.church, code="EXP_UTIL_CASH")
        txn = record_expense_by_category(
            church=self.church,
            created_by=self.treasurer,
            category=category,
            amount=Decimal("55.00"),
            description="Electricity",
        )
        validate_transaction_balance(txn)
        self.assertEqual(txn.transaction_type, "EXPENSE")
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertEqual(txn.ledger_category_id, category.pk)
        self.assertEqual(txn.description, "Electricity")
        debit = txn.lines.get(amount__gt=0)
        credit = txn.lines.get(amount__lt=0)
        self.assertEqual(debit.account_id, category.default_debit_account_id)
        self.assertEqual(credit.account_id, category.default_credit_account_id)

    def test_record_receipt_by_category_requires_member_when_configured(self):
        from ledger.models import LedgerCategory
        from ledger.services import seed_ledger
        from members.models import Member
        from transactions.services import record_receipt_by_category

        seed_ledger(self.church)
        category = LedgerCategory.objects.get(church=self.church, code="REC_PLEDGE_CASH")
        self.assertTrue(category.requires_member)
        with self.assertRaises(ValueError):
            record_receipt_by_category(
                church=self.church,
                created_by=self.treasurer,
                category=category,
                amount=Decimal("10.00"),
                description="Pledge without member",
            )
        member = Member.objects.create(
            church=self.church,
            first_name="Ben",
            last_name="Pledge",
            gender="M",
            membership_number="PL-1",
        )
        txn = record_receipt_by_category(
            church=self.church,
            created_by=self.treasurer,
            category=category,
            amount=Decimal("10.00"),
            description="Pledge with member",
            member=member,
        )
        self.assertEqual(txn.member_id, member.pk)

    def test_record_receipt_by_category_rejects_foreign_church_category(self):
        from ledger.models import LedgerCategory
        from ledger.services import seed_ledger
        from transactions.services import record_receipt_by_category

        other = Church.objects.create(
            name="Church 2",
            code="C2",
            district=self.church.district,
        )
        seed_ledger(self.church)
        seed_ledger(other)
        foreign = LedgerCategory.objects.get(church=other, code="REC_INCOME_CASH")
        with self.assertRaises(ValueError):
            record_receipt_by_category(
                church=self.church,
                created_by=self.treasurer,
                category=foreign,
                amount=Decimal("5.00"),
                description="Cross-tenant attempt",
            )

    def test_expense_is_balanced(self):
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("75.00"),
        )
        validate_transaction_balance(txn)

    def test_transfer_is_balanced(self):
        record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("500.00"),
        )
        txn = record_transfer(
            church=self.church,
            created_by=self.treasurer,
            from_account_type="CASH",
            to_account_type="BANK",
            amount=Decimal("200.00"),
        )
        validate_transaction_balance(txn)

    def test_creator_cannot_approve_own_transaction(self):
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("10.00"),
        )
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.treasurer)

    def test_approver_can_approve_transaction(self):
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("10.00"),
        )
        approve_transaction(txn, self.pastor)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)
        self.assertTrue(
            FinancialAuditLog.objects.filter(transaction=txn, action="APPROVE").exists()
        )

    def test_default_accounts_created(self):
        types = set(
            Account.objects.filter(church=self.church).values_list("account_type", flat=True)
        )
        self.assertIn("TITHE", types)
        self.assertIn("CASH", types)
        self.assertIn("BANK", types)

    def test_monthly_cutoff_and_remittance(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
            combined_amount=Decimal("50.00"),
        )
        approve_transaction(txn, self.pastor)
        month = timezone.now().date()
        cutoff = generate_monthly_cutoff(self.church, month)
        self.assertEqual(cutoff.total_tithe, Decimal("100.00"))
        self.assertEqual(cutoff.total_combined, Decimal("25.00"))

        remit = record_district_remittance(
            church=self.church,
            created_by=self.pastor,
            amount=cutoff.total_payable,
            month_date=month,
        )
        validate_transaction_balance(remit)
        approve_transaction(remit, self.treasurer)
        cutoff.refresh_from_db()
        self.assertTrue(cutoff.transferred)

    def test_void_creates_balanced_reversal(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("100.00"),
        )
        approve_transaction(txn, self.pastor)
        reversed_txn = void_transaction(txn, self.pastor, reason="Error")
        txn.refresh_from_db()
        self.assertEqual(reversed_txn.pk, txn.pk)
        self.assertTrue(txn.is_voided)
        self.assertEqual(txn.approval_status, "REVERSED")
        self.assertFalse(
            Transaction.objects.filter(reversal_of=txn).exists()
        )
        self.assertTrue(
            FinancialAuditLog.objects.filter(transaction=txn, action="VOID").exists()
        )

    def test_remove_void_pairs_keeps_good_journals(self):
        from django.core.management import call_command
        from io import StringIO
        from transactions.models import Transaction

        keep = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("40.00"),
        )
        approve_transaction(keep, self.pastor)
        voided = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("25.00"),
        )
        approve_transaction(voided, self.pastor)
        void_transaction(voided, self.pastor, reason="Mistake")

        out = StringIO()
        call_command(
            "remove_void_pairs",
            church=self.church.name,
            execute=True,
            stdout=out,
        )
        self.assertTrue(Transaction.objects.filter(pk=keep.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=voided.pk).exists())

    def test_period_lock_blocks_receipt(self):
        today = timezone.now().date()
        lock_financial_period(self.church, today.year, today.month, self.pastor)
        from transactions.services import PeriodLockedError
        with self.assertRaises(PeriodLockedError):
            record_receipt(
                church=self.church,
                created_by=self.treasurer,
                income_amount=Decimal("50.00"),
            )

    def test_period_unlock(self):
        today = timezone.now().date()
        lock_financial_period(self.church, today.year, today.month, self.pastor)
        unlock_financial_period(self.church, today.year, today.month, self.pastor)
        period = FinancialPeriod.objects.get(church=self.church, year=today.year, month=today.month)
        self.assertFalse(period.is_locked)

    def test_bank_reconciliation_flow(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("300.00"),
            payment_account_type="BANK",
        )
        approve_transaction(txn, self.pastor)
        bank = Account.objects.get(church=self.church, account_type="BANK")
        today = timezone.now().date()
        recon = create_bank_reconciliation(
            church=self.church,
            bank_account=bank,
            statement_date=today,
            statement_balance=Decimal("300.00"),
            user=self.pastor,
        )
        line_id = recon.items.first().transaction_line_id
        update_reconciliation_matches(recon, [line_id], self.pastor)
        finalize_bank_reconciliation(recon, self.pastor)
        recon.refresh_from_db()
        self.assertTrue(recon.is_reconciled)


class FinancialWorkflowIntegrationTests(FinancialServicesTests):
    """End-to-end service-layer flows across receipt, approval, cutoff, and budget."""

    def test_receipt_approve_cutoff_and_budget_actual(self):
        from transactions.models import Budget
        from transactions.services import budget_vs_actual

        tithe = Decimal("150.00")
        combined = Decimal("75.00")
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=tithe,
            combined_amount=combined,
        )
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)
        # Idempotent if already auto-approved under receipt policy.
        approve_transaction(txn, self.pastor)

        month = timezone.now().date()
        cutoff = generate_monthly_cutoff(self.church, month)
        self.assertEqual(cutoff.total_tithe, tithe)
        self.assertEqual(cutoff.total_combined, combined / 2)
        self.assertGreater(cutoff.total_payable, Decimal("0"))

        tithe_account = Account.objects.get(church=self.church, account_type="TITHE_REMIT_PAYABLE")
        Budget.objects.create(
            church=self.church,
            level="CHURCH",
            year=month.year,
            account=tithe_account,
            amount=Decimal("200.00"),
        )
        rows = budget_vs_actual(self.church, month.year)
        tithe_row = next(r for r in rows if r["account"] == tithe_account.name)
        self.assertEqual(tithe_row["actual"], tithe)
        self.assertEqual(tithe_row["budgeted"], Decimal("200.00"))

    def test_expense_approve_then_void_restores_integrity(self):
        from transactions.models import Transaction

        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("40.00"),
            description="Supplies",
        )
        approve_transaction(txn, self.pastor)
        reversed_txn = void_transaction(txn, self.pastor, reason="Duplicate entry")
        txn.refresh_from_db()
        self.assertEqual(reversed_txn.pk, txn.pk)
        self.assertTrue(txn.is_voided)
        self.assertEqual(txn.approval_status, "REVERSED")
        self.assertFalse(Transaction.objects.filter(reversal_of=txn).exists())


class TransactionViewTests(FinancialServicesTests):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="pastor", password="pass12345")

    def test_period_list_accessible(self):
        response = self.client.get(reverse("transactions:period_list"))
        self.assertEqual(response.status_code, 200)

    def test_transaction_list_accessible(self):
        response = self.client.get(reverse("transactions:transaction_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All Transactions")
        self.assertContains(response, "Print")
        self.assertNotContains(response, "badge bg-")

    def test_transaction_list_defaults_to_business_date(self):
        from transactions.services import resolve_transaction_date

        business = resolve_transaction_date(self.church)
        response = self.client.get(reverse("transactions:transaction_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_from"], business)
        self.assertEqual(response.context["date_to"], business)

    def test_transaction_list_export_csv(self):
        response = self.client.get(
            reverse("transactions:transaction_list"),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Reference,Date,Type,Status", response.content.decode("utf-8"))

    def test_reconciliation_list_accessible(self):
        response = self.client.get(reverse("transactions:reconciliation_list"))
        self.assertEqual(response.status_code, 200)

    def test_record_expense_page_has_category_search(self):
        from ledger.services import seed_ledger
        from transactions.services import create_default_accounts

        create_default_accounts(self.church)
        seed_ledger(self.church)
        response = self.client.get(reverse("transactions:record_expense"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js-category-picker")
        self.assertContains(response, "Type to search categories")
        self.assertContains(response, "preview-debit")
        self.assertContains(response, "preview-credit")
        self.assertContains(response, "expense-category-data")

    def test_remittance_payment_get_not_405(self):
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()
        response = self.client.get(reverse("transactions:record_remittance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remittance Payment")


class TransactionPostPermissionTests(TestCase):
    """Regression: POST handlers use granular finance permissions, not approve-only."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        conf = Conference.objects.create(name="Perm Conf", code="PCONF")
        zone = Zone.objects.create(name="Perm Zone", code="PZON", conference=conf)
        district = District.objects.create(name="Perm District", code="PDIS", zone=zone)
        cls.church = Church.objects.create(name="Perm Church", code="PCH", district=district)
        cls.treasurer = User.objects.create_user(
            username="perm_treasury",
            password="pass12345",
            role="TREASURY",
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="perm_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=cls.church,
        )

    def setUp(self):
        self.client = Client()
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def _login_church(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()

    def _approved_receipt(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("50.00"),
        )
        approve_transaction(txn, self.pastor)
        return txn

    def test_treasurer_with_manage_finances_cannot_void_via_post(self):
        txn = self._approved_receipt()
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:void_transaction", kwargs={"pk": txn.pk}),
            {"reason": "Unauthorized void attempt"},
        )
        self.assertEqual(response.status_code, 403)
        txn.refresh_from_db()
        self.assertFalse(txn.is_voided)

    def test_approver_denied_void_cannot_void_via_post(self):
        from permissions.models import Permission
        from permissions.services import create_override

        void_perm = Permission.objects.get(codename="void_transactions")
        create_override(self.pastor, void_perm, granted=False, reason="Separation of duties")
        txn = self._approved_receipt()
        self._login_church("perm_pastor")
        response = self.client.post(
            reverse("transactions:void_transaction", kwargs={"pk": txn.pk}),
            {"reason": "Should be blocked"},
        )
        self.assertEqual(response.status_code, 403)
        txn.refresh_from_db()
        self.assertFalse(txn.is_voided)

    def test_void_grant_without_approve_can_void_via_post(self):
        from permissions.models import Permission
        from permissions.services import create_override

        void_perm = Permission.objects.get(codename="void_transactions")
        create_override(self.treasurer, void_perm, granted=True, reason="Void-only delegate")
        txn = self._approved_receipt()
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:void_transaction", kwargs={"pk": txn.pk}),
            {"reason": "Correcting duplicate entry"},
        )
        self.assertEqual(response.status_code, 302)
        txn.refresh_from_db()
        self.assertTrue(txn.is_voided)

    def test_treasurer_cannot_open_working_day_via_post(self):
        close_working_day(self.church, self.pastor)
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:working_day_open"),
            {"date": timezone.localdate().isoformat(), "notes": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_treasurer_cannot_lock_period_via_post(self):
        today = timezone.localdate()
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:period_lock"),
            {"year": today.year, "month": today.month, "notes": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_treasurer_cannot_unlock_period_via_post(self):
        today = timezone.localdate()
        lock_financial_period(self.church, today.year, today.month, self.pastor)
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:period_unlock"),
            {"year": today.year, "month": today.month},
        )
        self.assertEqual(response.status_code, 403)

    def test_local_pastor_cannot_unlock_period_via_post(self):
        today = timezone.localdate()
        lock_financial_period(self.church, today.year, today.month, self.pastor)
        self._login_church("perm_pastor")
        response = self.client.post(
            reverse("transactions:period_unlock"),
            {"year": today.year, "month": today.month},
        )
        self.assertEqual(response.status_code, 403)

    def test_unlock_grant_can_unlock_period_via_post(self):
        from permissions.models import Permission
        from permissions.services import create_override

        today = timezone.localdate()
        lock_financial_period(self.church, today.year, today.month, self.pastor)
        unlock_perm = Permission.objects.get(codename="unlock_periods")
        create_override(self.treasurer, unlock_perm, granted=True, reason="Period unlock delegate")
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:period_unlock"),
            {"year": today.year, "month": today.month},
        )
        self.assertEqual(response.status_code, 302)
        period = FinancialPeriod.objects.get(church=self.church, year=today.year, month=today.month)
        self.assertFalse(period.is_locked)

    def test_pastor_can_lock_period_via_post(self):
        today = timezone.localdate()
        self._login_church("perm_pastor")
        response = self.client.post(
            reverse("transactions:period_lock"),
            {"year": today.year, "month": today.month, "notes": ""},
        )
        self.assertEqual(response.status_code, 302)

    def test_record_receipt_lands_on_confirmation_page(self):
        from ledger.models import LedgerCategory
        from ledger.services import seed_ledger
        from transactions.services import create_default_accounts

        create_default_accounts(self.church)
        seed_ledger(self.church)
        category = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:record_receipt"),
            {
                "idempotency_key": "confirm-receipt-key-1",
                "category": str(category.pk),
                "amount": "25.00",
                "description": "Confirmation slip test",
                "date": timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/transactions/confirm/", response["Location"])
        self.assertIn("new=1", response["Location"])
        confirm = self.client.get(response["Location"])
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Transaction confirmed")
        self.assertContains(confirm, "Print confirmation")

    def test_classic_record_receipt_still_works(self):
        from transactions.services import create_default_accounts

        create_default_accounts(self.church)
        self._login_church("perm_treasury")
        response = self.client.post(
            reverse("transactions:record_receipt") + "?classic=1",
            {
                "classic": "1",
                "idempotency_key": "classic-receipt-key-1",
                "tithe_amount": "0",
                "combined_amount": "0",
                "income_amount": "15.00",
                "payment_account_type": "CASH",
                "description": "Classic mode",
                "date": timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/transactions/confirm/", response["Location"])

    def test_pastor_retains_void_and_working_day_post_access(self):
        today = timezone.localdate()
        txn = self._approved_receipt()
        close_working_day(self.church, self.pastor)
        self._login_church("perm_pastor")

        open_response = self.client.post(
            reverse("transactions:working_day_open"),
            {"date": today.isoformat(), "notes": "Re-open"},
        )
        self.assertEqual(open_response.status_code, 302)

        void_response = self.client.post(
            reverse("transactions:void_transaction", kwargs={"pk": txn.pk}),
            {"reason": "Pastor void"},
        )
        self.assertEqual(void_response.status_code, 302)
        txn.refresh_from_db()
        self.assertTrue(txn.is_voided)


class SecurityAndIntegrityTests(FinancialServicesTests):
    def test_missing_idempotency_key_rejected(self):
        from transactions.idempotency import MissingIdempotencyKey, claim_financial_idempotency

        with self.assertRaises(MissingIdempotencyKey):
            claim_financial_idempotency(self.church, self.treasurer, "RECEIPT", "")

    def test_duplicate_remittance_blocked_while_pending(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
        )
        approve_transaction(txn, self.pastor)
        month = timezone.now().date()
        cutoff = generate_monthly_cutoff(self.church, month)
        record_district_remittance(
            church=self.church,
            created_by=self.pastor,
            amount=cutoff.total_payable,
            month_date=month,
        )
        with self.assertRaises(ValueError):
            record_district_remittance(
                church=self.church,
                created_by=self.pastor,
                amount=cutoff.total_payable,
                month_date=month,
            )

    def test_duplicate_remittance_blocked_after_transfer(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("50.00"),
        )
        approve_transaction(txn, self.pastor)
        month = timezone.now().date()
        cutoff = generate_monthly_cutoff(self.church, month)
        remit = record_district_remittance(
            church=self.church,
            created_by=self.pastor,
            amount=cutoff.total_payable,
            month_date=month,
        )
        approve_transaction(remit, self.treasurer)
        cutoff.refresh_from_db()
        self.assertTrue(cutoff.transferred)
        with self.assertRaises(ValueError):
            record_district_remittance(
                church=self.church,
                created_by=self.pastor,
                amount=cutoff.total_payable,
                month_date=month,
            )

    def test_transaction_line_rejects_cross_church_account(self):
        from organization.models import Conference, District, Zone

        conf2 = Conference.objects.create(name="Other Conf", code="OC2")
        zone2 = Zone.objects.create(name="Z2", code="Z2", conference=conf2)
        district2 = District.objects.create(name="D2", code="D2", zone=zone2)
        other_church = Church.objects.create(name="Other Church", code="OC1", district=district2)
        other_account = Account.objects.filter(church=other_church, account_type="EXPENSE").first()
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("10.00"),
        )
        from transactions.services import _post_line

        with self.assertRaises(ValueError):
            _post_line(txn, other_account, Decimal("5.00"))

    def test_void_reverses_welfare_contribution(self):
        from members.models import Member
        from remittance.models import WelfareContribution

        member = Member.objects.create(
            church=self.church,
            first_name="Jane",
            last_name="Doe",
            gender="Female",
        )
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            special_offerings={"WELFARE": Decimal("25.00")},
            member=member,
        )
        approve_transaction(txn, self.pastor)
        self.assertTrue(WelfareContribution.objects.filter(transaction=txn).exists())
        void_transaction(txn, self.pastor, reason="Error")
        self.assertFalse(WelfareContribution.objects.filter(transaction=txn).exists())

    def test_reference_uses_transaction_date(self):
        from datetime import date

        from transactions.models import Transaction

        txn = Transaction(
            transaction_type="RECEIPT",
            church=self.church,
            created_by=self.treasurer,
            date=date(2024, 3, 15),
        )
        txn.save()
        self.assertTrue(txn.reference.startswith("REC-C1-2024-03"))


class CrossChurchViewTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Test Conf", code="TC")
        zone = Zone.objects.create(name="Zone 1", code="Z1", conference=conf)
        district = District.objects.create(name="District 1", code="D1", zone=zone)
        self.church = Church.objects.create(name="Church 1", code="C1", district=district)
        self.treasurer = User.objects.create_user(
            username="treasury_x",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pastor_x",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

        from organization.models import Conference as Conf

        conf2 = Conf.objects.create(name="Conf B", code="CB")
        zone2 = Zone.objects.create(name="ZB", code="ZB", conference=conf2)
        district2 = District.objects.create(name="DB", code="DB", zone=zone2)
        self.other_church = Church.objects.create(name="Church B", code="CB1", district=district2)
        open_working_day(self.other_church, timezone.localdate(), self.pastor)
        self.other_treasurer = User.objects.create_user(
            username="treasury_b",
            password="pass12345",
            role="TREASURY",
            church=self.other_church,
        )
        self.other_txn = record_expense(
            church=self.other_church,
            created_by=self.other_treasurer,
            amount=Decimal("20.00"),
        )
        self.client = Client()
        self.client.login(username="pastor_x", password="pass12345")

    def test_cannot_approve_other_church_transaction(self):
        response = self.client.post(
            reverse("transactions:approve_transaction", kwargs={"pk": self.other_txn.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.other_txn.refresh_from_db()
        self.assertEqual(self.other_txn.approval_status, "PENDING")

    def test_financial_dashboard_export_csv(self):
        response = self.client.get(
            reverse("transactions:financial_dashboard"),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
