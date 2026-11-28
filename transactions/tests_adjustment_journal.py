"""Tests for church-scoped adjustment journals."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from approvals.services import actor_may_decide
from ledger.services import seed_ledger
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from transactions.adjustment_services import (
    build_adjustment_draft,
    is_account_allowed_for_adjustment,
    post_adjustment_journal,
)
from transactions.models import Account, Transaction
from transactions.services import open_working_day

User = get_user_model()


class AdjustmentJournalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.conference = Conference.objects.create(code="AJ", name="Adj Conf")
        cls.zone = Zone.objects.create(conference=cls.conference, code="AZ", name="Adj Zone")
        cls.district = District.objects.create(zone=cls.zone, code="AD", name="Adj District")
        cls.church = Church.objects.create(district=cls.district, code="ACH", name="Adj Church")
        seed_ledger(cls.church)
        cls.maker = User.objects.create_user(
            username="adj_maker",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.checker = User.objects.create_user(
            username="adj_checker",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )

    def setUp(self):
        open_working_day(self.church, timezone.localdate(), self.checker)
        self.cash = Account.objects.get(church=self.church, name="Cash")
        self.welfare = Account.objects.get(church=self.church, name="Welfare Fund")
        self.payable = Account.objects.get(
            church=self.church, account_type="TITHE_REMIT_PAYABLE"
        )

    def test_blocked_remittance_payable(self):
        self.assertFalse(is_account_allowed_for_adjustment(self.payable))

    def test_balanced_draft_and_post(self):
        lines = [
            {
                "account_id": str(self.welfare.pk),
                "account_name": self.welfare.name,
                "side": "DEBIT",
                "amount": Decimal("25.00"),
            },
            {
                "account_id": str(self.cash.pk),
                "account_name": self.cash.name,
                "side": "CREDIT",
                "amount": Decimal("25.00"),
            },
        ]
        draft = build_adjustment_draft(
            self.church,
            narration="Reclass welfare payout correction test",
            entry_date=timezone.localdate(),
            lines=lines,
        )
        trx = post_adjustment_journal(
            self.church, self.maker, draft, idempotency_key="adj-test-1"
        )
        self.assertEqual(trx.transaction_type, "ADJUSTMENT")
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertTrue(trx.reference.startswith("ADJ-"))

    def test_unbalanced_raises(self):
        lines = [
            {
                "account_id": str(self.cash.pk),
                "account_name": self.cash.name,
                "side": "DEBIT",
                "amount": Decimal("10.00"),
            },
            {
                "account_id": str(self.welfare.pk),
                "account_name": self.welfare.name,
                "side": "CREDIT",
                "amount": Decimal("5.00"),
            },
        ]
        with self.assertRaises(ValueError):
            build_adjustment_draft(
                self.church,
                narration="Unbalanced test entry",
                entry_date=timezone.localdate(),
                lines=lines,
            )

    def test_checker_may_decide_adjustment(self):
        lines = [
            {
                "account_id": str(self.cash.pk),
                "account_name": self.cash.name,
                "side": "DEBIT",
                "amount": Decimal("15.00"),
            },
            {
                "account_id": str(self.welfare.pk),
                "account_name": self.welfare.name,
                "side": "CREDIT",
                "amount": Decimal("15.00"),
            },
        ]
        draft = build_adjustment_draft(
            self.church,
            narration="Approve path test journal",
            entry_date=timezone.localdate(),
            lines=lines,
        )
        trx = post_adjustment_journal(self.church, self.maker, draft)
        self.assertTrue(actor_may_decide(self.checker, trx))
        self.assertFalse(actor_may_decide(self.maker, trx))

    def test_create_view_requires_permission(self):
        client = Client()
        client.login(username="adj_maker", password="pass12345")
        response = client.get(reverse("transactions:adjustment_create"))
        self.assertEqual(response.status_code, 200)
        client.logout()
        outsider = User.objects.create_user(
            username="adj_clerk",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        client.login(username="adj_clerk", password="pass12345")
        response = client.get(reverse("transactions:adjustment_create"))
        self.assertEqual(response.status_code, 403)