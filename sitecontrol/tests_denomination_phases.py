"""Platform denomination phases 2–6 — operator scoping, terminology, billing."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from organization.models import Church, Conference, District, Zone
from sitecontrol.denomination_services import ensure_builtin_denominations
from sitecontrol.models import Denomination, PlatformAuditLog
from sitecontrol.test_support import SiteControlClientHarness

User = get_user_model()


class DenominationPlatformPhasesTests(SiteControlClientHarness, TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_denominations()
        cls.sda = Denomination.objects.get(code="sda")
        cls.cop = Denomination.objects.get(code="cop")

        cls.global_op = User.objects.create_user(
            username="platform_global",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        cls.scoped_op = User.objects.create_user(
            username="platform_cop",
            password="pass12345",
            is_platform_user=True,
            platform_role="BILLING",
        )
        cls.scoped_op.managed_denominations.add(cls.cop)

        conf = Conference.objects.create(name="COP Conf", code="COPC", denomination=cls.cop)
        zone = Zone.objects.create(conference=conf, name="COP Z", code="COPZ")
        district = District.objects.create(zone=zone, name="COP D", code="COPD")
        cls.cop_church = Church.objects.create(district=district, name="COP Church", code="COPCH")

    def setUp(self):
        self.disable_privileged_mfa()

    def test_scoped_operator_sees_only_assigned_denominations(self):
        from sitecontrol.platform_access import get_operator_denominations

        global_denoms = list(get_operator_denominations(self.global_op).values_list("code", flat=True))
        scoped_denoms = list(get_operator_denominations(self.scoped_op).values_list("code", flat=True))
        self.assertIn("sda", global_denoms)
        self.assertIn("cop", global_denoms)
        self.assertEqual(scoped_denoms, ["cop"])

    def test_scoped_operator_blocked_from_other_denomination_detail(self):
        client = Client()
        client.login(username="platform_cop", password="pass12345")
        response = client.get(reverse("sitecontrol:denomination_detail", kwargs={"pk": self.sda.pk}))
        self.assertEqual(response.status_code, 403)

    def test_scoped_operator_can_open_assigned_billing_rollups(self):
        client = Client()
        client.login(username="platform_cop", password="pass12345")
        response = client.get(reverse("sitecontrol:denomination_billing_rollups"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CoP ChurchHub")

    def test_terminology_form_saves_labels(self):
        client = Client()
        client.login(username="platform_global", password="pass12345")
        url = reverse("sitecontrol:denomination_terminology", kwargs={"pk": self.cop.pk})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {}
        for key in ("general_conference", "union", "conference", "zone", "district", "church"):
            post_data[f"{key}_enabled"] = "on" if key in ("conference", "zone", "district", "church") else ""
            post_data[f"{key}_label"] = f"Label {key}"
            post_data[f"{key}_label_plural"] = f"Labels {key}"
        response = client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.cop.refresh_from_db()
        self.assertEqual(self.cop.hierarchy_labels["church"]["label"], "Label church")

    def test_tenant_list_filtered_for_scoped_operator(self):
        client = Client()
        client.login(username="platform_cop", password="pass12345")
        response = client.get(reverse("sitecontrol:tenant_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COP Church")

    def test_audit_log_includes_denomination_on_approve(self):
        from sitecontrol.models import TenantApplication

        app = TenantApplication.objects.create(
            denomination=self.cop,
            church_name="New COP",
            church_code="NEWCOP",
            contact_name="Pastor",
            contact_email="pastor@cop.test",
            applicant_username="cop_pastor",
        )
        PlatformAuditLog.objects.create(
            user=self.global_op,
            denomination=self.cop,
            action="APPLICATION_APPROVE",
            summary="Test approve",
            target_model="TenantApplication",
            target_id=str(app.pk),
            details={"denomination_id": str(self.cop.pk)},
        )
        from sitecontrol.billing_services import denomination_audit_log

        entries = list(denomination_audit_log(self.cop, limit=5))
        self.assertTrue(any(e.action == "APPLICATION_APPROVE" for e in entries))
