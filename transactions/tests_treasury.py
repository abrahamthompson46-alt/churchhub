"""Tests for cash position and teller console helpers."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserRole
from organization.models import Church, Conference, District, Zone
from transactions.models import Account, Transaction, TransactionLine
from transactions.services import create_default_accounts, open_working_day
from transactions.treasury import get_cash_position, get_teller_daily_summary

User = get_user_model()


class TreasuryHelpersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="TC", name="T Conf")
        zone = Zone.objects.create(conference=conf, code="TZ", name="T Zone")
        dist = District.objects.create(zone=zone, code="TD", name="T Dist")
        cls.church = Church.objects.create(district=dist, code="TCH", name="T Church")
        create_default_accounts(cls.church)
        cls.teller = User.objects.create_user(
            username="teller1",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        open_working_day(cls.church, timezone.localdate(), cls.teller)

    def test_cash_position_after_receipt(self):
        cash = Account.objects.get(church=self.church, name="Cash")
        tithe = Account.objects.get(church=self.church, name="Tithe")
        trx = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=self.church,
            created_by=self.teller,
            description="Cash tithe",
            date=timezone.localdate(),
            approval_status="APPROVED",
            approved_by=self.teller,
            approved_at=timezone.now(),
        )
        TransactionLine.objects.create(transaction=trx, account=cash, amount=Decimal("50.00"))
        TransactionLine.objects.create(transaction=trx, account=tithe, amount=Decimal("-50.00"))
        pos = get_cash_position(self.church)
        self.assertEqual(pos["cash"], Decimal("50.00"))

    def test_teller_daily_summary(self):
        cash = Account.objects.get(church=self.church, name="Cash")
        income = Account.objects.get(church=self.church, name="General Income")
        trx = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=self.church,
            created_by=self.teller,
            description="Income",
            date=timezone.localdate(),
            approval_status="PENDING",
        )
        TransactionLine.objects.create(transaction=trx, account=cash, amount=Decimal("25.00"))
        TransactionLine.objects.create(transaction=trx, account=income, amount=Decimal("-25.00"))
        summary = get_teller_daily_summary(self.church)
        self.assertEqual(summary["totals"]["entries"], 1)
        self.assertEqual(len(summary["tellers"]), 1)
        self.assertEqual(summary["tellers"][0]["pending"], 1)
