"""Regression tests for P0-11 — module journals must not bypass txn approval."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from payroll.models import PayComponentType, PayrollRun
from payroll.services import (
    approve_payroll_run,
    calculate_payroll_run,
    create_payroll_run,
    pay_payroll_run,
    post_payroll_run,
    treasury_approve_payroll_run,
)
from payroll.services import PayrollError
from remittance.services import (
    RemittancePolicyError,
    create_settlement_draft,
    post_settlement_batch,
)
from transactions.models import FinancialAuditLog, Transaction
from transactions.services import (
    approve_module_journal,
    approve_transaction,
    open_working_day,
    record_receipt,
    resolve_journal_checker,
)

User = get_user_model()


class AutoApproveRegressionTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Auto Conf", code="AC")
        zone = Zone.objects.create(name="Auto Zone", code="AZ", conference=conf)
        district = District.objects.create(name="Auto District", code="AD", zone=zone)
        self.church = Church.objects.create(name="Auto Church", code="ACH", district=district)
        self.treasurer = User.objects.create_user(
            username="auto_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="auto_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_maker_cannot_approve_own_transaction(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("25.00"),
        )
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.treasurer)

    def test_approve_module_journal_skips_self_checker(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            combined_amount=Decimal("10.00"),
        )
        result = approve_module_journal(txn, self.treasurer)
        self.assertEqual(result.approval_status, "PENDING")
        self.assertFalse(result.locked)

    def test_settlement_journal_requires_distinct_checker(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("40.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.localdate()
        batch = create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        with self.assertRaises(RemittancePolicyError):
            post_settlement_batch(batch, self.treasurer)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "DRAFT")

        post_settlement_batch(batch, self.pastor)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "POSTED")
        journal = batch.lines.first().source_transaction
        self.assertEqual(journal.approval_status, "APPROVED")
        self.assertTrue(journal.locked)
        self.assertEqual(journal.created_by_id, self.treasurer.id)
        self.assertEqual(journal.approved_by_id, self.pastor.id)
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                transaction=journal,
                action="APPROVE",
                performed_by=self.pastor,
            ).exists()
        )

    def test_approved_transactions_remain_locked(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("15.00"),
        )
        approve_transaction(txn, self.pastor)
        txn.refresh_from_db()
        self.assertTrue(txn.locked)
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.pastor)

    def test_payroll_workflow_approves_module_journals(self):
        from datetime import date

        from payroll.models import Employee, EmployeeCompensation, EmployeeCompensationLine
        from payroll.services import ensure_payroll_defaults_for_church

        ensure_payroll_defaults_for_church(self.church)
        employee = Employee.objects.create(
            host_church=self.church,
            paying_unit_type="CHURCH",
            paying_unit_id=self.church.pk,
            employee_number="AUTO1",
            first_name="Pat",
            last_name="Worker",
            employment_type="FULL_TIME",
            date_joined=date(2020, 1, 1),
            status="ACTIVE",
        )
        basic = PayComponentType.objects.get(host_church=self.church, code="BASIC")
        comp = EmployeeCompensation.objects.create(
            employee=employee,
            effective_from=date(2020, 1, 1),
            is_active=True,
        )
        EmployeeCompensationLine.objects.create(
            compensation=comp,
            line_type="EARNING",
            pay_component=basic,
            amount=Decimal("2000.00"),
        )

        run = create_payroll_run(self.church, 2026, 7, self.treasurer)
        calculate_payroll_run(run, self.treasurer)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasurer)
        post_payroll_run(run, self.treasurer)
        run.refresh_from_db()
        self.assertEqual(run.status, "POSTED")
        accrual = run.transaction
        self.assertEqual(accrual.approval_status, "APPROVED")
        self.assertTrue(accrual.locked)
        self.assertEqual(accrual.created_by_id, self.treasurer.id)
        self.assertEqual(accrual.approved_by_id, self.pastor.id)

        pay_payroll_run(run, self.treasurer)
        run.refresh_from_db()
        payment = run.payment_transaction
        self.assertEqual(payment.approval_status, "APPROVED")
        self.assertTrue(payment.locked)
        self.assertEqual(payment.approved_by_id, self.pastor.id)

    def test_resolve_journal_checker_prefers_distinct_user(self):
        checker = resolve_journal_checker(
            self.treasurer,
            self.treasurer,
            self.pastor,
        )
        self.assertEqual(checker.pk, self.pastor.pk)

    def test_asset_acquisition_journal_uses_asset_checker(self):
        from datetime import date

        from assets.models import FixedAsset
        from assets.services import approve_asset, ensure_asset_defaults_for_church

        ensure_asset_defaults_for_church(self.church)
        category = self.church.asset_categories.first()
        purchase_date = timezone.localdate()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="ACH-FA-001",
            name="Projector",
            purchase_date=purchase_date,
            acquisition_cost=Decimal("500.00"),
            useful_life_months=36,
            depreciation_method="STRAIGHT_LINE",
            status="PENDING_APPROVAL",
            created_by=self.treasurer,
            submitted_by=self.treasurer,
        )
        approve_asset(asset, self.pastor)
        asset.refresh_from_db()
        journal = asset.acquisition_transaction
        self.assertEqual(journal.approval_status, "APPROVED")
        self.assertTrue(journal.locked)
        self.assertEqual(journal.created_by_id, self.treasurer.id)
        self.assertEqual(journal.approved_by_id, self.pastor.id)
