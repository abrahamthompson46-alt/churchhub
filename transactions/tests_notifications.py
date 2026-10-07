"""Service-layer journal notification wiring."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from dashboard.models import Notification
from organization.models import Church, Conference, District, Zone
from transactions.services import (
    approve_transaction,
    open_working_day,
    record_expense,
    reject_transaction,
)

User = get_user_model()


class JournalNotificationTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Notify Conf", code="NC")
        zone = Zone.objects.create(name="Notify Zone", code="NZ", conference=conf)
        district = District.objects.create(name="Notify Dist", code="ND", zone=zone)
        self.church = Church.objects.create(name="Notify Church", code="NCH", district=district)
        self.treasurer = User.objects.create_user(
            username="n_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="n_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def test_pending_expense_notifies_checker(self):
        trx = record_expense(
            self.church,
            self.treasurer,
            Decimal("25.00"),
            description="Office supplies",
        )
        self.assertEqual(trx.approval_status, "PENDING")
        notes = Notification.objects.filter(event_key=f"txn.pending.{trx.pk}")
        self.assertTrue(notes.filter(user=self.pastor).exists())
        self.assertFalse(notes.filter(user=self.treasurer).exists())

    def test_approve_notifies_maker_once(self):
        trx = record_expense(
            self.church,
            self.treasurer,
            Decimal("12.00"),
            description="Travel",
        )
        approve_transaction(trx, self.pastor)
        approved = Notification.objects.filter(
            user=self.treasurer, event_key=f"txn.approved.{trx.pk}"
        )
        self.assertEqual(approved.count(), 1)

    def test_reject_notifies_maker(self):
        trx = record_expense(
            self.church,
            self.treasurer,
            Decimal("8.00"),
            description="Misc",
        )
        reject_transaction(trx, self.pastor, reason="Need receipt")
        self.assertTrue(
            Notification.objects.filter(
                user=self.treasurer, event_key=f"txn.rejected.{trx.pk}"
            ).exists()
        )
