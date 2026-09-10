"""Phase 3 intelligence: tenancy, RBAC, deterministic rules, HIGH queue, auto-approve regression."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from approvals.models import ApprovalCase
from audit.models import AuditEvent
from intelligence.models import RiskAlert, RiskPolicy
from intelligence.rules import collect_findings, journal_amount
from intelligence.services import (
    confirm_alert,
    dismiss_alert,
    evaluate_transaction,
    get_or_create_policy,
    save_risk_policy,
)
from organization.models import Church, Conference, District, Zone
from permissions.checks import (
    can_approve_transactions,
    can_manage_receipts,
    can_manage_risk_policy,
    can_review_risk_alerts,
    can_view_risk_alerts,
)
from permissions.org_scope import apply_org_scope
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.services import (
    approve_transaction,
    get_or_create_treasury_approval_policy,
    open_working_day,
    record_expense,
    record_receipt,
    void_transaction,
)

User = get_user_model()


def _no_auto_approve(church):
    policy = get_or_create_treasury_approval_policy(church)
    policy.receipt_auto_approve_enabled = True
    policy.default_receipt_auto_approve_limit = Decimal("0.00")
    policy.save(update_fields=["receipt_auto_approve_enabled", "default_receipt_auto_approve_limit"])


class FinancialIntelligencePhase3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(code="in3", name="Intel Denom", is_active=True)
        cls.conference = Conference.objects.create(
            code="IN", name="Intel Conf", denomination=cls.denomination
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="IZ", name="Intel Zone")
        cls.district = District.objects.create(zone=cls.zone, code="ID", name="Intel District")
        cls.church = Church.objects.create(district=cls.district, code="IC", name="Intel Church")
        cls.other_district = District.objects.create(zone=cls.zone, code="ID2", name="Other Dist")
        cls.other_church = Church.objects.create(
            district=cls.other_district, code="OC", name="Other Church"
        )
        cls.treasury = User.objects.create_user(
            username="in_treas", password="pass12345", role=UserRole.TREASURY, church=cls.church
        )
        cls.pastor = User.objects.create_user(
            username="in_pastor", password="pass12345", role=UserRole.LOCAL_PASTOR, church=cls.church
        )
        cls.district_admin = User.objects.create_user(
            username="in_da", password="pass12345", role=UserRole.DISTRICT_PASTOR, church=cls.church
        )
        apply_org_scope(
            cls.district_admin,
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
            district=cls.district,
        )
        cls.district_admin.save()
        cls.district_treasurer = User.objects.create_user(
            username="in_dt", password="pass12345", role=UserRole.DISTRICT_TREASURY, church=cls.church
        )
        apply_org_scope(
            cls.district_treasurer,
            role=UserRole.DISTRICT_TREASURY,
            church=cls.church,
            district=cls.district,
        )
        cls.district_treasurer.save()
        cls.conf_admin = User.objects.create_user(
            username="in_ca", password="pass12345", role=UserRole.CONFERENCE_ADMIN, church=cls.church
        )
        apply_org_scope(
            cls.conf_admin,
            role=UserRole.CONFERENCE_ADMIN,
            church=cls.church,
            conference=cls.conference,
        )
        cls.conf_admin.save()
        open_working_day(cls.church, timezone.localdate(), cls.pastor)
        open_working_day(cls.other_church, timezone.localdate(), cls.pastor)
        _no_auto_approve(cls.church)
        _no_auto_approve(cls.other_church)

    def _login(self, username):
        from accounts.mfa import SESSION_MFA_VERIFIED

        client = Client()
        client.login(username=username, password="pass12345")
        session = client.session
        session[SESSION_MFA_VERIFIED] = True
        session["current_church_id"] = str(self.church.pk)
        session.save()
        return client

    def _receipt(self, amount="25.00", church=None, maker=None):
        return record_receipt(
            church=church or self.church,
            created_by=maker or self.treasury,
            tithe_amount=Decimal(amount),
        )

    def test_policy_defaults_do_not_block_auto_approve(self):
        policy = get_or_create_policy(self.church)
        self.assertFalse(policy.block_auto_approve_on_high)
        self.assertEqual(policy.large_absolute, Decimal("10000.00"))
        treasury_policy = get_or_create_treasury_approval_policy(self.church)
        treasury_policy.receipt_auto_approve_enabled = True
        treasury_policy.default_receipt_auto_approve_limit = Decimal("500.00")
        treasury_policy.save()
        self.church.refresh_from_db()
        save_risk_policy(self.church, self.conf_admin, block_auto_approve_on_high=True)
        txn = record_receipt(
            church=self.church, created_by=self.treasury, tithe_amount=Decimal("40.00")
        )
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)

    def test_unusually_large_is_explainable_and_idempotent(self):
        policy = get_or_create_policy(self.church)
        policy.large_absolute = Decimal("1000.00")
        policy.large_min_sample = 99
        policy.save()
        txn = self._receipt("2500.00")
        evaluate_transaction(txn)
        self.assertTrue(
            RiskAlert.objects.filter(transaction=txn, rule_code="unusually_large").exists()
        )
        alert = RiskAlert.objects.get(transaction=txn, rule_code="unusually_large")
        self.assertIn("amount", alert.observed)
        self.assertIn("limit", alert.threshold)
        self.assertTrue(alert.explanation)
        again = evaluate_transaction(txn)
        self.assertFalse(any(a.rule_code == "unusually_large" for a in again))
        self.assertEqual(
            RiskAlert.objects.filter(transaction=txn, rule_code="unusually_large").count(), 1
        )
        self.assertTrue(AuditEvent.objects.filter(action="risk.detect", object_id=str(alert.pk)).exists())

    def test_high_pending_queues_case_without_posting(self):
        txn = self._receipt("25000.00")
        self.assertEqual(txn.approval_status, "PENDING")
        evaluate_transaction(txn)
        high = RiskAlert.objects.filter(transaction=txn, severity=RiskAlert.SEVERITY_HIGH)
        self.assertTrue(high.exists())
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertFalse(txn.locked)
        case = ApprovalCase.objects.get(transaction=txn)
        self.assertEqual(case.status, ApprovalCase.STATUS_OPEN)
        self.assertTrue(AuditEvent.objects.filter(action="risk.queue").exists())

    def test_confirm_and_dismiss_do_not_change_journal(self):
        txn = self._receipt("25000.00")
        evaluate_transaction(txn)
        alert = RiskAlert.objects.filter(transaction=txn, severity=RiskAlert.SEVERITY_HIGH).first()
        confirm_alert(alert, self.pastor, note="reviewed")
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertTrue(AuditEvent.objects.filter(action="risk.confirm").exists())
        txn2 = self._receipt("26000.00")
        evaluate_transaction(txn2)
        alert2 = RiskAlert.objects.filter(transaction=txn2, severity=RiskAlert.SEVERITY_HIGH).first()
        dismiss_alert(alert2, self.pastor)
        txn2.refresh_from_db()
        self.assertEqual(txn2.approval_status, "PENDING")
        self.assertTrue(AuditEvent.objects.filter(action="risk.dismiss").exists())

    def test_near_duplicate_and_repeated_and_velocity(self):
        policy = get_or_create_policy(self.church)
        policy.near_duplicate_min_amount = Decimal("10.00")
        policy.repeat_count = 2
        policy.velocity_count = 3
        policy.save()
        first = self._receipt("40.00")
        second = self._receipt("40.00")
        third = self._receipt("40.00")
        evaluate_transaction(first)
        evaluate_transaction(second)
        evaluate_transaction(third)
        codes = set(RiskAlert.objects.filter(church=self.church).values_list("rule_code", flat=True))
        self.assertIn("near_duplicate", codes)
        self.assertIn("repeated", codes)
        self.assertIn("teller_velocity", codes)

    def test_unusual_expense_and_abnormal_reversal(self):
        policy = get_or_create_policy(self.church)
        policy.expense_absolute = Decimal("50.00")
        policy.reversal_count = 2
        policy.save()
        expense = record_expense(
            church=self.church, created_by=self.treasury, amount=Decimal("80.00")
        )
        evaluate_transaction(expense)
        self.assertTrue(
            RiskAlert.objects.filter(transaction=expense, rule_code="unusual_expense").exists()
        )
        a = self._receipt("12.00")
        b = self._receipt("13.00")
        approve_transaction(a, self.pastor)
        approve_transaction(b, self.pastor)
        void_transaction(a, self.pastor, reason="one")
        void_transaction(b, self.pastor, reason="two")
        evaluate_transaction(b)
        self.assertTrue(RiskAlert.objects.filter(church=self.church, rule_code="abnormal_reversal").exists())

    def test_step_change_bunching_baseline_rules(self):
        policy = get_or_create_policy(self.church)
        policy.step_change_ratio = Decimal("2.00")
        policy.bunching_min_count = 3
        policy.bunching_share = Decimal("0.50")
        policy.bunching_last_days = 31
        policy.baseline_min_sample = 3
        policy.baseline_z = Decimal("1.50")
        policy.large_min_sample = 99
        policy.large_absolute = Decimal("999999.00")
        policy.save()
        today = timezone.localdate()
        previous = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        from transactions.services import _get_account, _post_line
        from transactions import repositories as txn_repo

        def _seed(amount, date, ttype="RECEIPT"):
            trx = txn_repo.create_transaction(
                transaction_type=ttype,
                church=self.church,
                created_by=self.treasury,
                description="seed",
                date=date,
            )
            if ttype == "RECEIPT":
                _post_line(trx, _get_account(self.church, "CASH"), Decimal(amount))
                _post_line(trx, _get_account(self.church, "TITHE"), -Decimal(amount))
            else:
                _post_line(trx, _get_account(self.church, "CASH"), -Decimal(amount))
                _post_line(trx, _get_account(self.church, "EXPENSE"), Decimal(amount))
            return trx

        _seed("10.00", previous)
        current = self._receipt("40.00")
        evaluate_transaction(current)
        self.assertTrue(
            RiskAlert.objects.filter(church=self.church, rule_code="giving_step_change").exists()
        )
        expense_prev = _seed("10.00", previous, "EXPENSE")
        expense_now = record_expense(
            church=self.church, created_by=self.treasury, amount=Decimal("40.00")
        )
        evaluate_transaction(expense_prev)
        evaluate_transaction(expense_now)
        self.assertTrue(
            RiskAlert.objects.filter(church=self.church, rule_code="spend_step_change").exists()
        )
        extra = self._receipt("11.00")
        evaluate_transaction(extra)
        self.assertTrue(
            RiskAlert.objects.filter(church=self.church, rule_code="period_end_bunching").exists()
        )
        for value in ("10.00", "11.00", "12.00"):
            _seed(value, today - timedelta(days=5))
        spike = self._receipt("90.00")
        findings = collect_findings(spike, policy)
        self.assertTrue(any(item.rule_code == "baseline_deviation" for item in findings))
        evaluate_transaction(spike)
        self.assertTrue(
            RiskAlert.objects.filter(transaction=spike, rule_code="baseline_deviation").exists()
        )
        self.assertGreater(journal_amount(spike), Decimal("0"))

    def test_rbac_district_roles(self):
        txn = self._receipt("25000.00")
        evaluate_transaction(txn)
        alert = RiskAlert.objects.filter(transaction=txn).first()
        self.assertFalse(can_view_risk_alerts(self.district_admin))
        self.assertFalse(can_review_risk_alerts(self.district_admin))
        self.assertFalse(can_manage_risk_policy(self.district_admin))
        self.assertTrue(can_view_risk_alerts(self.district_treasurer))
        self.assertFalse(can_review_risk_alerts(self.district_treasurer))
        self.assertFalse(can_manage_risk_policy(self.district_treasurer))
        self.assertFalse(can_manage_receipts(self.district_treasurer))
        self.assertFalse(can_approve_transactions(self.district_treasurer))
        with self.assertRaises(PermissionDenied):
            dismiss_alert(alert, self.district_admin)
        with self.assertRaises(PermissionDenied):
            dismiss_alert(alert, self.district_treasurer)
        with self.assertRaises(PermissionDenied):
            save_risk_policy(self.church, self.district_admin, is_active=False)
        da = self._login("in_da")
        self.assertEqual(da.get(reverse("intelligence:alert_list")).status_code, 403)
        dt = self._login("in_dt")
        self.assertEqual(dt.get(reverse("intelligence:alert_list")).status_code, 200)
        self.assertEqual(dt.get(reverse("intelligence:alert_detail", args=[alert.pk])).status_code, 200)
        self.assertEqual(dt.post(reverse("intelligence:alert_dismiss", args=[alert.pk])).status_code, 403)
        self.assertEqual(dt.get(reverse("intelligence:policy")).status_code, 403)

    def test_tenancy_other_church_404(self):
        other = self._receipt("25000.00", church=self.other_church)
        evaluate_transaction(other)
        alert = RiskAlert.objects.get(transaction=other)
        client = self._login("in_pastor")
        self.assertEqual(client.get(reverse("intelligence:alert_detail", args=[alert.pk])).status_code, 404)

    def test_permissions_are_additive(self):
        from permissions.registry import PERMISSION_REGISTRY

        forbidden = {
            "approve_transactions",
            "void_transactions",
            "manage_receipts",
            "manage_expenses",
            "manage_finances",
        }
        for codename in ("view_risk_alerts", "review_risk_alerts", "manage_risk_policy"):
            implied = set(PERMISSION_REGISTRY[codename].get("implies", []))
            self.assertTrue(forbidden.isdisjoint(implied))
