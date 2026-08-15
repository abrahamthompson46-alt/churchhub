"""Regression tests for welfare disbursement lock / concurrency (P0 follow-up)."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from remittance.models import WelfareAssistanceCase, WelfareMemberLedger
from remittance.services import RemittancePolicyError, approve_welfare_case
from remittance.welfare_services import (
    create_welfare_case,
    disburse_welfare_case,
    send_welfare_case_to_review,
)
from transactions.models import FinancialAuditLog, Transaction
from transactions.services import approve_transaction, open_working_day, record_receipt

User = get_user_model()


class WelfareDisburseBase:
    def _seed(self):
        conf = Conference.objects.create(name="Disb Conf", code="DC")
        zone = Zone.objects.create(name="Disb Zone", code="DZ", conference=conf)
        district = District.objects.create(name="Disb Dist", code="DD", zone=zone)
        self.church = Church.objects.create(
            name="Disb Church", code="DCH", district=district
        )
        self.treasurer = User.objects.create_user(
            username="disb_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="disb_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        self.reviewer = User.objects.create_user(
            username="disb_reviewer",
            password="pass12345",
            role="BOARD_MEMBER",
            church=self.church,
        )
        self.member = Member.objects.create(
            church=self.church,
            first_name="Ada",
            last_name="Case",
            gender=Gender.FEMALE,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def _fund_and_approve_case(self, amount=Decimal("75.00")):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            special_offerings={"WELFARE": Decimal("500.00")},
            member=self.member,
        )
        approve_transaction(txn, self.pastor)
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=amount,
            reason="Medical",
            user=self.treasurer,
            assistance_type="MEDICAL",
        )
        send_welfare_case_to_review(case, self.reviewer, review_notes="Reviewed")
        approve_welfare_case(case, self.pastor, amount_approved=amount)
        case.refresh_from_db()
        return case


class WelfareDisburseTests(WelfareDisburseBase, TestCase):
    def setUp(self):
        self._seed()

    def test_successful_disbursement(self):
        case = self._fund_and_approve_case()
        case, trx = disburse_welfare_case(case, self.treasurer)
        self.assertEqual(case.status, "DISBURSED")
        self.assertTrue(trx.locked)
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertEqual(trx.lines.count(), 2)
        self.assertEqual(trx.created_by_id, self.pastor.id)
        self.assertEqual(trx.approved_by_id, self.treasurer.id)
        self.assertEqual(
            WelfareMemberLedger.objects.filter(
                case=case, entry_type="DISBURSEMENT"
            ).count(),
            1,
        )
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                transaction=trx,
                action="CREATE",
                details__type="WELFARE_DISBURSEMENT",
            ).exists()
        )

    def test_duplicate_submission_rejected(self):
        case = self._fund_and_approve_case()
        disburse_welfare_case(case, self.treasurer)
        with self.assertRaises(RemittancePolicyError) as ctx:
            disburse_welfare_case(case, self.treasurer)
        self.assertIn("already been disbursed", str(ctx.exception).lower())
        self.assertEqual(
            Transaction.objects.filter(
                description__startswith="Welfare assistance —"
            ).count(),
            1,
        )
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                church=self.church,
                details__type="WELFARE_DISBURSE_REJECTED",
            ).exists()
        )

    def test_posting_failure_rolls_back_all_changes(self):
        case = self._fund_and_approve_case()
        with patch(
            "transactions.services.validate_transaction_balance",
            side_effect=ValueError("forced imbalance"),
        ):
            with self.assertRaises(ValueError):
                disburse_welfare_case(case, self.treasurer)
        case.refresh_from_db()
        self.assertEqual(case.status, "APPROVED")
        self.assertIsNone(case.disbursement_transaction_id)
        self.assertFalse(
            Transaction.objects.filter(
                description__startswith="Welfare assistance —"
            ).exists()
        )
        self.assertFalse(
            WelfareMemberLedger.objects.filter(
                case=case, entry_type="DISBURSEMENT"
            ).exists()
        )

    def test_audit_records_created_correctly(self):
        case = self._fund_and_approve_case()
        case, trx = disburse_welfare_case(case, self.treasurer)
        success = FinancialAuditLog.objects.get(
            transaction=trx, action="CREATE"
        )
        self.assertEqual(success.details.get("type"), "WELFARE_DISBURSEMENT")
        self.assertEqual(success.details.get("case_number"), case.case_number)

        with self.assertRaises(RemittancePolicyError):
            disburse_welfare_case(case, self.treasurer)
        rejected = FinancialAuditLog.objects.filter(
            church=self.church,
            details__type="WELFARE_DISBURSE_REJECTED",
        ).latest("created_at")
        self.assertEqual(rejected.details.get("case_id"), str(case.pk))
        self.assertEqual(rejected.performed_by_id, self.treasurer.id)


class WelfareDisburseConcurrencyTests(WelfareDisburseBase, TransactionTestCase):
    def setUp(self):
        self._seed()

    def test_concurrent_submission_protection(self):
        """Second caller blocked while first holds select_for_update lock."""
        case = self._fund_and_approve_case()
        results = {"ok": 0, "err": 0}

        def worker():
            try:
                with db_transaction.atomic():
                    disburse_welfare_case(case, self.treasurer)
                results["ok"] += 1
            except RemittancePolicyError:
                results["err"] += 1

        # Sequential under lock simulation: first succeeds, second fails.
        worker()
        worker()
        self.assertEqual(results["ok"], 1)
        self.assertEqual(results["err"], 1)
        self.assertEqual(
            WelfareAssistanceCase.objects.get(pk=case.pk).status, "DISBURSED"
        )
        self.assertEqual(
            Transaction.objects.filter(
                description__startswith="Welfare assistance —"
            ).count(),
            1,
        )
