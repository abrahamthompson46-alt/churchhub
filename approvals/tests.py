"""Phase 2 maker-checker: SoD, tenancy, RBAC, delegation, multi-step, escalation, audit."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from approvals.models import ApprovalCase, ApprovalDelegation
from approvals.services import (
    actor_may_decide,
    create_delegation,
    ensure_case,
    escalate_case,
    get_or_create_policy,
    record_approval,
    record_rejection,
    record_void,
    request_correction,
    save_required_steps,
)
from audit.models import AuditEvent
from organization.models import Church, Conference, District, Zone
from permissions.checks import (
    can_approve_transactions,
    can_manage_approval_policy,
    can_manage_receipts,
    can_view_approval_cases,
)
from permissions.org_scope import apply_org_scope
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.models import FinancialAuditLog, Transaction
from transactions.services import (
    approve_transaction,
    get_or_create_treasury_approval_policy,
    open_working_day,
    record_receipt,
    reject_transaction,
    void_transaction,
)

User = get_user_model()


def _no_auto_approve(church):
    policy = get_or_create_treasury_approval_policy(church)
    policy.receipt_auto_approve_enabled = True
    policy.default_receipt_auto_approve_limit = Decimal("0.00")
    policy.save(update_fields=["receipt_auto_approve_enabled", "default_receipt_auto_approve_limit"])


class MakerCheckerPhase2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="ap2", name="Approvals Denom", is_active=True
        )
        cls.conference = Conference.objects.create(
            code="AP", name="Approvals Conf", denomination=cls.denomination
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="AZ", name="Approvals Zone")
        cls.district = District.objects.create(zone=cls.zone, code="AD", name="Approvals District")
        cls.church = Church.objects.create(district=cls.district, code="AC", name="Approvals Church")
        cls.other_district = District.objects.create(zone=cls.zone, code="AD2", name="Other Dist")
        cls.other_church = Church.objects.create(
            district=cls.other_district, code="OC", name="Other Church"
        )
        cls.treasury = User.objects.create_user(
            username="ap_treas", password="pass12345", role=UserRole.TREASURY, church=cls.church
        )
        cls.pastor = User.objects.create_user(
            username="ap_pastor", password="pass12345", role=UserRole.LOCAL_PASTOR, church=cls.church
        )
        cls.member = User.objects.create_user(
            username="ap_mem", password="pass12345", role=UserRole.MEMBER, church=cls.church
        )
        cls.district_admin = User.objects.create_user(
            username="ap_da", password="pass12345", role=UserRole.DISTRICT_PASTOR, church=cls.church
        )
        apply_org_scope(
            cls.district_admin,
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
            district=cls.district,
        )
        cls.district_admin.save()
        cls.district_treasurer = User.objects.create_user(
            username="ap_dt", password="pass12345", role=UserRole.DISTRICT_TREASURY, church=cls.church
        )
        apply_org_scope(
            cls.district_treasurer,
            role=UserRole.DISTRICT_TREASURY,
            church=cls.church,
            district=cls.district,
        )
        cls.district_treasurer.save()
        cls.conf_admin = User.objects.create_user(
            username="ap_ca", password="pass12345", role=UserRole.CONFERENCE_ADMIN, church=cls.church
        )
        apply_org_scope(
            cls.conf_admin,
            role=UserRole.CONFERENCE_ADMIN,
            church=cls.church,
            conference=cls.conference,
        )
        cls.conf_admin.save()
        cls.superadmin = User.objects.create_user(
            username="ap_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=cls.church,
            denomination=cls.denomination,
        )
        open_working_day(cls.church, timezone.localdate(), cls.pastor)
        open_working_day(cls.other_church, timezone.localdate(), cls.pastor)
        _no_auto_approve(cls.church)
        _no_auto_approve(cls.other_church)

    def _pending(self, amount="25.00", church=None, maker=None):
        return record_receipt(
            church=church or self.church,
            created_by=maker or self.treasury,
            tithe_amount=Decimal(amount),
        )

    def _login(self, username):
        from accounts.mfa import SESSION_MFA_VERIFIED

        client = Client()
        client.login(username=username, password="pass12345")
        session = client.session
        session[SESSION_MFA_VERIFIED] = True
        session["current_church_id"] = str(self.church.pk)
        session.save()
        return client

    def test_default_one_step_posts_via_existing_approve(self):
        txn = self._pending()
        self.assertEqual(txn.approval_status, "PENDING")
        outcome = record_approval(txn, self.pastor)
        self.assertTrue(outcome.posted)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)
        self.assertEqual(txn.approved_by_id, self.pastor.id)
        self.assertTrue(
            FinancialAuditLog.objects.filter(transaction=txn, action="APPROVE").exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="approval.decide", object_id=str(outcome.case.pk)).exists()
        )

    def test_maker_cannot_approve_reject_or_void_own(self):
        txn = self._pending()
        with self.assertRaises(PermissionDenied):
            record_approval(txn, self.treasury)
        with self.assertRaises(ValueError):
            approve_transaction(txn, self.treasury)
        with self.assertRaises(ValueError):
            reject_transaction(txn, self.treasury)
        approved = approve_transaction(txn, self.pastor)
        with self.assertRaises(ValueError):
            void_transaction(approved, self.treasury)

    def test_superadmin_can_void_own_journal(self):
        txn = self._pending(maker=self.superadmin)
        approved = approve_transaction(txn, self.pastor)
        voided = void_transaction(approved, self.superadmin, reason="break-glass")
        self.assertEqual(voided.approval_status, "REVERSED")

    def test_receipt_auto_approve_unchanged(self):
        policy = get_or_create_treasury_approval_policy(self.church)
        policy.receipt_auto_approve_enabled = True
        policy.default_receipt_auto_approve_limit = Decimal("500.00")
        policy.save(update_fields=["receipt_auto_approve_enabled", "default_receipt_auto_approve_limit"])
        self.church.refresh_from_db()
        txn = record_receipt(
            church=self.church, created_by=self.treasury, tithe_amount=Decimal("10.00")
        )
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(
            (FinancialAuditLog.objects.filter(transaction=txn, action="APPROVE").first().details or {}).get(
                "auto_approved"
            )
        )
        _no_auto_approve(self.church)
        self.church.refresh_from_db()

    def test_multi_step_does_not_post_until_final(self):
        policy = get_or_create_policy(self.church)
        policy.required_steps = 2
        policy.save(update_fields=["required_steps"])
        txn = self._pending()
        first = record_approval(txn, self.pastor)
        self.assertFalse(first.posted)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertFalse(txn.locked)
        second = record_approval(txn, self.conf_admin)
        self.assertTrue(second.posted)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")
        policy.required_steps = 1
        policy.save(update_fields=["required_steps"])

    def test_correction_keeps_transaction_pending(self):
        txn = self._pending()
        case = request_correction(txn, self.pastor, note="Fix the memo")
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertEqual(case.status, ApprovalCase.STATUS_CORRECTION)
        self.assertTrue(AuditEvent.objects.filter(action="approval.correct").exists())

    def test_escalation_never_auto_approves(self):
        txn = self._pending()
        case = escalate_case(txn, self.pastor, reason="Need conference review")
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertEqual(case.status, ApprovalCase.STATUS_ESCALATED)
        self.assertTrue(case.escalations.exists())
        self.assertTrue(AuditEvent.objects.filter(action="approval.escalate").exists())

    def test_delegation_authorizes_treasury_within_cap_and_dates(self):
        txn = self._pending("40.00", maker=self.pastor)
        self.assertFalse(can_approve_transactions(self.treasury))
        self.assertFalse(actor_may_decide(self.treasury, txn))
        today = timezone.localdate()
        create_delegation(
            grantor=self.pastor,
            grantee=self.treasury,
            church=self.church,
            valid_from=today,
            valid_until=today,
            max_amount=Decimal("50.00"),
        )
        self.assertTrue(actor_may_decide(self.treasury, txn))
        outcome = record_approval(txn, self.treasury)
        self.assertTrue(outcome.posted)

    def test_expired_or_over_cap_or_other_church_delegation_is_denied(self):
        today = timezone.localdate()
        create_delegation(
            grantor=self.pastor,
            grantee=self.treasury,
            church=self.church,
            valid_from=today - timedelta(days=10),
            valid_until=today - timedelta(days=1),
            max_amount=Decimal("500.00"),
        )
        txn = self._pending("10.00")
        self.assertFalse(actor_may_decide(self.treasury, txn))
        ApprovalDelegation.objects.all().update(is_revoked=True)
        create_delegation(
            grantor=self.pastor,
            grantee=self.treasury,
            church=self.church,
            valid_from=today,
            valid_until=today,
            max_amount=Decimal("5.00"),
        )
        txn2 = self._pending("40.00")
        self.assertFalse(actor_may_decide(self.treasury, txn2))
        other_txn = self._pending("10.00", church=self.other_church)
        self.assertFalse(actor_may_decide(self.treasury, other_txn))

    def test_cannot_delegate_to_district_admin(self):
        today = timezone.localdate()
        with self.assertRaises(ValueError):
            create_delegation(
                grantor=self.pastor,
                grantee=self.district_admin,
                church=self.church,
                valid_from=today,
                valid_until=today,
            )

    def test_district_roles_rbac(self):
        txn = self._pending()
        self.assertTrue(can_view_approval_cases(self.district_admin))
        self.assertFalse(can_approve_transactions(self.district_admin))
        self.assertFalse(can_manage_approval_policy(self.district_admin))
        self.assertFalse(actor_may_decide(self.district_admin, txn))
        self.assertFalse(can_manage_receipts(self.district_treasurer))
        self.assertFalse(can_approve_transactions(self.district_treasurer))
        self.assertFalse(actor_may_decide(self.district_treasurer, txn))
        with self.assertRaises(PermissionDenied):
            save_required_steps(self.church, self.district_admin, 2)
        with self.assertRaises(PermissionDenied):
            save_required_steps(self.church, self.district_treasurer, 2)

    def test_tenancy_case_detail_404(self):
        txn = self._pending(church=self.other_church)
        case = ensure_case(txn)
        client = self._login("ap_treas")
        denied = client.get(reverse("approvals:case_detail", args=[case.pk]))
        self.assertEqual(denied.status_code, 404)
        client_p = self._login("ap_pastor")
        home = client_p.get(reverse("approvals:case_list"))
        self.assertEqual(home.status_code, 200)

    def test_member_cannot_open_approvals(self):
        client = self._login("ap_mem")
        self.assertEqual(client.get(reverse("approvals:case_list")).status_code, 403)

    def test_http_approve_wraps_service(self):
        txn = self._pending()
        client = self._login("ap_pastor")
        response = client.post(reverse("transactions:approve_transaction", args=[txn.pk]))
        self.assertEqual(response.status_code, 302)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")

    def test_policy_permission_http(self):
        client = self._login("ap_da")
        self.assertEqual(client.get(reverse("approvals:policy")).status_code, 403)
        client_ca = self._login("ap_ca")
        self.assertEqual(client_ca.get(reverse("approvals:policy")).status_code, 200)

    def test_dual_write_failure_does_not_block_journal_approve(self):
        txn = self._pending()
        with patch("approvals.services.emit_event", side_effect=RuntimeError("audit down")):
            outcome = record_approval(txn, self.pastor)
        self.assertTrue(outcome.posted)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")
