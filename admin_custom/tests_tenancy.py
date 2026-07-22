"""Django admin tenancy — platform OWNER vs denomination-scoped operators."""

from datetime import date
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from admin_custom.tenancy import (
    admin_operator_is_global,
    filter_admin_qs_by_church,
    filter_admin_qs_by_org_unit,
    scoped_admin_churches,
)
from assets.admin import FixedAssetAdmin
from assets.models import FixedAsset
from assets.services import ensure_asset_defaults_for_church, seed_platform_category_templates
from meetings.admin import MeetingAdmin
from meetings.models import Meeting
from organization.models import Church, Conference, District, Zone
from remittance.admin import RemittancePolicyAdmin
from remittance.models import RemittancePolicy
from sitecontrol.denomination_services import ensure_builtin_denominations
from sitecontrol.models import Denomination
from sitecontrol.rbac import ROLE_OWNER, ROLE_SECURITY

User = get_user_model()


class AdminTenancyHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_denominations()
        seed_platform_category_templates()
        cls.sda = Denomination.objects.get(code="sda")
        cls.cop = Denomination.objects.get(code="cop")

        sda_conf = Conference.objects.create(
            name="SDA Conf", code="SDAC-ADM", denomination=cls.sda
        )
        sda_zone = Zone.objects.create(conference=sda_conf, name="SDA Z", code="SDAZ-ADM")
        sda_dist = District.objects.create(zone=sda_zone, name="SDA D", code="SDAD-ADM")
        cls.sda_church = Church.objects.create(
            district=sda_dist, name="SDA Church Admin", code="SDACH-ADM"
        )

        cop_conf = Conference.objects.create(
            name="COP Conf", code="COPC-ADM", denomination=cls.cop
        )
        cop_zone = Zone.objects.create(conference=cop_conf, name="COP Z", code="COPZ-ADM")
        cop_dist = District.objects.create(zone=cop_zone, name="COP D", code="COPD-ADM")
        cls.cop_church = Church.objects.create(
            district=cop_dist, name="COP Church Admin", code="COPCH-ADM"
        )

        ensure_asset_defaults_for_church(cls.sda_church)
        ensure_asset_defaults_for_church(cls.cop_church)

        cls.owner = User.objects.create_user(
            username="admin_owner",
            password="pass12345",
            is_platform_user=True,
            is_staff=True,
            is_superuser=True,
            platform_role=ROLE_OWNER,
        )
        cls.security = User.objects.create_user(
            username="admin_security",
            password="pass12345",
            is_platform_user=True,
            is_staff=True,
            is_superuser=True,
            platform_role=ROLE_SECURITY,
        )
        cls.security.managed_denominations.add(cls.cop)

        cls.unassigned = User.objects.create_user(
            username="admin_unassigned",
            password="pass12345",
            is_platform_user=True,
            is_staff=True,
            is_superuser=True,
            platform_role=ROLE_SECURITY,
        )

        cls.sda_asset = FixedAsset.objects.create(
            church=cls.sda_church,
            category=cls.sda_church.asset_categories.first(),
            asset_code="SDACH-ADM-FA-0001",
            name="SDA Piano",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1000.00"),
            useful_life_months=60,
            depreciation_method="STRAIGHT_LINE",
        )
        cls.cop_asset = FixedAsset.objects.create(
            church=cls.cop_church,
            category=cls.cop_church.asset_categories.first(),
            asset_code="COPCH-ADM-FA-0001",
            name="COP Piano",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("800.00"),
            useful_life_months=60,
            depreciation_method="STRAIGHT_LINE",
        )

        cls.sda_policy = RemittancePolicy.objects.create(
            offering_type="TITHE",
            application_scope="GROSS_COLLECTION",
            unit_type="CHURCH",
            unit_id=cls.sda_church.pk,
            retain_percent=Decimal("40.00"),
            remit_percent=Decimal("60.00"),
            effective_from=date(2024, 1, 1),
        )
        cls.cop_policy = RemittancePolicy.objects.create(
            offering_type="TITHE",
            application_scope="GROSS_COLLECTION",
            unit_type="CHURCH",
            unit_id=cls.cop_church.pk,
            retain_percent=Decimal("40.00"),
            remit_percent=Decimal("60.00"),
            effective_from=date(2024, 1, 1),
        )

        when = timezone.now()
        cls.sda_meeting = Meeting.objects.create(
            church=cls.sda_church,
            title="SDA Board",
            scheduled_at=when,
        )
        cls.cop_meeting = Meeting.objects.create(
            church=cls.cop_church,
            title="COP Board",
            scheduled_at=when,
        )

    def test_owner_is_global_security_is_not(self):
        self.assertTrue(admin_operator_is_global(self.owner))
        self.assertFalse(admin_operator_is_global(self.security))
        self.assertFalse(admin_operator_is_global(self.unassigned))

    def test_scoped_admin_churches(self):
        owner_ids = set(scoped_admin_churches(self.owner).values_list("pk", flat=True))
        security_ids = set(scoped_admin_churches(self.security).values_list("pk", flat=True))
        unassigned_ids = set(
            scoped_admin_churches(self.unassigned).values_list("pk", flat=True)
        )
        self.assertIn(self.sda_church.pk, owner_ids)
        self.assertIn(self.cop_church.pk, owner_ids)
        self.assertEqual(security_ids, {self.cop_church.pk})
        self.assertEqual(unassigned_ids, set())

    def test_filter_assets_by_church(self):
        qs = FixedAsset.objects.all()
        security_qs = filter_admin_qs_by_church(qs, self.security)
        self.assertEqual(set(security_qs.values_list("pk", flat=True)), {self.cop_asset.pk})
        owner_qs = filter_admin_qs_by_church(qs, self.owner)
        self.assertEqual(owner_qs.count(), qs.count())

    def test_filter_policies_by_org_unit(self):
        qs = RemittancePolicy.objects.all()
        security_qs = filter_admin_qs_by_org_unit(qs, self.security)
        ids = set(security_qs.values_list("pk", flat=True))
        self.assertIn(self.cop_policy.pk, ids)
        self.assertNotIn(self.sda_policy.pk, ids)

    def test_fixed_asset_admin_queryset(self):
        factory = RequestFactory()
        site = AdminSite()
        ma = FixedAssetAdmin(FixedAsset, site)

        req = factory.get("/admin/assets/fixedasset/")
        req.user = self.security
        ids = set(ma.get_queryset(req).values_list("pk", flat=True))
        self.assertEqual(ids, {self.cop_asset.pk})

        req.user = self.owner
        ids = set(ma.get_queryset(req).values_list("pk", flat=True))
        self.assertIn(self.sda_asset.pk, ids)
        self.assertIn(self.cop_asset.pk, ids)

    def test_remittance_policy_admin_queryset(self):
        factory = RequestFactory()
        ma = RemittancePolicyAdmin(RemittancePolicy, AdminSite())
        req = factory.get("/admin/remittance/remittancepolicy/")
        req.user = self.security
        ids = set(ma.get_queryset(req).values_list("pk", flat=True))
        self.assertIn(self.cop_policy.pk, ids)
        self.assertNotIn(self.sda_policy.pk, ids)

    def test_meeting_admin_queryset(self):
        factory = RequestFactory()
        ma = MeetingAdmin(Meeting, AdminSite())
        req = factory.get("/admin/meetings/meeting/")
        req.user = self.security
        ids = set(ma.get_queryset(req).values_list("pk", flat=True))
        self.assertEqual(ids, {self.cop_meeting.pk})
