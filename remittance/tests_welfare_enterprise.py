"""Enterprise welfare ledger and workflow tests."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from remittance.models import WelfareMemberLedger
from remittance.services import RemittancePolicyError, approve_welfare_case
from remittance.welfare_services import (
    assert_welfare_fund_sufficient,
    create_welfare_case,
    disburse_welfare_case,
    get_welfare_fund_balance,
    member_welfare_summary,
    record_manual_welfare_contribution,
    send_welfare_case_to_review,
)
from transactions.services import approve_transaction, open_working_day, record_receipt

User = get_user_model()


class WelfareEnterpriseTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Welfare Conf", code="WC")
        zone = Zone.objects.create(name="Zone W", code="ZW", conference=conf)
        district = District.objects.create(name="District W", code="DW", zone=zone)
        self.church = Church.objects.create(name="Welfare Church", code="WCH", district=district)
        self.treasurer = User.objects.create_user(
            username="welfare_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="welfare_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        self.member = Member.objects.create(
            church=self.church,
            first_name="John",
            last_name="Welfare",
            gender=Gender.MALE,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_contribution_creates_ledger_entry(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            special_offerings={"WELFARE": Decimal("120.00")},
            member=self.member,
        )
        approve_transaction(txn, self.pastor)
        self.assertEqual(WelfareMemberLedger.objects.filter(member=self.member, entry_type="CONTRIBUTION").count(), 1)
        summary = member_welfare_summary(self.member)
        self.assertEqual(summary["contributed"], Decimal("120.00"))

    def test_case_workflow_with_case_number_and_ledger(self):
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
            amount_requested=Decimal("100.00"),
            reason="Medical",
            user=self.treasurer,
            assistance_type="MEDICAL",
        )
        self.assertTrue(case.case_number.startswith("WEL-"))
        self.assertEqual(WelfareMemberLedger.objects.filter(case=case, entry_type="REQUEST").count(), 1)

        send_welfare_case_to_review(case, self.treasurer, review_notes="Committee review")
        case.refresh_from_db()
        self.assertEqual(case.status, "UNDER_REVIEW")

        approve_welfare_case(case, self.pastor, amount_approved=Decimal("80.00"))
        case, trx = disburse_welfare_case(case, self.treasurer)
        self.assertEqual(case.status, "DISBURSED")
        self.assertIsNotNone(case.disbursement_transaction)
        self.assertEqual(case.disbursement_transaction, trx)
        self.assertEqual(WelfareMemberLedger.objects.filter(case=case, entry_type="DISBURSEMENT").count(), 1)

        summary = member_welfare_summary(self.member)
        self.assertEqual(summary["received"], Decimal("80.00"))

    def test_disbursement_blocked_when_insufficient_fund(self):
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("50.00"),
            reason="Need",
            user=self.treasurer,
        )
        approve_welfare_case(case, self.pastor)
        with self.assertRaises(RemittancePolicyError):
            disburse_welfare_case(case, self.treasurer)

    def test_manual_contribution_form_path(self):
        trx, contribution = record_manual_welfare_contribution(
            church=self.church,
            member=self.member,
            amount=Decimal("45.00"),
            user=self.treasurer,
        )
        self.assertIsNotNone(trx)
        self.assertIsNotNone(contribution)
        self.assertGreater(get_welfare_fund_balance(self.church), Decimal("0"))

    def test_fund_balance_guard(self):
        balance = get_welfare_fund_balance(self.church)
        with self.assertRaises(RemittancePolicyError):
            assert_welfare_fund_sufficient(self.church, balance + Decimal("1.00"))
