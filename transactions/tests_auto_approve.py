"""Regression tests for P0-11 — module journals must not bypass txn approval."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from approvals.services import create_delegation
from organization.models import Church, Conference, District, Zone
from payroll.models import PayComponentType, PayrollRun
from payroll.services import (
    PayrollError,
    approve_payroll_run,
    calculate_payroll_run,
    create_payroll_run,
    pay_payroll_run,
    post_payroll_run,
    treasury_approve_payroll_run,
)
from permissions.org_scope import apply_org_scope
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from remittance.services import (
    RemittancePolicyError,
    create_settlement_draft,
    post_settlement_batch,
)
from sitecontrol.models import Denomination
from transactions.models import FinancialAuditLog, Transaction, TreasuryApprovalPolicy
from transactions.services import (
    approve_module_journal,
    approve_transaction,
    get_or_create_treasury_approval_policy,
    open_working_day,
    record_receipt,
    resolve_authorized_journal_checker,
    resolve_journal_checker,
)

User = get_user_model()


def _require_second_approval(church):
    """Force receipts to stay PENDING (limit 0)."""
    policy = get_or_create_treasury_approval_policy(church)
    policy.receipt_auto_approve_enabled = True
    policy.default_receipt_auto_approve_limit = Decimal("0.00")
    policy.save(update_fields=["receipt_auto_approve_enabled", "default_receipt_auto_approve_limit"])


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
        _require_second_approval(self.church)

    def test_maker_cannot_approve_own_transaction(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("25.00"),
        )
        self.assertEqual(txn.approval_status, "PENDING")
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.treasurer)

    def test_maker_cannot_reject_own_transaction(self):
        from transactions.services import reject_transaction

        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("25.00"),
        )
        with self.assertRaises(ValueError):
            reject_transaction(txn, self.treasurer)

    def test_maker_cannot_void_own_transaction(self):
        from transactions.services import void_transaction

        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("25.00"),
        )
        approve_transaction(txn, self.pastor)
        txn.refresh_from_db()
        with self.assertRaises(ValueError):
            void_transaction(txn, self.treasurer)

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
        # Already-approved journals are idempotent (e.g. after receipt auto-approve).
        again = approve_transaction(txn, self.pastor)
        self.assertEqual(again.pk, txn.pk)
        self.assertEqual(again.approval_status, "APPROVED")

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

class ReceiptAutoApprovePolicyTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="RCP Conf", code="RC")
        zone = Zone.objects.create(name="RCP Zone", code="RZ", conference=conf)
        district = District.objects.create(name="RCP District", code="RD", zone=zone)
        self.church = Church.objects.create(name="RCP Church", code="RCH", district=district)
        self.treasurer = User.objects.create_user(
            username="rcp_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="rcp_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_default_unlimited_auto_approves_receipt(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
        )
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)
        self.assertEqual(txn.approved_by_id, self.treasurer.id)
        audit = FinancialAuditLog.objects.filter(
            transaction=txn, action="APPROVE"
        ).latest("created_at")
        self.assertTrue((audit.details or {}).get("auto_approved"))

    def test_amount_above_church_limit_stays_pending(self):
        policy = get_or_create_treasury_approval_policy(self.church)
        policy.default_receipt_auto_approve_limit = Decimal("50.00")
        policy.save(update_fields=["default_receipt_auto_approve_limit"])
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("75.00"),
        )
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertFalse(txn.locked)

    def test_user_override_limit_zero_requires_second_approval(self):
        self.treasurer.max_receipt_auto_approve = Decimal("0.00")
        self.treasurer.save(update_fields=["max_receipt_auto_approve"])
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            income_amount=Decimal("5.00"),
        )
        self.assertEqual(txn.approval_status, "PENDING")

    def test_disabled_policy_keeps_pending(self):
        policy = get_or_create_treasury_approval_policy(self.church)
        policy.receipt_auto_approve_enabled = False
        policy.save(update_fields=["receipt_auto_approve_enabled"])
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            combined_amount=Decimal("20.00"),
        )
        self.assertEqual(txn.approval_status, "PENDING")


class AuthorizedModuleJournalCheckerTests(TestCase):
    """CH-ENT-002 — module journals require actor_may_decide for the checker."""

    def setUp(self):
        ensure_permission_matrix()
        self.denomination = Denomination.objects.create(
            code="amj", name="AMJ Denom", is_active=True
        )
        other_denom = Denomination.objects.create(
            code="amjx", name="AMJ Other Denom", is_active=True
        )
        conference = Conference.objects.create(
            name="AMJ Conf", code="AMJC", denomination=self.denomination
        )
        other_conf = Conference.objects.create(
            name="AMJ Other Conf", code="AMJX", denomination=other_denom
        )
        zone = Zone.objects.create(name="AMJ Zone", code="AMJZ", conference=conference)
        other_zone = Zone.objects.create(
            name="AMJ XZone", code="AMJZX", conference=other_conf
        )
        district = District.objects.create(name="AMJ Dist", code="AMJD", zone=zone)
        other_district = District.objects.create(
            name="AMJ Dist 2", code="AMJD2", zone=zone
        )
        x_district = District.objects.create(name="AMJ XDist", code="AMJDX", zone=other_zone)
        self.church = Church.objects.create(name="AMJ Church", code="AMJCH", district=district)
        self.other_church = Church.objects.create(
            name="AMJ Other Church", code="AMJOC", district=other_district
        )
        self.x_church = Church.objects.create(
            name="AMJ Cross Denom", code="AMJXD", district=x_district
        )
        self.treasurer = User.objects.create_user(
            username="amj_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="amj_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.other_pastor = User.objects.create_user(
            username="amj_other_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.other_church,
        )
        self.x_pastor = User.objects.create_user(
            username="amj_x_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.x_church,
        )
        self.district_pastor = User.objects.create_user(
            username="amj_dp",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
        )
        apply_org_scope(
            self.district_pastor,
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
            district=district,
        )
        self.district_pastor.save()
        self.superadmin = User.objects.create_user(
            username="amj_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
            denomination=self.denomination,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        open_working_day(self.other_church, timezone.localdate(), self.other_pastor)
        open_working_day(self.x_church, timezone.localdate(), self.x_pastor)
        _require_second_approval(self.church)

    def _pending(self, maker=None):
        return record_receipt(
            church=self.church,
            created_by=maker or self.treasurer,
            tithe_amount=Decimal("25.00"),
        )

    def test_authorized_in_scope_checker_approves(self):
        txn = self._pending()
        result = approve_module_journal(txn, self.pastor)
        self.assertEqual(result.approval_status, "APPROVED")
        self.assertTrue(result.locked)
        self.assertEqual(result.approved_by_id, self.pastor.id)

    def test_checker_without_approve_transactions_is_rejected(self):
        txn = self._pending(maker=self.pastor)
        result = approve_module_journal(txn, self.treasurer)
        self.assertEqual(result.approval_status, "PENDING")
        self.assertFalse(result.locked)
        self.assertIsNone(result.approved_by_id)

    def test_valid_delegation_authorizes_treasury_checker(self):
        txn = self._pending(maker=self.pastor)
        today = timezone.localdate()
        create_delegation(
            grantor=self.pastor,
            grantee=self.treasurer,
            church=self.church,
            valid_from=today,
            valid_until=today,
            max_amount=Decimal("100.00"),
        )
        result = approve_module_journal(txn, self.treasurer)
        self.assertEqual(result.approval_status, "APPROVED")
        self.assertEqual(result.approved_by_id, self.treasurer.id)

    def test_district_pastor_cannot_be_selected(self):
        txn = self._pending()
        self.assertIsNone(
            resolve_authorized_journal_checker(txn, self.district_pastor)
        )
        result = approve_module_journal(txn, self.district_pastor)
        self.assertEqual(result.approval_status, "PENDING")
        self.assertFalse(result.locked)

    def test_cross_district_and_cross_denomination_candidates_rejected(self):
        txn = self._pending()
        self.assertIsNone(
            resolve_authorized_journal_checker(txn, self.other_pastor, self.x_pastor)
        )
        result = approve_module_journal(txn, self.other_pastor, self.x_pastor)
        self.assertEqual(result.approval_status, "PENDING")
        self.assertFalse(result.locked)

    def test_ineligible_first_candidate_skipped_when_later_eligible(self):
        txn = self._pending()
        checker = resolve_authorized_journal_checker(
            txn, self.treasurer, self.district_pastor, self.pastor
        )
        self.assertEqual(checker.pk, self.pastor.pk)
        result = approve_module_journal(
            txn, self.treasurer, self.district_pastor, self.pastor
        )
        self.assertEqual(result.approval_status, "APPROVED")
        self.assertEqual(result.approved_by_id, self.pastor.id)

    def test_no_eligible_checker_fails_closed(self):
        txn = self._pending()
        result = approve_module_journal(txn, self.treasurer, self.district_pastor)
        self.assertEqual(result.approval_status, "PENDING")
        self.assertFalse(result.locked)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertFalse(txn.locked)
        self.assertFalse(
            FinancialAuditLog.objects.filter(
                transaction=txn,
                action="APPROVE",
            ).exists()
        )

    def test_maker_cannot_approve_own_module_journal_including_superadmin(self):
        txn = self._pending()
        result = approve_module_journal(txn, self.treasurer)
        self.assertEqual(result.approval_status, "PENDING")
        sa_txn = record_receipt(
            church=self.church,
            created_by=self.superadmin,
            tithe_amount=Decimal("12.00"),
        )
        sa_result = approve_module_journal(sa_txn, self.superadmin)
        self.assertEqual(sa_result.approval_status, "PENDING")
        self.assertFalse(sa_result.locked)
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.treasurer)
        approved = approve_transaction(sa_txn, self.superadmin)
        self.assertEqual(approved.approval_status, "APPROVED")
