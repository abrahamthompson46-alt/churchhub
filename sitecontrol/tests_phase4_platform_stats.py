"""CH-SEC-009 — platform stats / health alerts denomination scoping (Option A)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from organization.models import Church, Conference, District, Zone
from sitecontrol.models import (
    Denomination,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)
from sitecontrol.services import platform_stats, tenant_health_alerts

User = get_user_model()


class PlatformStatsScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.denom_a = Denomination.objects.create(code="ps-a", name="Stats Denom A")
        cls.denom_b = Denomination.objects.create(code="ps-b", name="Stats Denom B")
        conf_a = Conference.objects.create(
            name="Stats Conf A", code="PSCA", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            name="Stats Conf B", code="PSCB", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="PSZA", name="Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="PSZB", name="Zone B")
        dist_a = District.objects.create(zone=zone_a, code="PSDA", name="Dist A")
        dist_b = District.objects.create(zone=zone_b, code="PSDB", name="Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="PSCHA", name="Alpha Chapel"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="PSCHB", name="Beta Sanctuary"
        )
        plan = SubscriptionPlan.objects.create(
            code="ps-plan",
            name="Stats Plan",
            max_users=1,
            is_active=True,
        )
        TenantSubscription.objects.create(
            church=cls.church_a,
            plan=plan,
            status="ACTIVE",
        )
        TenantSubscription.objects.create(
            church=cls.church_b,
            plan=plan,
            status="ACTIVE",
        )
        # Over-limit on B only (max_users=1, two users on B).
        User.objects.create_user(
            username="ps_user_b1",
            password="pass12345",
            church=cls.church_b,
        )
        User.objects.create_user(
            username="ps_user_b2",
            password="pass12345",
            church=cls.church_b,
        )
        User.objects.create_user(
            username="ps_user_a1",
            password="pass12345",
            church=cls.church_a,
        )
        TenantApplication.objects.create(
            church_name="Pending A",
            church_code="PEND-A",
            contact_name="Applicant A",
            contact_email="a@example.com",
            applicant_username="pend_a",
            denomination=cls.denom_a,
            status="PENDING",
            application_type="NEW_HIERARCHY",
        )
        TenantApplication.objects.create(
            church_name="Pending B",
            church_code="PEND-B",
            contact_name="Applicant B",
            contact_email="b@example.com",
            applicant_username="pend_b",
            denomination=cls.denom_b,
            status="PENDING",
            application_type="NEW_HIERARCHY",
        )

        cls.owner = User.objects.create_user(
            username="ps_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        cls.readonly_a = User.objects.create_user(
            username="ps_readonly_a",
            password="pass12345",
            is_platform_user=True,
            platform_role="READONLY",
        )
        cls.readonly_a.managed_denominations.add(cls.denom_a)
        cls.support_a = User.objects.create_user(
            username="ps_support_a",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
        )
        cls.support_a.managed_denominations.add(cls.denom_a)
        cls.unanchored_ro = User.objects.create_user(
            username="ps_unanchored_ro",
            password="pass12345",
            is_platform_user=True,
            platform_role="READONLY",
        )

    def test_owner_sees_global_church_counts(self):
        stats = platform_stats(self.owner)
        self.assertGreaterEqual(stats["churches"], 2)
        self.assertGreaterEqual(stats["pending_applications"], 2)

    def test_readonly_same_denomination_only(self):
        stats = platform_stats(self.readonly_a)
        self.assertEqual(stats["churches"], 1)
        self.assertEqual(stats["conferences"], 1)
        self.assertEqual(stats["pending_applications"], 1)

    def test_readonly_cross_denomination_excluded(self):
        stats = platform_stats(self.readonly_a)
        self.assertEqual(stats["churches"], 1)
        # Only denom A church counted — not B.
        global_stats = platform_stats(self.owner)
        self.assertGreater(global_stats["churches"], stats["churches"])

    def test_unanchored_readonly_sees_zero_tenant_counts(self):
        stats = platform_stats(self.unanchored_ro)
        self.assertEqual(stats["churches"], 0)
        self.assertEqual(stats["conferences"], 0)
        self.assertEqual(stats["pending_applications"], 0)

    def test_over_limit_alert_hides_other_denom_church_names(self):
        from unittest import mock

        with mock.patch(
            "sitecontrol.services.subscription_enforced", return_value=True
        ):
            alerts = tenant_health_alerts(self.readonly_a)
        detail_blob = " ".join(a.get("detail", "") for a in alerts)
        self.assertNotIn("Beta Sanctuary", detail_blob)

        with mock.patch(
            "sitecontrol.services.subscription_enforced", return_value=True
        ):
            owner_alerts = tenant_health_alerts(self.owner)
        owner_blob = " ".join(a.get("detail", "") for a in owner_alerts)
        self.assertIn("Beta Sanctuary", owner_blob)

    def test_support_scoped_matches_readonly(self):
        self.assertEqual(
            platform_stats(self.support_a)["churches"],
            platform_stats(self.readonly_a)["churches"],
        )
