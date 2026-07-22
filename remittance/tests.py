"""Tests for remittance policy splits, settlements, and welfare."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from remittance.models import RemittancePolicy
from remittance.services import (
    RemittancePolicyError,
    approve_welfare_case,
    calculate_split,
    create_settlement_draft,
    create_welfare_case,
    disburse_welfare_case,
    ensure_hierarchy_settlement_policies,
    get_church_collection_policy,
    post_offering_credit_lines,
    post_settlement_batch,
)
from transactions.models import Account, Transaction, TransactionLine
from transactions.services import (
    approve_transaction,
    open_working_day,
    record_district_remittance,
    record_receipt,
    validate_transaction_balance,
)

User = get_user_model()


class RemittancePolicyTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Test Conf", code="TC")
        zone = Zone.objects.create(name="Zone 1", code="Z1", conference=conf)
        district = District.objects.create(name="District 1", code="D1", zone=zone)
        self.church = Church.objects.create(name="Church 1", code="C1", district=district)
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
        self.member = Member.objects.create(
            church=self.church,
            first_name="Jane",
            last_name="Doe",
            gender=Gender.FEMALE,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_default_church_combined_policy_is_fifty_fifty(self):
        policy = get_church_collection_policy(self.church, "COMBINED")
        self.assertIsNotNone(policy)
        self.assertEqual(policy.retain_percent, Decimal("50.00"))
        self.assertEqual(policy.remit_percent, Decimal("50.00"))

    def test_calculate_split(self):
        retain, remit = calculate_split(Decimal("100.00"), Decimal("50.00"), Decimal("50.00"))
        self.assertEqual(retain, Decimal("50.00"))
        self.assertEqual(remit, Decimal("50.00"))

    def test_combined_receipt_splits_on_gross_collection(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            combined_amount=Decimal("100.00"),
        )
        validate_transaction_balance(txn)
        lines = {
            line.account.account_type: line.amount
            for line in txn.lines.select_related("account")
        }
        self.assertEqual(lines["COMBINED_RETENTION"], Decimal("-50.00"))
        self.assertEqual(lines["COMBINED_REMIT_PAYABLE"], Decimal("-50.00"))

        retention = txn.lines.get(account__account_type="COMBINED_RETENTION")
        remit = txn.lines.get(account__account_type="COMBINED_REMIT_PAYABLE")
        self.assertEqual(retention.fund, "COMBINED_RETENTION")
        self.assertEqual(remit.fund, "COMBINED_TRUST")

    def test_tithe_receipt_posts_to_remit_payable(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("200.00"),
        )
        line = txn.lines.get(account__account_type="TITHE_REMIT_PAYABLE")
        self.assertEqual(line.amount, Decimal("-200.00"))
        self.assertEqual(line.fund, "TITHE_TRUST")

    def test_welfare_receipt_posts_to_welfare_fund(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            special_offerings={"WELFARE": Decimal("80.00")},
            member=self.member,
        )
        line = txn.lines.get(account__account_type="WELFARE_FUND")
        self.assertEqual(line.amount, Decimal("-80.00"))
        self.assertEqual(line.fund, "WELFARE")

    def test_policy_is_configurable_not_hardcoded(self):
        policy = get_church_collection_policy(self.church, "COMBINED")
        policy.retain_percent = Decimal("40.00")
        policy.remit_percent = Decimal("60.00")
        policy.save()

        trx = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=self.church,
            created_by=self.treasurer,
            date=timezone.now().date(),
        )
        TransactionLine.objects.create(
            transaction=trx,
            account=Account.objects.get(church=self.church, name="Cash"),
            amount=Decimal("100.00"),
        )
        retain, remit = post_offering_credit_lines(trx, self.church, "COMBINED", Decimal("100.00"))
        self.assertEqual(retain, Decimal("40.00"))
        self.assertEqual(remit, Decimal("60.00"))

    def test_settlement_draft_from_church_remit_payable(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            combined_amount=Decimal("100.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        batch = create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="COMBINED",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        self.assertEqual(batch.status, "DRAFT")
        self.assertEqual(batch.gross_received, Decimal("50.00"))
        self.assertEqual(batch.remit_amount, Decimal("50.00"))
        self.assertEqual(batch.retain_amount, Decimal("0.00"))

        post_settlement_batch(batch, self.pastor)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "POSTED")

    def test_district_settlement_post_refused_without_gl(self):
        """District+ batches must not become POSTED without a ledger journal."""
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        church_batch = create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        post_settlement_batch(church_batch, self.pastor)

        ensure_hierarchy_settlement_policies(self.church)
        district_batch = create_settlement_draft(
            from_unit_type="DISTRICT",
            from_unit_id=self.church.district.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
        )
        self.assertEqual(district_batch.status, "DRAFT")
        self.assertGreater(district_batch.gross_received, Decimal("0.00"))

        with self.assertRaises(RemittancePolicyError) as ctx:
            post_settlement_batch(district_batch, self.treasurer)
        self.assertIn("not yet implemented", str(ctx.exception).lower())

        district_batch.refresh_from_db()
        self.assertEqual(district_batch.status, "DRAFT")
        self.assertIsNone(district_batch.posted_at)
        self.assertFalse(district_batch.lines.exists())

    def test_hierarchy_settlement_policies_seeded(self):
        created = ensure_hierarchy_settlement_policies(self.church)
        self.assertTrue(created or RemittancePolicy.objects.filter(
            unit_type="DISTRICT",
            unit_id=self.church.district.pk,
            application_scope="SETTLEMENT_FROM_BELOW",
        ).exists())

    def test_welfare_case_workflow(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            special_offerings={"WELFARE": Decimal("500.00")},
        )
        approve_transaction(txn, self.pastor)
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("100.00"),
            reason="Medical support",
            user=self.treasurer,
        )
        self.assertEqual(case.status, "PENDING")

        approve_welfare_case(case, self.pastor, amount_approved=Decimal("75.00"))
        case.refresh_from_db()
        self.assertEqual(case.status, "APPROVED")
        self.assertEqual(case.amount_approved, Decimal("75.00"))

        case, trx = disburse_welfare_case(case, self.treasurer)
        self.assertEqual(case.status, "DISBURSED")
        validate_transaction_balance(trx)
        self.assertEqual(trx.lines.count(), 2)
        welfare_line = trx.lines.get(account__account_type="WELFARE_FUND")
        cash_line = trx.lines.get(account__account_type="CASH")
        self.assertEqual(welfare_line.amount, Decimal("75.00"))
        self.assertEqual(cash_line.amount, Decimal("-75.00"))

    def test_missing_policy_raises(self):
        RemittancePolicy.objects.filter(
            unit_type="CHURCH",
            unit_id=self.church.pk,
            offering_type="COMBINED",
        ).delete()
        with self.assertRaises(RemittancePolicyError):
            record_receipt(
                church=self.church,
                created_by=self.treasurer,
                combined_amount=Decimal("10.00"),
            )

    def test_duplicate_settlement_blocked(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("50.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        kwargs = dict(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        create_settlement_draft(**kwargs)
        with self.assertRaises(RemittancePolicyError):
            create_settlement_draft(**kwargs)

    def test_settlement_blocked_after_bank_remittance(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        remit = record_district_remittance(
            church=self.church,
            created_by=self.pastor,
            amount=Decimal("0.00"),
            month_date=today,
        )
        approve_transaction(remit, self.treasurer)
        with self.assertRaises(RemittancePolicyError) as ctx:
            create_settlement_draft(
                from_unit_type="CHURCH",
                from_unit_id=self.church.pk,
                offering_type="TITHE",
                period_start=today.replace(day=1),
                period_end=today,
                user=self.treasurer,
                church=self.church,
            )
        self.assertIn("monthly cut-off", str(ctx.exception).lower())

    def test_bank_remittance_blocked_after_posted_settlement(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("80.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        batch = create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        post_settlement_batch(batch, self.pastor)
        with self.assertRaises(ValueError) as ctx:
            record_district_remittance(
                church=self.church,
                created_by=self.pastor,
                amount=Decimal("0.00"),
                month_date=today,
            )
        self.assertIn("settlement batch", str(ctx.exception).lower())

    def test_draft_settlement_does_not_block_bank_remittance(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("60.00"),
        )
        approve_transaction(txn, self.pastor)
        today = timezone.now().date()
        create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=today.replace(day=1),
            period_end=today,
            user=self.treasurer,
            church=self.church,
        )
        remit = record_district_remittance(
            church=self.church,
            created_by=self.pastor,
            amount=Decimal("0.00"),
            month_date=today,
        )
        self.assertEqual(remit.transaction_type, "TRANSFER")

