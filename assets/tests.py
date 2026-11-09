"""Tests for fixed asset register — services, RBAC, and views."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Count
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import (
    AssetCategoryTemplate,
    AssetDepreciationEntry,
    AssetPolicyAuditLog,
    FixedAsset,
)
from assets import selectors
from assets.depreciation_classification import classify_historical_depreciation_entries
from assets.rbac import churches_in_asset_scope
from assets.services import (
    AssetError,
    REGISTER_RECONCILE_REQUIRED,
    _finalize_depreciation_register,
    approve_asset,
    assert_segregation_of_duties,
    calculate_monthly_depreciation,
    dispose_asset,
    ensure_asset_defaults_for_church,
    ensure_depreciation_policy,
    format_depreciation_run_summary,
    generate_asset_code,
    post_depreciation_entry,
    preview_monthly_depreciation,
    reject_asset,
    run_monthly_depreciation,
    seed_platform_category_templates,
    submit_asset_for_approval,
    validate_depreciation_period,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from transactions.models import FinancialAuditLog, Transaction
from transactions.services import (
    DEPRECIATION_GENERIC_APPROVAL_REFUSED,
    UNLINKED_CAPITAL_GENERIC_APPROVAL_REFUSED,
    UNLINKED_CAPITAL_MODULE_APPROVAL_REFUSED,
    _commit_journal_approval,
    approve_module_journal,
    approve_transaction,
    close_working_day,
    create_default_accounts,
    get_active_working_day,
    open_working_day,
    record_expense,
)


def _complete_depreciation(asset, year, month, maker, checker):
    post_depreciation_entry(asset, year, month, maker, allow_approval=False)
    return post_depreciation_entry(
        asset, year, month, checker, allow_approval=True
    )

User = get_user_model()


class AssetServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_platform_category_templates()
        conference = Conference.objects.create(name="Test Conf", code="TC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="Z1")
        district = District.objects.create(zone=zone, name="District", code="D1")
        cls.church = Church.objects.create(district=district, name="Test Church", code="TC01")
        ensure_asset_defaults_for_church(cls.church)
        create_default_accounts(cls.church)
        cls.user = User.objects.create_user(
            username="assetuser",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.approver = User.objects.create_user(
            username="assetapprover",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )

    def test_platform_templates_seeded(self):
        self.assertGreaterEqual(AssetCategoryTemplate.objects.count(), 8)

    def test_church_categories_created(self):
        self.assertTrue(self.church.asset_categories.exists())

    def test_generate_asset_code(self):
        code = generate_asset_code(self.church)
        self.assertTrue(code.startswith("TC01-FA-"))

    def test_generate_asset_code_sequential(self):
        category = self.church.asset_categories.first()
        FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code=generate_asset_code(self.church),
            name="A",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("100.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
        )
        code2 = generate_asset_code(self.church)
        self.assertTrue(code2.endswith("0002"))

    def test_straight_line_depreciation(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0001",
            name="Office Desk",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        amount = calculate_monthly_depreciation(asset, 2024, 1)
        self.assertEqual(amount, Decimal("100.00"))

    def test_submit_for_approval(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0002",
            name="Projector",
            purchase_date=date(2024, 6, 1),
            acquisition_cost=Decimal("5000.00"),
            useful_life_months=48,
            depreciation_method="STRAIGHT_LINE",
            status="DRAFT",
        )
        submit_asset_for_approval(asset, self.user)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "PENDING_APPROVAL")

    def test_segregation_blocks_self_approval(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0003",
            name="Chair",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("200.00"),
            useful_life_months=24,
            depreciation_method="STRAIGHT_LINE",
            status="PENDING_APPROVAL",
            created_by=self.user,
            submitted_by=self.user,
        )
        with self.assertRaises(AssetError):
            approve_asset(asset, self.user)

    def test_assert_segregation_of_duties(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0004",
            name="Table",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("300.00"),
            useful_life_months=24,
            depreciation_method="STRAIGHT_LINE",
            created_by=self.user,
            submitted_by=self.user,
        )
        with self.assertRaises(AssetError):
            assert_segregation_of_duties(asset, self.user)

    def test_approve_posts_acquisition(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0005",
            name="Van",
            purchase_date=date(2024, 3, 1),
            acquisition_cost=Decimal("10000.00"),
            useful_life_months=60,
            depreciation_method="STRAIGHT_LINE",
            status="PENDING_APPROVAL",
            created_by=self.user,
            submitted_by=self.user,
        )
        open_working_day(self.church, date(2024, 3, 1), self.approver)
        approve_asset(asset, self.approver)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "ACTIVE")
        self.assertIsNotNone(asset.acquisition_transaction_id)
        trx = asset.acquisition_transaction
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertTrue(trx.locked)
        self.assertEqual(trx.approved_by_id, self.approver.id)
        self.assertNotEqual(trx.created_by_id, trx.approved_by_id)

    def test_future_depreciation_period_rejected(self):
        future = timezone.now().date()
        future_year = future.year + 1
        with self.assertRaises(AssetError):
            validate_depreciation_period(future_year, 1)

    def test_depreciation_idempotent(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0006",
            name="Laptop",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("2400.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=24,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        open_working_day(self.church, date(2024, 1, 28), self.approver)
        _complete_depreciation(asset, 2024, 1, self.user, self.approver)
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                asset, 2024, 1, self.approver, allow_approval=True
            )

    def test_preview_monthly_depreciation(self):
        category = self.church.asset_categories.first()
        FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0007",
            name="Printer",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        preview = preview_monthly_depreciation(self.church, 2024, 1)
        self.assertEqual(preview["asset_count"], 1)
        self.assertEqual(preview["total"], Decimal("100.00"))

    def test_dispose_posts_ledger(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0008",
            name="Old Desk",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1000.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("250.00"),
        )
        open_working_day(self.church, timezone.localdate(), self.approver)
        dispose_asset(asset, self.user, notes="Scrapped", checker=self.approver)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "DISPOSED")
        self.assertIsNotNone(asset.disposal_transaction_id)
        trx = asset.disposal_transaction
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertTrue(trx.locked)
        self.assertEqual(trx.approved_by_id, self.approver.id)
        self.assertNotEqual(trx.created_by_id, trx.approved_by_id)

    def test_dispose_maker_leaves_pending_then_checker_posts(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0018",
            name="Old Pew",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("800.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("100.00"),
        )
        open_working_day(self.church, timezone.localdate(), self.approver)
        prepared = dispose_asset(asset, self.user, notes="Worn out")
        prepared.refresh_from_db()
        self.assertEqual(prepared.status, "ACTIVE")
        self.assertIsNotNone(prepared.disposal_transaction_id)
        trx = prepared.disposal_transaction
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertEqual(trx.created_by_id, self.user.id)
        completed = dispose_asset(prepared, self.approver, notes="Worn out")
        completed.refresh_from_db()
        self.assertEqual(completed.status, "DISPOSED")
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertEqual(trx.approved_by_id, self.approver.id)

    def test_http_dispose_uses_authenticated_actor_not_generic_queue(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0019",
            name="Old Amp",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("400.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("50.00"),
        )
        open_working_day(self.church, timezone.localdate(), self.approver)
        for actor in (self.user, self.approver):
            if not getattr(actor, "mfa_enabled", False):
                enable_mfa_for_user(actor, generate_totp_secret(), [])
                actor.refresh_from_db()

        def _client(actor):
            client = Client()
            client.login(username=actor.username, password="test12345")
            session = client.session
            session["current_church_id"] = str(self.church.pk)
            session[SESSION_MFA_VERIFIED] = True
            session.save()
            return client

        url = reverse("assets:asset_dispose", kwargs={"pk": asset.pk})
        first = _client(self.user).post(url, {"notes": "Broken"})
        self.assertEqual(first.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "ACTIVE")
        self.assertEqual(asset.disposal_transaction.approval_status, "PENDING")
        second = _client(self.approver).post(url, {"notes": "Broken"})
        self.assertEqual(second.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "DISPOSED")
        asset.disposal_transaction.refresh_from_db()
        self.assertEqual(asset.disposal_transaction.approval_status, "APPROVED")
        self.assertEqual(asset.disposal_transaction.approved_by_id, self.approver.id)

    def test_reject_pending_asset(self):
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="TC01-FA-0009",
            name="Rejected Item",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("500.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="PENDING_APPROVAL",
        )
        reject_asset(asset, self.approver, reason="Incomplete documentation")
        asset.refresh_from_db()
        self.assertEqual(asset.status, "REJECTED")
        self.assertEqual(asset.rejection_reason, "Incomplete documentation")


class AssetRbacTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        conf = Conference.objects.create(name="Conf", code="CF")
        zone = Zone.objects.create(conference=conf, name="Zone", code="Z1")
        d1 = District.objects.create(zone=zone, name="D1", code="D1")
        d2 = District.objects.create(zone=zone, name="D2", code="D2")
        cls.church1 = Church.objects.create(district=d1, name="Church 1", code="CH1")
        cls.church2 = Church.objects.create(district=d2, name="Church 2", code="CH2")
        cls.overseer = User.objects.create_user(
            username="overseer",
            password="test12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church1,
        )
        cls.board = User.objects.create_user(
            username="board_viewer",
            password="test12345",
            role=UserRole.BOARD_MEMBER,
            church=cls.church1,
        )
        cls.member = User.objects.create_user(
            username="member_no_assets",
            password="test12345",
            role=UserRole.MEMBER,
            church=cls.church1,
        )

    def test_churches_in_scope_district_pastor(self):
        scoped = churches_in_asset_scope(self.overseer)
        self.assertEqual(scoped.count(), 1)
        self.assertEqual(scoped.first().pk, self.church1.pk)

    def test_view_assets_grants_read_access(self):
        from assets.rbac import user_may_view_assets
        from permissions.checks import can_manage_assets, can_view_assets

        self.assertTrue(can_view_assets(self.board))
        self.assertFalse(can_manage_assets(self.board))
        self.assertTrue(user_may_view_assets(self.board))
        self.assertFalse(user_may_view_assets(self.member))


class AssetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conf = Conference.objects.create(name="Conf", code="CF")
        zone = Zone.objects.create(conference=conf, name="Zone", code="Z1")
        district = District.objects.create(zone=zone, name="D1", code="D1")
        cls.church = Church.objects.create(district=district, name="Church", code="CH1")
        ensure_asset_defaults_for_church(cls.church)
        cls.treasury = User.objects.create_user(
            username="treasury",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="pastor",
            password="test12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
        )
        cls.board = User.objects.create_user(
            username="board_assets",
            password="test12345",
            role=UserRole.BOARD_MEMBER,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="CH1-FA-0001",
            name="Sound System",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("3000.00"),
            useful_life_months=36,
            depreciation_method="STRAIGHT_LINE",
            status="DRAFT",
            created_by=cls.treasury,
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Python 3.14 + Django test client: Context.__copy__ crashes in
        # store_rendered_templates. Skip the copy; status/content asserts still work.
        from django.test.client import ContextList
        from unittest.mock import patch

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    def _login(self, user):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret

        # Privileged roles require MFA; satisfy middleware so view tests stay focused.
        if not getattr(user, "mfa_enabled", False):
            enable_mfa_for_user(user, generate_totp_secret(), [])
            user.refresh_from_db()
        client = Client()
        client.login(username=user.username, password="test12345")
        session = client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        return client

    def test_asset_list_requires_view_permission(self):
        member = User.objects.create_user(
            username="memberuser",
            password="test12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        client = self._login(member)
        response = client.get(reverse("assets:asset_list"))
        self.assertEqual(response.status_code, 403)

    def test_view_only_board_member_can_read_register(self):
        client = self._login(self.board)
        index_response = client.get(reverse("assets:index"))
        self.assertEqual(index_response.status_code, 200)
        list_response = client.get(reverse("assets:asset_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertFalse(list_response.context["can_manage"])
        detail_response = client.get(
            reverse("assets:asset_detail", kwargs={"pk": self.asset.pk})
        )
        self.assertEqual(detail_response.status_code, 200)

    def test_view_only_board_member_cannot_create_or_export(self):
        client = self._login(self.board)
        create_response = client.get(reverse("assets:asset_create"))
        self.assertEqual(create_response.status_code, 403)
        export_response = client.get(reverse("assets:asset_export_csv"))
        self.assertEqual(export_response.status_code, 403)

    def test_asset_csv_exports_are_audited(self):
        from reports.models import ReportAccessAuditLog

        client = self._login(self.treasury)
        register = client.get(reverse("assets:asset_export_csv"))
        self.assertEqual(register.status_code, 200)
        self.assertEqual(
            ReportAccessAuditLog.objects.filter(report_key="asset_register").count(),
            1,
        )
        activity = client.get(reverse("assets:activity_log_export"))
        self.assertEqual(activity.status_code, 200)
        self.assertEqual(
            ReportAccessAuditLog.objects.filter(report_key="asset_activity").count(),
            1,
        )

    def test_board_cannot_export_activity_log(self):
        client = self._login(self.board)
        response = client.get(reverse("assets:activity_log_export"))
        self.assertEqual(response.status_code, 403)

    def test_index_accessible_to_treasury(self):
        client = self._login(self.treasury)
        response = client.get(reverse("assets:index"))
        self.assertEqual(response.status_code, 200)

    def test_submit_requires_post(self):
        client = self._login(self.treasury)
        response = client.get(reverse("assets:asset_submit", kwargs={"pk": self.asset.pk}))
        self.assertEqual(response.status_code, 405)

    def test_submit_via_post(self):
        client = self._login(self.treasury)
        response = client.post(reverse("assets:asset_submit", kwargs={"pk": self.asset.pk}))
        self.assertEqual(response.status_code, 302)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "PENDING_APPROVAL")

    def test_approve_blocked_for_submitter(self):
        self.asset.status = "PENDING_APPROVAL"
        self.asset.submitted_by = self.treasury
        self.asset.save()
        client = self._login(self.treasury)
        response = client.post(reverse("assets:asset_approve", kwargs={"pk": self.asset.pk}))
        self.assertEqual(response.status_code, 302)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "PENDING_APPROVAL")

    def test_policy_update_creates_audit_log(self):
        client = self._login(self.treasury)
        response = client.post(
            reverse("assets:policy_edit"),
            {
                "allow_straight_line": "on",
                "allow_declining_balance": "on",
                "default_method": "STRAIGHT_LINE",
                "auto_run_monthly": "",
                "run_day_of_month": 28,
                "post_depreciation_to_ledger": "on",
                "post_disposal_to_ledger": "on",
                "capitalize_on_approval": "on",
                "default_payment_account_type": "BANK",
                "fiscal_year_start_month": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AssetPolicyAuditLog.objects.filter(church=self.church, action="POLICY_UPDATE").exists()
        )

    def test_activity_log_page(self):
        client = self._login(self.treasury)
        response = client.get(reverse("assets:activity_log"))
        self.assertEqual(response.status_code, 200)

    def test_asset_list_search(self):
        client = self._login(self.treasury)
        response = client.get(reverse("assets:asset_list"), {"q": "Sound"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sound System")

    def test_depreciation_preview(self):
        client = self._login(self.treasury)
        response = client.get(
            reverse("assets:run_depreciation"),
            {"preview": "1", "year": 2024, "month": 1},
        )
        self.assertEqual(response.status_code, 200)

    def test_maintenance_blocked_on_disposed_asset(self):
        self.asset.status = "DISPOSED"
        self.asset.save()
        client = self._login(self.treasury)
        response = client.post(
            reverse("assets:maintenance_add", kwargs={"pk": self.asset.pk}),
            {
                "service_date": timezone.localdate().isoformat(),
                "description": "Should fail",
                "cost": "0",
                "vendor": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.asset.maintenance_logs.count(), 0)


class DepreciationLifecycleTests(TestCase):
    """CH-ENT-003A: checker fail-closed, no duplicate journals, register after APPROVED."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conference = Conference.objects.create(name="Dep Conf", code="DC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="DZ")
        district = District.objects.create(zone=zone, name="District", code="DD")
        cls.church = Church.objects.create(district=district, name="Dep Church", code="DCH1")
        cls.other_church = Church.objects.create(
            district=district, name="Other Church", code="DCH2"
        )
        ensure_asset_defaults_for_church(cls.church)
        ensure_asset_defaults_for_church(cls.other_church)
        create_default_accounts(cls.church)
        create_default_accounts(cls.other_church)
        cls.maker = User.objects.create_user(
            username="dep_maker",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.checker = User.objects.create_user(
            username="dep_checker",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        cls.district_admin = User.objects.create_user(
            username="dep_district_admin",
            password="test12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
        )
        cls.cross_checker = User.objects.create_user(
            username="dep_cross_pastor",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.other_church,
        )
        cls.member = User.objects.create_user(
            username="dep_member",
            password="test12345",
            role=UserRole.MEMBER,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="DCH1-FA-0100",
            name="Sound Desk",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.test.client import ContextList
        from unittest.mock import patch

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)

    def _capital_count(self):
        return Transaction.objects.filter(
            church=self.church,
            transaction_type="CAPITAL",
            description="Depreciation DCH1-FA-0100 2024-01",
        ).count()

    def _seed_stranded_pending_journal(self):
        from transactions import repositories as txn_repo
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        trx = txn_repo.create_transaction(
            transaction_type="CAPITAL",
            church=self.church,
            created_by=self.maker,
            description="Depreciation DCH1-FA-0100 2024-01",
            date=date(2024, 1, 28),
        )
        _post_line(trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("100.00"))
        _post_line(trx, _get_account(self.church, "ACCUMULATED_DEPRECIATION"), Decimal("-100.00"))
        validate_transaction_balance(trx)
        return trx

    def test_eligible_checker_posts_journal_and_register(self):
        entry = _complete_depreciation(
            self.asset, 2024, 1, self.maker, self.checker
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))
        self.assertEqual(entry.transaction.approval_status, "APPROVED")
        self.assertEqual(entry.transaction.approved_by_id, self.checker.id)
        self.assertEqual(self._capital_count(), 1)

    def test_user_none_creates_nothing(self):
        with self.assertRaises(AssetError) as ctx:
            post_depreciation_entry(self.asset, 2024, 1, None)
        self.assertIn("no journal or period entry was created", str(ctx.exception).lower())
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertEqual(self._capital_count(), 0)
        self.assertFalse(
            AssetDepreciationEntry.objects.filter(
                asset=self.asset, period_year=2024, period_month=1
            ).exists()
        )

    def test_ineligible_and_cross_church_checker_rejected(self):
        prepared = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=False
        )
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 1, self.member, allow_approval=True
            )
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 1, self.cross_checker, allow_approval=True
            )
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 1, self.district_admin, allow_approval=True
            )
        prepared.refresh_from_db()
        prepared.transaction.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertEqual(prepared.transaction.approval_status, "PENDING")
        self.assertIsNone(prepared.transaction.approved_by_id)
        self.assertEqual(self._capital_count(), 1)

    def test_maker_cannot_act_as_checker(self):
        entry = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=True
        )
        entry.refresh_from_db()
        entry.transaction.refresh_from_db()
        self.assertEqual(entry.transaction.approval_status, "PENDING")
        self.assertIsNone(entry.transaction.approved_by_id)
        self.assertFalse(entry.register_applied)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertEqual(self._capital_count(), 1)

    def test_stranded_pending_does_not_duplicate_or_false_success(self):
        stranded = self._seed_stranded_pending_journal()
        result = run_monthly_depreciation(self.church, 2024, 1, self.maker)
        self.assertEqual(result["posted"], 0)
        self.assertGreaterEqual(result["failed"], 1)
        self.assertEqual(self._capital_count(), 1)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        stranded.refresh_from_db()
        self.assertEqual(stranded.approval_status, "PENDING")
        self.assertFalse(
            AssetDepreciationEntry.objects.filter(
                asset=self.asset, period_year=2024, period_month=1
            ).exists()
        )

        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 1, self.checker, allow_approval=True
            )
        self.assertEqual(self._capital_count(), 1)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        stranded.refresh_from_db()
        self.assertEqual(stranded.approval_status, "PENDING")

    def test_repeated_invocation_is_idempotent(self):
        first = run_monthly_depreciation(
            self.church, 2024, 1, self.maker, allow_approval=False
        )
        approved = run_monthly_depreciation(
            self.church, 2024, 1, self.checker, allow_approval=True
        )
        second = run_monthly_depreciation(
            self.church, 2024, 1, self.checker, allow_approval=True
        )
        self.assertEqual(first["posted"], 0)
        self.assertEqual(first["pending"], 1)
        self.assertEqual(approved["posted"], 1)
        self.assertEqual(approved["failed"], 0)
        self.assertEqual(second["posted"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(self._capital_count(), 1)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))
        self.assertEqual(
            FinancialAuditLog.objects.filter(
                transaction__church=self.church, action="APPROVE"
            ).count(),
            1,
        )

    def test_celery_and_user_none_never_bypass_checker(self):
        from church_system.tasks import run_church_depreciation_task

        none_result = run_monthly_depreciation(self.church, 2024, 1, None)
        self.assertEqual(none_result["posted"], 0)
        self.assertGreaterEqual(none_result["failed"], 1)
        self.assertNotIn("posted", format_depreciation_run_summary(none_result))
        self.assertIn("failed", format_depreciation_run_summary(none_result))
        self.assertEqual(self._capital_count(), 0)

        task_result = run_church_depreciation_task.apply(
            args=[str(self.church.pk), 2024, 1, str(self.maker.pk)]
        ).get()
        self.assertEqual(task_result["posted"], 0)
        self.assertGreaterEqual(task_result["pending"], 1)
        self.assertEqual(self._capital_count(), 1)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))

        retry = run_church_depreciation_task.apply(
            args=[str(self.church.pk), 2024, 1, str(self.maker.pk)]
        ).get()
        self.assertEqual(retry["posted"], 0)
        self.assertEqual(self._capital_count(), 1)

        impersonated = run_church_depreciation_task.apply(
            args=[
                str(self.church.pk),
                2024,
                1,
                str(self.maker.pk),
                str(self.checker.pk),
            ]
        ).get()
        self.assertEqual(impersonated["posted"], 0)
        self.assertEqual(self._capital_count(), 1)
        entry = AssetDepreciationEntry.objects.get(
            asset=self.asset, period_year=2024, period_month=1
        )
        entry.transaction.refresh_from_db()
        self.assertEqual(entry.transaction.approval_status, "PENDING")
        self.assertIsNone(entry.transaction.approved_by_id)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))

    def test_register_changes_only_after_journal_approved(self):
        prepared = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=False
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertFalse(prepared.register_applied)
        entry = post_depreciation_entry(
            self.asset, 2024, 1, self.checker, allow_approval=True
        )
        entry.transaction.refresh_from_db()
        self.assertEqual(entry.transaction.approval_status, "APPROVED")
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))

    def test_http_authenticated_actor_is_checker_not_form_field(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from django.contrib.messages import get_messages

        enable_mfa_for_user(self.maker, generate_totp_secret(), [])
        self.maker.refresh_from_db()
        maker_client = Client()
        maker_client.login(username="dep_maker", password="test12345")
        session = maker_client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()

        nominated = maker_client.post(
            reverse("assets:run_depreciation"),
            {"year": 2024, "month": 1, "checker": str(self.checker.pk)},
        )
        self.assertEqual(nominated.status_code, 302)
        self.assertEqual(self._capital_count(), 1)
        entry = AssetDepreciationEntry.objects.get(
            asset=self.asset, period_year=2024, period_month=1
        )
        entry.transaction.refresh_from_db()
        self.assertEqual(entry.transaction.approval_status, "PENDING")
        self.assertIsNone(entry.transaction.approved_by_id)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))

        enable_mfa_for_user(self.checker, generate_totp_secret(), [])
        self.checker.refresh_from_db()
        checker_client = Client()
        checker_client.login(username="dep_checker", password="test12345")
        session = checker_client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        ok = checker_client.post(
            reverse("assets:run_depreciation"),
            {"year": 2024, "month": 1, "checker": str(self.member.pk)},
        )
        self.assertEqual(ok.status_code, 302)
        texts = " ".join(str(m) for m in get_messages(ok.wsgi_request))
        self.assertIn("completed", texts.lower())
        self.assertNotIn("1 posted", texts.lower())
        entry.refresh_from_db()
        entry.transaction.refresh_from_db()
        self.assertEqual(entry.transaction.approval_status, "APPROVED")
        self.assertEqual(entry.transaction.approved_by_id, self.checker.id)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))


class DepreciationWorkflowSchemaTests(TestCase):
    """CH-ENT-003A Phase 1: workflow fields and register_applied NBV filter."""

    @classmethod
    def setUpTestData(cls):
        seed_platform_category_templates()
        conference = Conference.objects.create(name="WF Conf", code="WFC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="WFZ")
        district = District.objects.create(zone=zone, name="District", code="WFD")
        cls.church = Church.objects.create(
            district=district, name="WF Church", code="WFCH"
        )
        ensure_asset_defaults_for_church(cls.church)
        cls.user = User.objects.create_user(
            username="wf_asset_user",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="WFCH-FA-0001",
            name="Piano",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("0.00"),
        )

    def test_historical_defaults_remain_on_register(self):
        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
        )
        self.assertEqual(entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED)
        self.assertTrue(entry.register_applied)
        self.assertIsNone(entry.initiated_by_id)
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("100.00")
        )
        self.asset.accumulated_depreciation = selectors.asset_depreciation_total(
            self.asset
        )
        self.asset.save(update_fields=["accumulated_depreciation"])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))
        self.assertEqual(self.asset.net_book_value, Decimal("1100.00"))

    def test_unapplied_entry_does_not_change_register_or_nbv(self):
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            workflow_status=AssetDepreciationEntry.WORKFLOW_POSTED,
            register_applied=True,
        )
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=2,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            register_applied=False,
            initiated_by=self.user,
        )
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("100.00")
        )
        self.asset.accumulated_depreciation = selectors.asset_depreciation_total(
            self.asset
        )
        self.asset.save(update_fields=["accumulated_depreciation"])
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))
        self.assertEqual(self.asset.net_book_value, Decimal("1100.00"))

    def test_asset_period_uniqueness_still_enforced(self):
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=3,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
        )
        with self.assertRaises(IntegrityError):
            AssetDepreciationEntry.objects.create(
                asset=self.asset,
                period_year=2024,
                period_month=3,
                amount=Decimal("50.00"),
                method_used="STRAIGHT_LINE",
                register_applied=False,
                workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            )

    def test_pending_workflow_does_not_imply_posted_journal_or_register(self):
        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=4,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            register_applied=False,
            initiated_by=self.user,
            posted_at=None,
            transaction=None,
        )
        self.assertIsNone(entry.transaction_id)
        self.assertIsNone(entry.posted_at)
        self.assertFalse(entry.register_applied)
        self.assertNotEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED
        )
        self.assertEqual(selectors.asset_depreciation_total(self.asset), Decimal("0.00"))
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertEqual(self.asset.net_book_value, Decimal("1200.00"))

    def test_duplicate_transaction_links_are_not_schema_forbidden(self):
        duplicates = (
            AssetDepreciationEntry.objects.exclude(transaction_id=None)
            .values("transaction_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )
        self.assertEqual(duplicates, 0)


class DepreciationHistoricalClassificationTests(TestCase):
    """CH-ENT-003A Phase 1A: FK-only reclassification of 0006 defaults."""

    @classmethod
    def setUpTestData(cls):
        seed_platform_category_templates()
        conference = Conference.objects.create(name="CL Conf", code="CLC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="CLZ")
        district = District.objects.create(zone=zone, name="District", code="CLD")
        cls.church = Church.objects.create(
            district=district, name="CL Church", code="CLCH"
        )
        ensure_asset_defaults_for_church(cls.church)
        cls.user = User.objects.create_user(
            username="cl_asset_user",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="CLCH-FA-0001",
            name="Organ",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("2400.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=24,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("50.00"),
        )

    def _journal(self, approval_status, *, is_voided=False):
        return Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status=approval_status,
            created_by=self.user,
            description="unrelated capital text",
            is_voided=is_voided,
        )

    def _entry(self, month, trx, **kwargs):
        defaults = {
            "asset": self.asset,
            "period_year": 2024,
            "period_month": month,
            "amount": Decimal("100.00"),
            "method_used": "STRAIGHT_LINE",
            "transaction": trx,
            "workflow_status": AssetDepreciationEntry.WORKFLOW_POSTED,
            "register_applied": True,
        }
        defaults.update(kwargs)
        return AssetDepreciationEntry.objects.create(**defaults)

    def test_pending_linked_becomes_unapplied_without_changing_stored_accum(self):
        from transactions.models import FinancialAuditLog

        trx = self._journal("PENDING")
        audit_before = FinancialAuditLog.objects.count()
        entry = self._entry(1, trx)
        stored = self.asset.accumulated_depreciation
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("0.00")
        )
        changed = classify_historical_depreciation_entries(AssetDepreciationEntry)
        self.assertEqual(changed, 1)
        entry.refresh_from_db()
        trx.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL
        )
        self.assertFalse(entry.register_applied)
        self.assertEqual(entry.transaction_id, trx.pk)
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertEqual(FinancialAuditLog.objects.count(), audit_before)
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("0.00")
        )

    def test_rejected_linked_is_unapplied_rejected(self):
        trx = self._journal("REJECTED")
        entry = self._entry(2, trx)
        stored = self.asset.accumulated_depreciation
        classify_historical_depreciation_entries(AssetDepreciationEntry)
        entry.refresh_from_db()
        trx.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_REJECTED
        )
        self.assertFalse(entry.register_applied)
        self.assertEqual(trx.approval_status, "REJECTED")
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("0.00")
        )

    def test_approved_linked_is_not_assumed_register_consistent(self):
        trx = self._journal("APPROVED")
        entry = self._entry(3, trx)
        self.asset.accumulated_depreciation = Decimal("50.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        classify_historical_depreciation_entries(AssetDepreciationEntry)
        entry.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED)
        self.assertTrue(entry.register_applied)
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("50.00"))
        self.assertNotEqual(
            selectors.asset_depreciation_total(self.asset),
            self.asset.accumulated_depreciation,
        )

    def test_voided_reversed_keeps_register_contribution(self):
        trx = self._journal("REVERSED", is_voided=True)
        entry = self._entry(4, trx)
        stored = self.asset.accumulated_depreciation
        classify_historical_depreciation_entries(AssetDepreciationEntry)
        entry.refresh_from_db()
        trx.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_RECOVERY_REQUIRED
        )
        self.assertTrue(entry.register_applied)
        self.assertTrue(trx.is_voided)
        self.assertEqual(trx.approval_status, "REVERSED")
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("100.00")
        )

    def test_null_transaction_legacy_stays_applied(self):
        entry = self._entry(5, None)
        stored = self.asset.accumulated_depreciation
        changed = classify_historical_depreciation_entries(AssetDepreciationEntry)
        self.assertEqual(changed, 0)
        entry.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED)
        self.assertTrue(entry.register_applied)
        self.assertIsNone(entry.transaction_id)
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertEqual(
            selectors.asset_depreciation_total(self.asset), Decimal("100.00")
        )

    def test_classification_is_idempotent(self):
        pending = self._entry(6, self._journal("PENDING"))
        rejected = self._entry(7, self._journal("REJECTED"))
        first = classify_historical_depreciation_entries(AssetDepreciationEntry)
        second = classify_historical_depreciation_entries(AssetDepreciationEntry)
        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        self.assertEqual(AssetDepreciationEntry.objects.filter(asset=self.asset).count(), 2)
        pending.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(
            pending.workflow_status, AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL
        )
        self.assertEqual(
            rejected.workflow_status, AssetDepreciationEntry.WORKFLOW_REJECTED
        )

    def test_migration_0007_forwards_ignores_live_helper(self):
        import importlib
        from unittest.mock import patch

        from django.apps import apps

        frozen = importlib.import_module(
            "assets.migrations.0007_classify_depreciation_workflow"
        )

        trx = self._journal("PENDING")
        entry = self._entry(8, trx)
        stored = self.asset.accumulated_depreciation
        with patch(
            "assets.depreciation_classification.classify_historical_depreciation_entries",
            side_effect=AssertionError("live helper must not run"),
        ):
            frozen.forwards(apps, None)
        entry.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL
        )
        self.assertFalse(entry.register_applied)
        self.assertEqual(self.asset.accumulated_depreciation, stored)


class DepreciationRegisterGuardTests(TestCase):
    """CH-ENT-003A Phase 1B: fail-closed full-sum register rewrite."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conference = Conference.objects.create(name="RG Conf", code="RGC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="RGZ")
        district = District.objects.create(zone=zone, name="District", code="RGD")
        cls.church = Church.objects.create(
            district=district, name="RG Church", code="RGCH"
        )
        ensure_asset_defaults_for_church(cls.church)
        create_default_accounts(cls.church)
        cls.maker = User.objects.create_user(
            username="rg_maker",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.checker = User.objects.create_user(
            username="rg_checker",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="RGCH-FA-0001",
            name="Organ",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("2400.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=24,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("0.00"),
        )

    def setUp(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)

    def _open_day(self, business_date):
        current = get_active_working_day(self.church)
        if current and current.date != business_date:
            close_working_day(self.church, self.checker)
        try:
            open_working_day(self.church, business_date, self.checker)
        except ValueError as exc:
            if "already open" not in str(exc).lower():
                raise

    def _journal(self, approval_status, *, is_voided=False, locked=False):
        return Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status=approval_status,
            created_by=self.maker,
            description="unrelated capital text",
            is_voided=is_voided,
            locked=locked,
        )

    def _entry(self, month, trx, **kwargs):
        defaults = {
            "asset": self.asset,
            "period_year": 2024,
            "period_month": month,
            "amount": Decimal("100.00"),
            "method_used": "STRAIGHT_LINE",
            "transaction": trx,
            "workflow_status": AssetDepreciationEntry.WORKFLOW_POSTED,
            "register_applied": True,
        }
        defaults.update(kwargs)
        return AssetDepreciationEntry.objects.create(**defaults)

    def _seed_pending_journal(self, month):
        from transactions import repositories as txn_repo
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        trx = txn_repo.create_transaction(
            transaction_type="CAPITAL",
            church=self.church,
            created_by=self.maker,
            description=f"Depreciation {self.asset.asset_code} 2024-{month:02d}",
            date=date(2024, month, 28),
        )
        _post_line(trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("100.00"))
        _post_line(trx, _get_account(self.church, "ACCUMULATED_DEPRECIATION"), Decimal("-100.00"))
        validate_transaction_balance(trx)
        return trx

    def _disable_ledger(self):
        policy = ensure_depreciation_policy(self.church)
        policy.post_depreciation_to_ledger = False
        policy.save(update_fields=["post_depreciation_to_ledger"])

    def test_approved_unreconciled_blocks_before_stored_nbv_changes(self):
        self._open_day(date(2024, 2, 28))
        trx = self._journal("APPROVED", locked=True)
        self._entry(1, trx)
        self.asset.accumulated_depreciation = Decimal("50.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        stored = self.asset.accumulated_depreciation
        audit_before = FinancialAuditLog.objects.filter(church=self.church).count()
        with self.assertRaises(AssetError) as ctx:
            post_depreciation_entry(
                self.asset, 2024, 2, self.checker, allow_approval=True
            )
        self.assertEqual(str(ctx.exception), REGISTER_RECONCILE_REQUIRED)
        self.asset.refresh_from_db()
        trx.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertFalse(
            AssetDepreciationEntry.objects.filter(
                asset=self.asset, period_year=2024, period_month=2
            ).exists()
        )
        self.assertEqual(
            FinancialAuditLog.objects.filter(church=self.church).count(), audit_before
        )
        with self.assertRaises(AssetError):
            _finalize_depreciation_register(
                self.asset, 2024, 2, Decimal("100.00"), self.maker, None
            )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, stored)

    def test_recovery_required_blocks_before_stored_nbv_changes(self):
        self._open_day(date(2024, 2, 28))
        trx = self._journal("REVERSED", is_voided=True)
        self._entry(
            1,
            trx,
            workflow_status=AssetDepreciationEntry.WORKFLOW_RECOVERY_REQUIRED,
            register_applied=True,
        )
        self.asset.accumulated_depreciation = Decimal("100.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        stored = self.asset.accumulated_depreciation
        with self.assertRaises(AssetError) as ctx:
            post_depreciation_entry(
                self.asset, 2024, 2, self.checker, allow_approval=True
            )
        self.assertEqual(str(ctx.exception), REGISTER_RECONCILE_REQUIRED)
        self.asset.refresh_from_db()
        trx.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, stored)
        self.assertTrue(trx.is_voided)
        self.assertEqual(trx.approval_status, "REVERSED")
        self.assertFalse(
            AssetDepreciationEntry.objects.filter(
                asset=self.asset, period_year=2024, period_month=2
            ).exists()
        )

    def test_blocked_recover_does_not_approve_pending_journal(self):
        self._open_day(date(2024, 2, 28))
        stale = self._journal("APPROVED", locked=True)
        self._entry(1, stale)
        self.asset.accumulated_depreciation = Decimal("50.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        pending = self._seed_pending_journal(2)
        self._entry(
            2,
            pending,
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            register_applied=False,
        )
        audit_before = FinancialAuditLog.objects.filter(church=self.church).count()
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 2, self.checker, allow_approval=True
            )
        pending.refresh_from_db()
        stale.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(pending.approval_status, "PENDING")
        self.assertFalse(pending.locked)
        self.assertEqual(stale.approval_status, "APPROVED")
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("50.00"))
        month2 = AssetDepreciationEntry.objects.get(
            asset=self.asset, period_year=2024, period_month=2
        )
        self.assertFalse(month2.register_applied)
        self.assertEqual(
            month2.workflow_status, AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL
        )
        self.assertEqual(
            FinancialAuditLog.objects.filter(church=self.church).count(), audit_before
        )
        result = run_monthly_depreciation(
            self.church, 2024, 2, self.checker, allow_approval=True
        )
        self.assertEqual(result["posted"], 0)
        self.assertGreaterEqual(result["failed"], 1)
        self.assertTrue(any("reconciliation" in err.lower() for err in result["errors"]))
        pending.refresh_from_db()
        self.assertEqual(pending.approval_status, "PENDING")

    def test_clean_history_still_posts(self):
        entry = _complete_depreciation(
            self.asset, 2024, 1, self.maker, self.checker
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))
        self.assertEqual(entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED)
        self.assertTrue(entry.register_applied)
        self._open_day(date(2024, 2, 28))
        second = _complete_depreciation(
            self.asset, 2024, 2, self.maker, self.checker
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("200.00"))
        self.assertEqual(second.transaction.approval_status, "APPROVED")

    def test_repeated_blocked_attempts_are_side_effect_free(self):
        self._open_day(date(2024, 2, 28))
        trx = self._journal("APPROVED", locked=True)
        entry = self._entry(1, trx)
        self.asset.accumulated_depreciation = Decimal("50.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        audit_before = FinancialAuditLog.objects.filter(church=self.church).count()
        capital_before = Transaction.objects.filter(
            church=self.church, transaction_type="CAPITAL"
        ).count()
        for _ in range(2):
            with self.assertRaises(AssetError):
                post_depreciation_entry(
                    self.asset, 2024, 2, self.checker, allow_approval=True
                )
        entry.refresh_from_db()
        trx.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("50.00"))
        self.assertEqual(entry.transaction_id, trx.pk)
        self.assertEqual(trx.approval_status, "APPROVED")
        self.assertEqual(
            FinancialAuditLog.objects.filter(church=self.church).count(), audit_before
        )
        self.assertEqual(
            Transaction.objects.filter(
                church=self.church, transaction_type="CAPITAL"
            ).count(),
            capital_before,
        )

    def test_null_fk_legacy_matching_stored_still_posts(self):
        self._open_day(date(2024, 2, 28))
        self._disable_ledger()
        self._entry(1, None)
        self.asset.accumulated_depreciation = Decimal("100.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        entry = post_depreciation_entry(self.asset, 2024, 2, self.maker)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("200.00"))
        self.assertIsNone(entry.transaction_id)
        self.assertTrue(entry.register_applied)

    def test_null_fk_disagreement_is_blocked_without_reclassifying(self):
        """Null-FK rows stay applied; disagreement still fail-closes the rewrite."""
        self._open_day(date(2024, 2, 28))
        self._disable_ledger()
        entry = self._entry(1, None)
        self.asset.accumulated_depreciation = Decimal("0.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        with self.assertRaises(AssetError):
            post_depreciation_entry(self.asset, 2024, 2, self.maker)
        entry.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertIsNone(entry.transaction_id)
        self.assertTrue(entry.register_applied)
        self.assertEqual(
            entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED
        )
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))


class DepreciationGenericApprovalGuardTests(TestCase):
    """CH-ENT-003A Phase 1C: generic approval cannot approve linked depreciation journals."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conference = Conference.objects.create(name="GA Conf", code="GAC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="GAZ")
        district = District.objects.create(zone=zone, name="District", code="GAD")
        cls.church = Church.objects.create(
            district=district, name="GA Church", code="GACH"
        )
        ensure_asset_defaults_for_church(cls.church)
        create_default_accounts(cls.church)
        cls.maker = User.objects.create_user(
            username="ga_maker",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.checker = User.objects.create_user(
            username="ga_checker",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="GACH-FA-0001",
            name="Piano",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("0.00"),
        )

    def setUp(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)

    def _linked_pending(self):
        trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="PENDING",
            created_by=self.maker,
            description="unrelated capital text",
            date=date(2024, 1, 28),
        )
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        _post_line(trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("100.00"))
        _post_line(trx, _get_account(self.church, "ACCUMULATED_DEPRECIATION"), Decimal("-100.00"))
        validate_transaction_balance(trx)
        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=trx,
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            register_applied=False,
        )
        return trx, entry

    def _snapshot(self, trx, entry):
        trx.refresh_from_db()
        entry.refresh_from_db()
        self.asset.refresh_from_db()
        return {
            "status": trx.approval_status,
            "approved_by": trx.approved_by_id,
            "locked": trx.locked,
            "workflow": entry.workflow_status,
            "applied": entry.register_applied,
            "accum": self.asset.accumulated_depreciation,
            "audits": FinancialAuditLog.objects.filter(transaction=trx).count(),
        }

    def test_generic_service_refuses_linked_depreciation_journal(self):
        trx, entry = self._linked_pending()
        before = self._snapshot(trx, entry)
        with self.assertRaises(ValueError) as ctx:
            approve_transaction(trx, self.checker)
        self.assertEqual(str(ctx.exception), DEPRECIATION_GENERIC_APPROVAL_REFUSED)
        self.assertNotIn("unrelated capital text", str(ctx.exception))
        self.assertEqual(self._snapshot(trx, entry), before)
        with self.assertRaises(ValueError):
            approve_module_journal(trx, self.checker)
        self.assertEqual(self._snapshot(trx, entry), before)

    def test_generic_approval_view_refuses_linked_depreciation_journal(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from django.contrib.messages import get_messages

        trx, entry = self._linked_pending()
        before = self._snapshot(trx, entry)
        enable_mfa_for_user(self.checker, generate_totp_secret(), [])
        self.checker.refresh_from_db()
        client = Client()
        client.login(username="ga_checker", password="test12345")
        session = client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        response = client.post(
            reverse("transactions:approve_transaction", kwargs={"pk": trx.pk})
        )
        self.assertEqual(response.status_code, 302)
        texts = " ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("depreciation register", texts.lower())
        self.assertEqual(self._snapshot(trx, entry), before)

    def test_admin_bulk_approve_cannot_bypass(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from transactions.admin import TransactionAdmin

        trx, entry = self._linked_pending()
        before = self._snapshot(trx, entry)
        request = RequestFactory().post("/admin/")
        request.user = self.checker
        request.session = {}
        request._messages = FallbackStorage(request)
        admin = TransactionAdmin(Transaction, AdminSite())
        admin.approve_selected(request, Transaction.objects.filter(pk=trx.pk))
        self.assertEqual(self._snapshot(trx, entry), before)

    def test_non_depreciation_journal_still_approves(self):
        expense = record_expense(
            church=self.church,
            created_by=self.maker,
            amount=Decimal("10.00"),
        )
        approved = approve_transaction(expense, self.checker)
        self.assertEqual(approved.approval_status, "APPROVED")
        self.assertTrue(approved.locked)
        self.assertEqual(approved.approved_by_id, self.checker.id)

    def test_null_fk_entry_does_not_block_unrelated_journal(self):
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
            workflow_status=AssetDepreciationEntry.WORKFLOW_POSTED,
            register_applied=True,
        )
        expense = record_expense(
            church=self.church,
            created_by=self.maker,
            amount=Decimal("15.00"),
        )
        approved = approve_transaction(expense, self.checker)
        self.assertEqual(approved.approval_status, "APPROVED")
        self.assertIsNone(
            AssetDepreciationEntry.objects.filter(transaction=expense).first()
        )

    def test_repeated_refused_attempts_are_side_effect_free(self):
        from approvals.services import record_approval

        trx, entry = self._linked_pending()
        before = self._snapshot(trx, entry)
        for _ in range(2):
            with self.assertRaises(ValueError):
                approve_transaction(trx, self.checker)
            with self.assertRaises(ValueError):
                record_approval(trx, self.checker)
        self.assertEqual(self._snapshot(trx, entry), before)
        self.assertEqual(trx.description, "unrelated capital text")

    def test_generic_service_refuses_unlinked_pending_capital(self):
        from transactions.models import TransactionLine
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="PENDING",
            created_by=self.maker,
            description="unrelated capital text",
            date=date(2024, 1, 28),
        )
        _post_line(
            trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("100.00")
        )
        _post_line(
            trx,
            _get_account(self.church, "ACCUMULATED_DEPRECIATION"),
            Decimal("-100.00"),
        )
        validate_transaction_balance(trx)
        line_sum = sum(
            TransactionLine.objects.filter(transaction=trx).values_list(
                "amount", flat=True
            )
        )
        audits = FinancialAuditLog.objects.filter(transaction=trx).count()
        with self.assertRaises(ValueError) as ctx:
            approve_transaction(trx, self.checker)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_GENERIC_APPROVAL_REFUSED)
        self.assertNotIn("unrelated capital text", str(ctx.exception))
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        self.assertFalse(trx.locked)
        self.assertEqual(
            FinancialAuditLog.objects.filter(transaction=trx).count(), audits
        )
        self.assertEqual(
            sum(
                TransactionLine.objects.filter(transaction=trx).values_list(
                    "amount", flat=True
                )
            ),
            line_sum,
        )
        from approvals.services import record_approval

        with self.assertRaises(ValueError):
            record_approval(trx, self.checker)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)

    def test_generic_view_and_admin_refuse_unlinked_pending_capital(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages import get_messages
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from transactions.admin import TransactionAdmin
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="PENDING",
            created_by=self.maker,
            description="unrelated capital text",
            date=date(2024, 1, 28),
        )
        _post_line(
            trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("40.00")
        )
        _post_line(
            trx,
            _get_account(self.church, "ACCUMULATED_DEPRECIATION"),
            Decimal("-40.00"),
        )
        validate_transaction_balance(trx)
        enable_mfa_for_user(self.checker, generate_totp_secret(), [])
        self.checker.refresh_from_db()
        client = Client()
        client.login(username="ga_checker", password="test12345")
        session = client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        response = client.post(
            reverse("transactions:approve_transaction", kwargs={"pk": trx.pk})
        )
        self.assertEqual(response.status_code, 302)
        texts = " ".join(str(m) for m in get_messages(response.wsgi_request))
        self.assertIn("source module cannot be established", texts.lower())
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        request = RequestFactory().post("/admin/")
        request.user = self.checker
        request.session = {}
        request._messages = FallbackStorage(request)
        admin = TransactionAdmin(Transaction, AdminSite())
        admin.approve_selected(request, Transaction.objects.filter(pk=trx.pk))
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)

    def _unlinked_pending_capital(self):
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="PENDING",
            created_by=self.maker,
            description="unrelated capital text",
            date=date(2024, 1, 28),
        )
        _post_line(
            trx, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("55.00")
        )
        _post_line(
            trx,
            _get_account(self.church, "ACCUMULATED_DEPRECIATION"),
            Decimal("-55.00"),
        )
        validate_transaction_balance(trx)
        return trx

    def test_module_journal_refuses_unlinked_pending_capital(self):
        from transactions.models import TransactionLine

        trx = self._unlinked_pending_capital()
        line_sum = sum(
            TransactionLine.objects.filter(transaction=trx).values_list(
                "amount", flat=True
            )
        )
        audits = FinancialAuditLog.objects.filter(transaction=trx).count()
        with self.assertRaises(ValueError) as ctx:
            approve_module_journal(trx, self.checker)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_MODULE_APPROVAL_REFUSED)
        self.assertNotIn("unrelated capital text", str(ctx.exception))
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        self.assertFalse(trx.locked)
        self.assertEqual(
            FinancialAuditLog.objects.filter(transaction=trx).count(), audits
        )
        self.assertEqual(
            sum(
                TransactionLine.objects.filter(transaction=trx).values_list(
                    "amount", flat=True
                )
            ),
            line_sum,
        )
        with self.assertRaises(ValueError) as ctx:
            approve_module_journal(trx)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_MODULE_APPROVAL_REFUSED)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)

    def test_module_journal_approves_capital_after_acquisition_fk(self):
        trx = self._unlinked_pending_capital()
        with self.assertRaises(ValueError) as ctx:
            approve_transaction(trx, self.checker)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_GENERIC_APPROVAL_REFUSED)
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="GACH-FA-ACQ1",
            name="Linked Van",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("55.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        asset.acquisition_transaction = trx
        asset.save(update_fields=["acquisition_transaction", "updated_at"])
        with self.assertRaises(ValueError) as ctx:
            approve_transaction(trx, self.checker)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_GENERIC_APPROVAL_REFUSED)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        approved = approve_module_journal(trx, self.checker)
        self.assertEqual(approved.approval_status, "APPROVED")
        self.assertTrue(approved.locked)
        self.assertEqual(approved.approved_by_id, self.checker.id)
        self.assertNotEqual(approved.created_by_id, approved.approved_by_id)

    def test_module_journal_approves_capital_after_disposal_fk(self):
        trx = self._unlinked_pending_capital()
        category = self.church.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="GACH-FA-DSP1",
            name="Linked Desk",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("55.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        asset.disposal_transaction = trx
        asset.save(update_fields=["disposal_transaction", "updated_at"])
        approved = approve_module_journal(trx, self.checker)
        self.assertEqual(approved.approval_status, "APPROVED")
        self.assertEqual(approved.approved_by_id, self.checker.id)

    def test_module_journal_non_capital_paths_unchanged(self):
        from transactions.services import (
            _get_account,
            _post_line,
            validate_transaction_balance,
        )

        expense = record_expense(
            church=self.church,
            created_by=self.maker,
            amount=Decimal("12.00"),
        )
        approved_expense = approve_module_journal(expense, self.checker)
        self.assertEqual(approved_expense.approval_status, "APPROVED")
        self.assertEqual(approved_expense.approved_by_id, self.checker.id)

        for txn_type in ("PAYROLL", "TRANSFER"):
            trx = Transaction.objects.create(
                church=self.church,
                transaction_type=txn_type,
                approval_status="PENDING",
                created_by=self.maker,
                description=f"{txn_type} module path",
                date=date(2024, 1, 28),
            )
            _post_line(trx, _get_account(self.church, "EXPENSE"), Decimal("3.00"))
            _post_line(trx, _get_account(self.church, "CASH"), Decimal("-3.00"))
            validate_transaction_balance(trx)
            approved = approve_module_journal(trx, self.checker)
            self.assertEqual(approved.approval_status, "APPROVED")
            self.assertEqual(approved.approved_by_id, self.checker.id)
            self.assertNotEqual(approved.created_by_id, approved.approved_by_id)

    def test_module_journal_refuses_capital_linked_to_other_church_asset(self):
        trx = self._unlinked_pending_capital()
        other = Church.objects.create(
            district=self.church.district,
            name="Other Guard Church",
            code="GACH2",
        )
        ensure_asset_defaults_for_church(other)
        category = other.asset_categories.first()
        asset = FixedAsset.objects.create(
            church=other,
            category=category,
            asset_code="GACH2-FA-X001",
            name="Cross Church Piano",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("55.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        asset.acquisition_transaction = trx
        asset.save(update_fields=["acquisition_transaction", "updated_at"])
        with self.assertRaises(ValueError) as ctx:
            approve_module_journal(trx, self.checker)
        self.assertEqual(str(ctx.exception), UNLINKED_CAPITAL_MODULE_APPROVAL_REFUSED)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        self.assertFalse(trx.locked)


class DepreciationAuthenticatedCheckerTests(TestCase):
    """CH-ENT-003A Phase 1D: persisted checker is the authenticated actor."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conference = Conference.objects.create(name="1D Conf", code="1DC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="1DZ")
        district = District.objects.create(zone=zone, name="District", code="1DD")
        cls.church = Church.objects.create(
            district=district, name="1D Church", code="1DCH"
        )
        ensure_asset_defaults_for_church(cls.church)
        create_default_accounts(cls.church)
        cls.maker = User.objects.create_user(
            username="d1d_maker",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.checker = User.objects.create_user(
            username="d1d_checker",
            password="test12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        cls.member = User.objects.create_user(
            username="d1d_member",
            password="test12345",
            role=UserRole.MEMBER,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="1DCH-FA-0001",
            name="Organ",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )

    def setUp(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)

    def test_failed_finalization_rolls_back_approval_and_register(self):
        from unittest.mock import patch

        prepared = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=False
        )
        trx = prepared.transaction
        approve_before = FinancialAuditLog.objects.filter(
            transaction=trx, action="APPROVE"
        ).count()
        with patch(
            "assets.services._finalize_depreciation_register",
            side_effect=AssetError("finalize failed"),
        ):
            with self.assertRaises(AssetError):
                post_depreciation_entry(
                    self.asset, 2024, 1, self.checker, allow_approval=True
                )
        trx.refresh_from_db()
        prepared.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertFalse(trx.locked)
        self.assertIsNone(trx.approved_by_id)
        self.assertFalse(prepared.register_applied)
        self.assertEqual(
            prepared.workflow_status, AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL
        )
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertEqual(
            FinancialAuditLog.objects.filter(transaction=trx, action="APPROVE").count(),
            approve_before,
        )

    def test_refused_attempt_creates_no_approval_audit_or_notification(self):
        from unittest.mock import patch

        prepared = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=False
        )
        trx = prepared.transaction
        with patch("transactions.notifications.notify_journal_outcome") as notify:
            with self.assertRaises(AssetError):
                post_depreciation_entry(
                    self.asset, 2024, 1, self.member, allow_approval=True
                )
            notify.assert_not_called()
        trx.refresh_from_db()
        prepared.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertIsNone(trx.approved_by_id)
        self.assertFalse(prepared.register_applied)
        self.assertEqual(
            FinancialAuditLog.objects.filter(transaction=trx, action="APPROVE").count(),
            0,
        )
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))

    def test_unlinked_journal_cannot_use_commit_or_description_recover(self):
        from transactions import repositories as txn_repo
        from transactions.services import _get_account, _post_line, validate_transaction_balance

        stranded = txn_repo.create_transaction(
            transaction_type="CAPITAL",
            church=self.church,
            created_by=self.maker,
            description="Depreciation 1DCH-FA-0001 2024-01",
            date=date(2024, 1, 28),
        )
        _post_line(
            stranded, _get_account(self.church, "DEPRECIATION_EXPENSE"), Decimal("100.00")
        )
        _post_line(
            stranded,
            _get_account(self.church, "ACCUMULATED_DEPRECIATION"),
            Decimal("-100.00"),
        )
        validate_transaction_balance(stranded)
        with self.assertRaises(ValueError) as ctx:
            _commit_journal_approval(stranded, self.checker)
        self.assertEqual(str(ctx.exception), DEPRECIATION_GENERIC_APPROVAL_REFUSED)
        stranded.refresh_from_db()
        self.assertEqual(stranded.approval_status, "PENDING")
        with self.assertRaises(AssetError):
            post_depreciation_entry(
                self.asset, 2024, 1, self.checker, allow_approval=True
            )
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        self.assertFalse(
            AssetDepreciationEntry.objects.filter(
                asset=self.asset, period_year=2024, period_month=1
            ).exists()
        )
        stranded.refresh_from_db()
        self.assertEqual(stranded.approval_status, "PENDING")
        self.assertIsNone(stranded.approved_by_id)

    def test_commit_requires_authenticated_eligible_checker(self):
        prepared = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, allow_approval=False
        )
        trx = prepared.transaction
        with self.assertRaises(ValueError):
            _commit_journal_approval(trx, self.maker)
        with self.assertRaises(ValueError):
            _commit_journal_approval(trx, self.member)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "PENDING")
        approved = post_depreciation_entry(
            self.asset, 2024, 1, self.checker, allow_approval=True
        )
        approved.transaction.refresh_from_db()
        self.assertEqual(approved.transaction.approved_by_id, self.checker.id)
        self.assertTrue(approved.register_applied)


class DepreciationRegisterInventoryTests(TestCase):
    """CH-ENT-003A Phase 1F: read-only register inventory; FK identity only."""

    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        seed_platform_category_templates()
        conference = Conference.objects.create(name="Inv Conf", code="IVC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="IVZ")
        district = District.objects.create(zone=zone, name="District", code="IVD")
        cls.church = Church.objects.create(
            district=district, name="Inv Church", code="IVCH"
        )
        cls.other = Church.objects.create(
            district=district, name="Other Inv", code="IVCO"
        )
        ensure_asset_defaults_for_church(cls.church)
        ensure_asset_defaults_for_church(cls.other)
        create_default_accounts(cls.church)
        create_default_accounts(cls.other)
        cls.user = User.objects.create_user(
            username="inv_user",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="IVCH-FA-0001",
            name="Pulpit",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("0.00"),
        )

    def _snapshot(self):
        from members.models import MemberAuditLog
        from sitecontrol.models import PlatformAuditLog
        from transactions.models import TransactionLine

        return {
            "entries": AssetDepreciationEntry.objects.count(),
            "entry_rows": list(
                AssetDepreciationEntry.objects.order_by("pk").values_list(
                    "pk",
                    "workflow_status",
                    "register_applied",
                    "transaction_id",
                    "amount",
                )
            ),
            "transactions": Transaction.objects.count(),
            "transaction_rows": list(
                Transaction.objects.order_by("pk").values_list(
                    "pk",
                    "approval_status",
                    "locked",
                    "is_voided",
                    "description",
                )
            ),
            "lines": TransactionLine.objects.count(),
            "accum": list(
                FixedAsset.objects.order_by("pk").values_list(
                    "pk",
                    "accumulated_depreciation",
                    "status",
                    "acquisition_transaction_id",
                    "disposal_transaction_id",
                )
            ),
            "financial_audits": FinancialAuditLog.objects.count(),
            "member_audits": MemberAuditLog.objects.count(),
            "platform_audits": PlatformAuditLog.objects.count(),
        }

    def _capital(self, church, created_by, *, description="unrelated capital text"):
        from transactions import repositories as txn_repo

        return txn_repo.create_transaction(
            transaction_type="CAPITAL",
            church=church,
            created_by=created_by,
            description=description,
            date=date(2024, 1, 28),
        )

    def test_linked_entries_identified_only_through_fk(self):
        from assets.register_inventory import build_depreciation_register_inventory

        trx = self._capital(self.church, self.user)
        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=trx,
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
            register_applied=False,
        )
        orphan = self._capital(
            self.church,
            self.user,
            description=f"Depreciation {self.asset.asset_code} 2024-01",
        )
        inventory = build_depreciation_register_inventory([self.church])
        linked_ids = inventory["categories"]["linked_entries"]["ids"]
        self.assertIn(str(entry.pk), linked_ids)
        self.assertNotIn(str(orphan.pk), linked_ids)
        candidate_ids = inventory["categories"][
            "unclassified_pending_capital_candidates"
        ]["ids"]
        self.assertIn(str(orphan.pk), candidate_ids)
        self.assertNotIn(str(trx.pk), candidate_ids)

    def test_null_fk_entries_remain_visible(self):
        from assets.register_inventory import build_depreciation_register_inventory

        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
        )
        inventory = build_depreciation_register_inventory([self.church])
        self.assertIn(
            str(entry.pk), inventory["categories"]["null_fk_entries"]["ids"]
        )
        self.assertNotIn(
            str(entry.pk), inventory["categories"]["linked_entries"]["ids"]
        )

    def test_unlinked_pending_capital_is_candidate_not_confirmed(self):
        from assets.register_inventory import build_depreciation_register_inventory

        trx = self._capital(self.church, self.user)
        inventory = build_depreciation_register_inventory([self.church])
        block = inventory["categories"]["unclassified_pending_capital_candidates"]
        self.assertIn(str(trx.pk), block["ids"])
        record = next(row for row in block["records"] if row["id"] == str(trx.pk))
        self.assertFalse(record["confirmed_depreciation"])
        self.assertFalse(record["source_module_known"])
        self.assertEqual(record["kind"], "unclassified_pending_capital_candidate")

    def test_acquisition_and_disposal_fks_excluded_from_candidates(self):
        from assets.register_inventory import build_depreciation_register_inventory

        acq = self._capital(self.church, self.user)
        disp = self._capital(self.church, self.user)
        stray = self._capital(self.church, self.user)
        self.asset.acquisition_transaction = acq
        self.asset.disposal_transaction = disp
        self.asset.save(
            update_fields=["acquisition_transaction", "disposal_transaction"]
        )
        inventory = build_depreciation_register_inventory([self.church])
        ids = inventory["categories"]["unclassified_pending_capital_candidates"]["ids"]
        self.assertNotIn(str(acq.pk), ids)
        self.assertNotIn(str(disp.pk), ids)
        self.assertIn(str(stray.pk), ids)

    def test_aggregate_mismatch_detected(self):
        from assets.register_inventory import build_depreciation_register_inventory

        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
            register_applied=True,
        )
        self.asset.accumulated_depreciation = Decimal("0.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        inventory = build_depreciation_register_inventory([self.church])
        mismatch = inventory["categories"]["aggregate_mismatch_assets"]
        self.assertIn(str(self.asset.pk), mismatch["ids"])
        self.assertEqual(mismatch["records"][0]["outcome"], "mismatch")
        self.assertNotIn(
            str(self.asset.pk),
            inventory["categories"]["matching_unproven_assets"]["ids"],
        )

    def test_matching_totals_with_uncertain_history_are_unproven(self):
        from assets.register_inventory import build_depreciation_register_inventory

        trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            locked=True,
            created_by=self.user,
            description="unrelated capital text",
            date=date(2024, 1, 28),
        )
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=trx,
            workflow_status=AssetDepreciationEntry.WORKFLOW_POSTED,
            register_applied=True,
        )
        self.asset.accumulated_depreciation = Decimal("100.00")
        self.asset.save(update_fields=["accumulated_depreciation"])
        inventory = build_depreciation_register_inventory([self.church])
        self.assertIn(
            str(self.asset.pk),
            inventory["categories"]["matching_unproven_assets"]["ids"],
        )
        self.assertIn(
            str(AssetDepreciationEntry.objects.get(asset=self.asset).pk),
            inventory["categories"]["approved_unproven_entries"]["ids"],
        )
        self.assertNotIn(
            str(self.asset.pk),
            inventory["categories"]["aggregate_mismatch_assets"]["ids"],
        )

    def test_recovery_voided_reversed_failed_and_unexpected_are_listed(self):
        from assets.register_inventory import build_depreciation_register_inventory

        voided = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            is_voided=True,
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        reversed_trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="REVERSED",
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        category = self.church.asset_categories.first()
        failed_asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="IVCH-FA-0002",
            name="Chair",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("120.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        unexpected_asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="IVCH-FA-0003",
            name="Lamp",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("60.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )
        void_entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("10.00"),
            method_used="STRAIGHT_LINE",
            transaction=voided,
            workflow_status=AssetDepreciationEntry.WORKFLOW_RECOVERY_REQUIRED,
            register_applied=True,
        )
        reversed_entry = AssetDepreciationEntry.objects.create(
            asset=failed_asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("10.00"),
            method_used="STRAIGHT_LINE",
            transaction=reversed_trx,
            workflow_status=AssetDepreciationEntry.WORKFLOW_POSTED,
            register_applied=True,
        )
        failed_entry = AssetDepreciationEntry.objects.create(
            asset=failed_asset,
            period_year=2024,
            period_month=2,
            amount=Decimal("10.00"),
            method_used="STRAIGHT_LINE",
            workflow_status=AssetDepreciationEntry.WORKFLOW_FAILED,
            register_applied=True,
        )
        unexpected = AssetDepreciationEntry.objects.create(
            asset=unexpected_asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("5.00"),
            method_used="STRAIGHT_LINE",
        )
        AssetDepreciationEntry.objects.filter(pk=unexpected.pk).update(
            workflow_status="NOT_A_WORKFLOW"
        )
        inventory = build_depreciation_register_inventory([self.church])
        recovery_ids = inventory["categories"]["recovery_required_entries"]["ids"]
        self.assertIn(str(void_entry.pk), recovery_ids)
        self.assertIn(str(reversed_entry.pk), recovery_ids)
        self.assertIn(str(failed_entry.pk), recovery_ids)
        self.assertIn(
            str(unexpected.pk),
            inventory["categories"]["unexpected_workflow_entries"]["ids"],
        )
        self.assertIn(str(void_entry.pk), inventory["overlaps"]["linked_and_recovery"])

    def test_category_counts_match_unique_ids(self):
        from assets.register_inventory import build_depreciation_register_inventory

        trx = self._capital(self.church, self.user)
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=trx,
            register_applied=False,
            workflow_status=AssetDepreciationEntry.WORKFLOW_AWAITING_APPROVAL,
        )
        inventory = build_depreciation_register_inventory([self.church])
        for key, block in inventory["categories"].items():
            self.assertEqual(block["count"], len(set(_ for _ in block["ids"])))
            self.assertLessEqual(len(block["ids"]), block["count"])
            self.assertEqual(
                inventory["overlaps"]["mismatch_and_matching_unproven_assets"],
                [],
                msg=key,
            )
        self.assertEqual(
            inventory["overlaps"]["null_fk_and_linked"],
            [],
        )

    def test_inventory_performs_no_writes(self):
        """Compares snapshotted fields only.

        Covered: AssetDepreciationEntry (pk, workflow_status, register_applied,
        transaction_id, amount), Transaction (pk, approval_status, locked,
        is_voided, description), TransactionLine count, FixedAsset (pk,
        accumulated_depreciation, status, acquisition/disposal FKs), and
        Financial/Member/Platform audit *counts*. Other tables and unlisted
        fields are outside this evidence.
        """
        from django.core.management import call_command
        from io import StringIO

        from assets.register_inventory import build_depreciation_register_inventory

        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("100.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
        )
        before = self._snapshot()
        build_depreciation_register_inventory([self.church])
        out = StringIO()
        call_command(
            "inventory_depreciation_register",
            church="IVCH",
            stdout=out,
        )
        self.assertEqual(self._snapshot(), before)
        text = out.getvalue()
        self.assertIn("read-only", text.lower())
        self.assertIn("null_fk_entries: count=1 shown=1 omitted=0 truncated=False", text)
        self.assertIn("does not enforce rbac", text.lower())
        self.assertIn("Church scope: IVCH", text)
        self.assertIn("restricts displayed identifiers only", text)

    def test_unlinked_approved_capital_is_candidate_not_confirmed(self):
        from assets.register_inventory import build_depreciation_register_inventory

        approved = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            locked=True,
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        pending = self._capital(self.church, self.user)
        inventory = build_depreciation_register_inventory([self.church])
        gap = inventory["categories"]["unclassified_approved_capital_candidates"]
        pending_block = inventory["categories"][
            "unclassified_pending_capital_candidates"
        ]
        self.assertIn(str(approved.pk), gap["ids"])
        self.assertNotIn(str(pending.pk), gap["ids"])
        self.assertNotIn(str(approved.pk), pending_block["ids"])
        record = next(row for row in gap["records"] if row["id"] == str(approved.pk))
        self.assertFalse(record["confirmed_depreciation"])
        self.assertFalse(record["source_module_known"])
        self.assertEqual(record["kind"], "unclassified_approved_capital_candidate")
        linked_approved = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            locked=True,
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=2,
            amount=Decimal("10.00"),
            method_used="STRAIGHT_LINE",
            transaction=linked_approved,
        )
        inventory = build_depreciation_register_inventory([self.church])
        gap = inventory["categories"]["unclassified_approved_capital_candidates"]
        self.assertNotIn(str(linked_approved.pk), gap["ids"])
        self.assertEqual(
            inventory["overlaps"]["pending_candidates_and_approved_candidates"],
            [],
        )

    def test_identifier_limit_does_not_change_population_count(self):
        from assets.register_inventory import build_depreciation_register_inventory

        first = self._capital(self.church, self.user)
        second = self._capital(self.church, self.user)
        inventory = build_depreciation_register_inventory(
            [self.church], identifier_limit=1
        )
        block = inventory["categories"]["unclassified_pending_capital_candidates"]
        self.assertEqual(block["count"], 2)
        self.assertEqual(block["shown"], 1)
        self.assertEqual(block["omitted"], 1)
        self.assertTrue(block["truncated"])
        self.assertEqual(len(block["ids"]), 1)
        zero = build_depreciation_register_inventory(
            [self.church], identifier_limit=0
        )
        zero_block = zero["categories"]["unclassified_pending_capital_candidates"]
        self.assertEqual(zero_block["count"], 2)
        self.assertEqual(zero_block["shown"], 0)
        self.assertEqual(zero_block["omitted"], 2)
        self.assertEqual(zero_block["ids"], [])
        self.assertIn(block["ids"][0], {str(first.pk), str(second.pk)})
        with self.assertRaises(ValueError):
            build_depreciation_register_inventory(
                [self.church], identifier_limit=-1
            )

    def test_church_scope_excludes_other_church(self):
        from assets.register_inventory import build_depreciation_register_inventory

        local = self._capital(self.church, self.user)
        other_user = User.objects.create_user(
            username="inv_other",
            password="test12345",
            role=UserRole.TREASURY,
            church=self.other,
        )
        foreign = self._capital(self.other, other_user)
        other_asset = FixedAsset.objects.create(
            church=self.other,
            category=self.other.asset_categories.first(),
            asset_code="IVCO-FA-0001",
            name="Foreign pulpit",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("500.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("0.00"),
        )
        foreign_entry = AssetDepreciationEntry.objects.create(
            asset=other_asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("25.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
        )
        scoped = build_depreciation_register_inventory([self.church])
        ids = scoped["categories"]["unclassified_pending_capital_candidates"]["ids"]
        self.assertIn(str(local.pk), ids)
        self.assertNotIn(str(foreign.pk), ids)
        self.assertNotIn(
            str(foreign_entry.pk),
            scoped["categories"]["null_fk_entries"]["ids"],
        )
        for block in scoped["categories"].values():
            for record in block["records"]:
                if "church_code" in record:
                    self.assertEqual(record["church_code"], "IVCH")
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command(
            "inventory_depreciation_register",
            church="IVCH",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("Church scope: IVCH", text)
        self.assertNotIn(str(foreign.pk), text)
        self.assertNotIn(str(foreign_entry.pk), text)

    def test_unfamiliar_workflow_status_is_unexpected_not_understood(self):
        from assets.register_inventory import (
            UNDERSTOOD_WORKFLOW_STATUSES,
            build_depreciation_register_inventory,
        )

        entry = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("5.00"),
            method_used="STRAIGHT_LINE",
        )
        AssetDepreciationEntry.objects.filter(pk=entry.pk).update(
            workflow_status="WRITTEN_OFF"
        )
        self.assertNotIn("WRITTEN_OFF", UNDERSTOOD_WORKFLOW_STATUSES)
        inventory = build_depreciation_register_inventory([self.church])
        self.assertIn(
            str(entry.pk),
            inventory["categories"]["unexpected_workflow_entries"]["ids"],
        )
        self.assertNotIn(
            str(entry.pk),
            inventory["categories"]["recovery_required_entries"]["ids"],
        )

    def test_command_requires_explicit_scope(self):
        from django.core.management import call_command, CommandError
        from io import StringIO

        with self.assertRaises(CommandError):
            call_command("inventory_depreciation_register", stdout=StringIO())
        out = StringIO()
        call_command(
            "inventory_depreciation_register",
            all_churches=True,
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("ALL CHURCHES", text)
        self.assertIn("does not enforce rbac", text.lower())

    def test_command_unknown_church_code_fails_closed(self):
        from django.core.management import call_command, CommandError
        from io import StringIO

        with self.assertRaises(CommandError) as raised:
            call_command(
                "inventory_depreciation_register",
                church="NO-SUCH-CHURCH",
                stdout=StringIO(),
            )
        self.assertIn("was not found", str(raised.exception))

    def test_command_church_uuid_lookup(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command(
            "inventory_depreciation_register",
            church=str(self.church.pk),
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn(f"Church scope: IVCH id={self.church.pk}", text)
        self.assertNotIn("ALL CHURCHES", text)

    def test_command_duplicate_church_code_fails_closed(self):
        from django.core.management import call_command, CommandError
        from io import StringIO

        district_two = District.objects.create(
            zone=self.church.district.zone,
            name="Other District",
            code="IVD2",
        )
        duplicate = Church.objects.create(
            district=district_two,
            name="Duplicate Code Church",
            code="IVCH",
        )
        with self.assertRaises(CommandError) as raised:
            call_command(
                "inventory_depreciation_register",
                church="IVCH",
                stdout=StringIO(),
            )
        message = str(raised.exception)
        self.assertIn("matches 2 churches", message)
        self.assertIn(str(self.church.pk), message)
        self.assertIn(str(duplicate.pk), message)
        out = StringIO()
        call_command(
            "inventory_depreciation_register",
            church=str(self.church.pk),
            stdout=out,
        )
        scoped = out.getvalue()
        self.assertIn(f"Church scope: IVCH id={self.church.pk}", scoped)
        self.assertNotIn(str(duplicate.pk), scoped)

    def test_unlinked_rejected_reversed_voided_capital_are_review_candidates(self):
        from assets.register_inventory import build_depreciation_register_inventory

        pending = self._capital(self.church, self.user)
        approved = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            locked=True,
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        rejected = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="REJECTED",
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        reversed_trx = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="REVERSED",
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        voided = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="APPROVED",
            is_voided=True,
            created_by=self.user,
            date=date(2024, 1, 28),
        )
        inventory = build_depreciation_register_inventory([self.church])
        pending_ids = inventory["categories"][
            "unclassified_pending_capital_candidates"
        ]["ids"]
        approved_ids = inventory["categories"][
            "unclassified_approved_capital_candidates"
        ]["ids"]
        other = inventory["categories"]["unclassified_other_capital_candidates"]
        other_ids = other["ids"]
        self.assertIn(str(pending.pk), pending_ids)
        self.assertIn(str(approved.pk), approved_ids)
        self.assertIn(str(rejected.pk), other_ids)
        self.assertIn(str(reversed_trx.pk), other_ids)
        self.assertIn(str(voided.pk), other_ids)
        self.assertNotIn(str(voided.pk), approved_ids)
        self.assertNotIn(str(pending.pk), other_ids)
        self.assertNotIn(str(approved.pk), other_ids)
        record = next(row for row in other["records"] if row["id"] == str(rejected.pk))
        self.assertFalse(record["confirmed_depreciation"])
        self.assertFalse(record["source_module_known"])
        self.assertEqual(record["kind"], "unclassified_other_capital_candidate")
        self.assertEqual(
            inventory["overlaps"]["pending_candidates_and_other_candidates"],
            [],
        )
        self.assertEqual(
            inventory["overlaps"]["approved_candidates_and_other_candidates"],
            [],
        )
        self.assertNotIn(
            str(rejected.pk),
            inventory["categories"]["recovery_required_entries"]["ids"],
        )

    def test_entry_limit_ids_match_records_deterministically(self):
        from assets.register_inventory import build_depreciation_register_inventory

        later = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=2,
            amount=Decimal("20.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
        )
        earlier = AssetDepreciationEntry.objects.create(
            asset=self.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("10.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
        )
        first = build_depreciation_register_inventory(
            [self.church], identifier_limit=1
        )
        second = build_depreciation_register_inventory(
            [self.church], identifier_limit=1
        )
        block = first["categories"]["null_fk_entries"]
        self.assertEqual(block["count"], 2)
        self.assertEqual(block["shown"], 1)
        self.assertEqual(block["omitted"], 1)
        self.assertEqual(block["ids"], [str(earlier.pk)])
        self.assertEqual(block["records"][0]["id"], str(earlier.pk))
        self.assertEqual(block["ids"], second["categories"]["null_fk_entries"]["ids"])
        self.assertNotEqual(block["ids"][0], str(later.pk))


class DepreciationAdminReadonlyTests(TestCase):
    """Phase 1I/1K: admin cannot edit NBV, workflow flags, or journal FKs.

    Does not claim protection against ORM or SQL updates.
    """

    @classmethod
    def setUpTestData(cls):
        seed_platform_category_templates()
        conference = Conference.objects.create(name="Adm Conf", code="ADC")
        zone = Zone.objects.create(conference=conference, name="Zone", code="ADZ")
        district = District.objects.create(zone=zone, name="District", code="ADD")
        cls.church = Church.objects.create(
            district=district, name="Adm Church", code="ADCH"
        )
        ensure_asset_defaults_for_church(cls.church)
        cls.user = User.objects.create_user(
            username="adm_asset_user",
            password="test12345",
            role=UserRole.TREASURY,
            church=cls.church,
            is_staff=True,
        )
        category = cls.church.asset_categories.first()
        cls.asset = FixedAsset.objects.create(
            church=cls.church,
            category=category,
            asset_code="ADCH-FA-0001",
            name="Pew",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
            accumulated_depreciation=Decimal("25.00"),
        )
        cls.entry = AssetDepreciationEntry.objects.create(
            asset=cls.asset,
            period_year=2024,
            period_month=1,
            amount=Decimal("25.00"),
            method_used="STRAIGHT_LINE",
            transaction=None,
            workflow_status=AssetDepreciationEntry.WORKFLOW_POSTED,
            register_applied=True,
        )

    def test_admin_forms_exclude_protected_fields_and_ignore_posted_values(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from assets.admin import AssetDepreciationEntryAdmin, FixedAssetAdmin

        request = RequestFactory().get("/admin/")
        request.user = self.user
        asset_admin = FixedAssetAdmin(FixedAsset, AdminSite())
        entry_admin = AssetDepreciationEntryAdmin(
            AssetDepreciationEntry, AdminSite()
        )
        readonly = asset_admin.get_readonly_fields(request, self.asset)
        self.assertIn("accumulated_depreciation", readonly)
        self.assertIn("acquisition_transaction", readonly)
        self.assertIn("disposal_transaction", readonly)
        self.assertNotIn(
            "acquisition_transaction", getattr(asset_admin, "list_editable", ()) or ()
        )
        self.assertNotIn(
            "disposal_transaction", getattr(asset_admin, "list_editable", ()) or ()
        )
        self.assertIn(
            "workflow_status",
            entry_admin.get_readonly_fields(request, self.entry),
        )
        self.assertIn(
            "register_applied",
            entry_admin.get_readonly_fields(request, self.entry),
        )
        asset_form_class = asset_admin.get_form(request, self.asset)
        entry_form_class = entry_admin.get_form(request, self.entry)
        self.assertNotIn("accumulated_depreciation", asset_form_class.base_fields)
        self.assertNotIn("acquisition_transaction", asset_form_class.base_fields)
        self.assertNotIn("disposal_transaction", asset_form_class.base_fields)
        self.assertNotIn("workflow_status", entry_form_class.base_fields)
        self.assertNotIn("register_applied", entry_form_class.base_fields)

        asset_form = asset_form_class(instance=self.asset)
        payload = {}
        for name, field in asset_form.fields.items():
            value = asset_form.initial.get(name, getattr(self.asset, name, ""))
            payload[name] = value
        payload["accumulated_depreciation"] = "999.00"
        decoy = Transaction.objects.create(
            church=self.church,
            transaction_type="CAPITAL",
            approval_status="PENDING",
            created_by=self.user,
            description="admin decoy capital",
            date=date(2024, 1, 28),
        )
        payload["acquisition_transaction"] = str(decoy.pk)
        payload["disposal_transaction"] = str(decoy.pk)
        posted_asset = asset_form_class(payload, instance=self.asset)
        self.assertTrue(posted_asset.is_valid(), posted_asset.errors)
        posted_asset.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("25.00"))
        self.assertIsNone(self.asset.acquisition_transaction_id)
        self.assertIsNone(self.asset.disposal_transaction_id)

        entry_form = entry_form_class(instance=self.entry)
        entry_payload = {}
        for name, field in entry_form.fields.items():
            value = entry_form.initial.get(name, getattr(self.entry, name, ""))
            entry_payload[name] = value
        entry_payload["workflow_status"] = AssetDepreciationEntry.WORKFLOW_FAILED
        entry_payload["register_applied"] = False
        posted_entry = entry_form_class(entry_payload, instance=self.entry)
        self.assertTrue(posted_entry.is_valid(), posted_entry.errors)
        posted_entry.save()
        self.entry.refresh_from_db()
        self.assertEqual(
            self.entry.workflow_status, AssetDepreciationEntry.WORKFLOW_POSTED
        )
        self.assertTrue(self.entry.register_applied)
