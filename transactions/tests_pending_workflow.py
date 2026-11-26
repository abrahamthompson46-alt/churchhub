"""Pending approval queue UX: reject reasons and CSRF on finance actions."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from permissions.org_scope import apply_org_scope
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.models import FinancialAuditLog, Transaction
from transactions.services import (
    get_or_create_treasury_approval_policy,
    open_working_day,
    record_receipt,
)

User = get_user_model()


class PendingWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom = Denomination.objects.create(code="pw", name="Pending WF", is_active=True)
        cls.conf = Conference.objects.create(code="PWC", name="Pending Conf", denomination=cls.denom)
        cls.zone = Zone.objects.create(conference=cls.conf, code="PWZ", name="Pending Zone")
        cls.dist = District.objects.create(zone=cls.zone, code="PWD", name="Pending Dist")
        cls.church = Church.objects.create(district=cls.dist, code="PCH", name="Pending Church")
        cls.treasury = User.objects.create_user(
            username="pw_treas",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="pw_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        apply_org_scope(cls.pastor, role=UserRole.LOCAL_PASTOR, church=cls.church, district=cls.dist)
        cls.pastor.save()
        open_working_day(cls.church, timezone.localdate(), cls.treasury)
        policy = get_or_create_treasury_approval_policy(cls.church)
        policy.receipt_auto_approve_enabled = True
        policy.default_receipt_auto_approve_limit = Decimal("0.00")
        policy.save(
            update_fields=["receipt_auto_approve_enabled", "default_receipt_auto_approve_limit"]
        )

    def _pending_txn(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasury,
            tithe_amount=Decimal("25.00"),
        )
        self.assertEqual(txn.approval_status, "PENDING")
        return txn

    def test_reject_without_reason_blocked(self):
        txn = self._pending_txn()
        self.client.force_login(self.pastor)
        url = reverse("transactions:reject_transaction", kwargs={"pk": txn.pk})
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 302)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertFalse(
            FinancialAuditLog.objects.filter(transaction=txn, action="REJECT").exists()
        )

    def test_reject_with_reason_persists(self):
        txn = self._pending_txn()
        self.client.force_login(self.pastor)
        url = reverse("transactions:reject_transaction", kwargs={"pk": txn.pk})
        self.client.post(url, {"reason": "Missing supporting receipt"})
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "REJECTED")
        log = FinancialAuditLog.objects.get(transaction=txn, action="REJECT")
        self.assertEqual(log.details.get("reason"), "Missing supporting receipt")

    def test_approve_requires_csrf_token(self):
        txn = self._pending_txn()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.pastor)
        url = reverse("transactions:approve_transaction", kwargs={"pk": txn.pk})
        response = csrf_client.post(url, {})
        self.assertEqual(response.status_code, 403)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")

    def test_reject_requires_csrf_token(self):
        txn = self._pending_txn()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.pastor)
        url = reverse("transactions:reject_transaction", kwargs={"pk": txn.pk})
        response = csrf_client.post(url, {"reason": "Test"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Transaction.objects.filter(pk=txn.pk, approval_status="PENDING").count(),
            1,
        )