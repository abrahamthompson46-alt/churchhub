"""Tests for fixed asset register — services, RBAC, and views."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import AssetCategoryTemplate, AssetPolicyAuditLog, FixedAsset
from assets.rbac import churches_in_asset_scope
from assets.services import (
    AssetError,
    approve_asset,
    assert_segregation_of_duties,
    calculate_monthly_depreciation,
    dispose_asset,
    ensure_asset_defaults_for_church,
    generate_asset_code,
    post_depreciation_entry,
    preview_monthly_depreciation,
    reject_asset,
    seed_platform_category_templates,
    submit_asset_for_approval,
    validate_depreciation_period,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from transactions.models import Transaction
from transactions.services import create_default_accounts, open_working_day

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
            role=UserRole.DISTRICT_PASTOR,
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
        post_depreciation_entry(asset, 2024, 1, self.approver)
        with self.assertRaises(AssetError):
            post_depreciation_entry(asset, 2024, 1, self.approver)

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
        dispose_asset(asset, self.approver, notes="Scrapped")
        asset.refresh_from_db()
        self.assertEqual(asset.status, "DISPOSED")
        self.assertIsNotNone(asset.disposal_transaction_id)
        self.assertTrue(Transaction.objects.filter(pk=asset.disposal_transaction_id).exists())

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

    def test_churches_in_scope_district_pastor(self):
        scoped = churches_in_asset_scope(self.overseer)
        self.assertEqual(scoped.count(), 1)
        self.assertEqual(scoped.first().pk, self.church1.pk)


class AssetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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

    def _login(self, user):
        client = Client()
        client.login(username=user.username, password="test12345")
        session = client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()
        return client

    def test_asset_list_requires_manage_permission(self):
        member = User.objects.create_user(
            username="memberuser",
            password="test12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        client = self._login(member)
        response = client.get(reverse("assets:asset_list"))
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
