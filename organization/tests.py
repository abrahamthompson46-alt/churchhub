"""Tests for organization hierarchy views and services."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from organization.models import (
    Church,
    Conference,
    District,
    OrganizationAuditLog,
    Zone,
)
from organization.services import (
    create_church,
    onboard_full_hierarchy,
    reconcile_organization,
    set_church_active,
    transfer_church,
    update_church,
)
from permissions.scoping import get_manageable_churches
from sitecontrol.models import Denomination
from transactions.models import Account

User = get_user_model()


class OrganizationTestMixin:
    @classmethod
    def setUpTestData(cls):
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save(update_fields=["enforce_subscription_limits"])
        clear_settings_cache()

        cls.denomination = Denomination.objects.create(
            name="Test Denomination",
            code="TD",
            is_active=True,
        )
        cls.other_denomination = Denomination.objects.create(
            name="Other Denomination",
            code="OD",
            is_active=True,
        )
        cls.conference = Conference.objects.create(
            code="T1",
            name="Test Conference",
            denomination=cls.denomination,
        )
        cls.other_conference = Conference.objects.create(
            code="OT1",
            name="Other Conference",
            denomination=cls.other_denomination,
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z1", name="Test Zone")
        cls.other_zone = Zone.objects.create(
            conference=cls.other_conference, code="Z1", name="Other Zone"
        )
        cls.district = District.objects.create(zone=cls.zone, code="D1", name="Test District")
        cls.other_district = District.objects.create(
            zone=cls.other_zone, code="D1", name="Other District"
        )
        cls.district2 = District.objects.create(zone=cls.zone, code="D2", name="Second District")
        cls.church = Church.objects.create(
            district=cls.district,
            code="C1",
            name="Test Church",
            financials_provisioned=True,
        )
        cls.other_church = Church.objects.create(
            district=cls.other_district,
            code="C1",
            name="Other Church",
            financials_provisioned=True,
        )


class ServiceTests(OrganizationTestMixin, TestCase):
    def test_create_church_sets_up_financials(self):
        church, created = create_church(
            district=self.district,
            name="New Church",
            code="NC01",
            setup_financials=True,
        )
        self.assertTrue(created)
        self.assertTrue(church.financials_provisioned)
        self.assertGreaterEqual(Account.objects.filter(church=church).count(), 7)
        self.assertTrue(
            OrganizationAuditLog.objects.filter(
                action="CREATE", entity_type="Church", entity_id=church.pk
            ).exists()
        )

    def test_onboard_full_hierarchy(self):
        church, created = onboard_full_hierarchy(
            conference_name="New Conf",
            conference_code="NC",
            zone_name="New Zone",
            zone_code="NZ",
            district_name="New District",
            district_code="ND",
            church_name="Onboard Church",
            church_code="OC01",
            setup_financials=True,
            denomination=self.denomination,
        )
        self.assertTrue(created)
        self.assertEqual(church.district.zone.conference.code, "NC")
        self.assertEqual(church.district.zone.conference.denomination_id, self.denomination.pk)
        self.assertTrue(Account.objects.filter(church=church).exists())

    def test_onboard_rejects_cross_denomination_conference_collision(self):
        with self.assertRaises(ValueError):
            onboard_full_hierarchy(
                conference_name="Stolen Conf",
                conference_code="OT1",
                zone_name="Zone",
                zone_code="Z9",
                district_name="District",
                district_code="D9",
                church_name="Bad Church",
                church_code="BAD1",
                denomination=self.denomination,
            )

    def test_transfer_church_within_denomination(self):
        church, _ = create_church(
            district=self.district,
            name="Movable Church",
            code="MV01",
            setup_financials=False,
        )
        transfer_church(church, self.district2, reason="Realignment")
        church.refresh_from_db()
        self.assertEqual(church.district_id, self.district2.pk)
        self.assertTrue(
            OrganizationAuditLog.objects.filter(action="TRANSFER", entity_id=church.pk).exists()
        )

    def test_transfer_church_rejects_cross_denomination(self):
        with self.assertRaises(ValidationError):
            transfer_church(self.church, self.other_district)

    def test_update_church_rejects_district_change(self):
        with self.assertRaises(ValueError):
            update_church(self.church, district=self.district2)

    def test_set_church_active_creates_audit_log(self):
        set_church_active(self.church, False)
        self.church.refresh_from_db()
        self.assertFalse(self.church.is_active)
        self.assertTrue(
            OrganizationAuditLog.objects.filter(
                action="DEACTIVATE", entity_id=self.church.pk
            ).exists()
        )

    def test_reconcile_organization_reports_unprovisioned(self):
        church, _ = create_church(
            district=self.district,
            name="Unprovisioned",
            code="UP01",
            setup_financials=False,
        )
        church.financials_provisioned = False
        church.save(update_fields=["financials_provisioned"])
        issues = reconcile_organization(denomination=self.denomination)
        kinds = {i["kind"] for i in issues}
        self.assertIn("unprovisioned_financials", kinds)


class ViewTests(OrganizationTestMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Python 3.14 + Django test client: Context.__copy__ crashes in
        # store_rendered_templates. Skip the copy; status/content asserts still work.
        from unittest.mock import patch

        from django.test.client import ContextList

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
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret

        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin",
            password="pass12345",
            email="admin@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        enable_mfa_for_user(self.admin, generate_totp_secret(), [])
        self.secretary = User.objects.create_user(
            username="secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.district_pastor = User.objects.create_user(
            username="district_pastor",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
        )
        self._mfa_session_key = SESSION_MFA_VERIFIED

    def _login(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[self._mfa_session_key] = True
        session.save()

    def test_hierarchy_requires_hierarchy_role(self):
        self._login("secretary")
        response = self.client.get(reverse("organization:hierarchy"))
        self.assertEqual(response.status_code, 403)

    def test_hierarchy_accessible_to_super_admin(self):
        self._login("admin")
        response = self.client.get(reverse("organization:hierarchy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.conference.name)

    def test_hierarchy_search_filters_results(self):
        self._login("admin")
        response = self.client.get(reverse("organization:hierarchy"), {"q": "Test Church"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Church")

    def test_hierarchy_export_csv(self):
        self._login("admin")
        response = self.client.get(reverse("organization:hierarchy"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_district_pastor_redirected_to_district_detail(self):
        self._login("district_pastor")
        response = self.client.get(reverse("organization:hierarchy"))
        self.assertRedirects(
            response,
            reverse("organization:district_detail", kwargs={"pk": self.district.pk}),
        )

    def test_district_pastor_cannot_create_conference(self):
        self._login("district_pastor")
        response = self.client.post(
            reverse("organization:conference_create"),
            {"name": "Blocked Conference", "code": "BC", "denomination": str(self.denomination.pk)},
        )
        self.assertEqual(response.status_code, 403)

    def test_conference_create(self):
        self._login("admin")
        response = self.client.post(
            reverse("organization:conference_create"),
            {
                "name": "Second Conference",
                "code": "SC",
                "denomination": str(self.denomination.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Conference.objects.filter(code="SC").exists())

    def test_church_create_with_district_query_param(self):
        from sitecontrol.services import clear_settings_cache
        from sitecontrol.models import SiteSettings

        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save(update_fields=["enforce_subscription_limits"])
        clear_settings_cache()

        self._login("admin")
        url = reverse("organization:church_create") + f"?district={self.district.pk}"
        response = self.client.post(
            url,
            {
                "district": str(self.district.pk),
                "name": "Query Param Church",
                "code": "QPC1",
                "address": "1 Test Rd",
            },
        )
        if response.status_code != 302:
            form = response.context.get("form") if response.context else None
            self.fail(
                f"Expected redirect, got {response.status_code}; "
                f"form errors={getattr(form, 'errors', None)}"
            )
        church = Church.objects.get(code="QPC1")
        self.assertEqual(church.district_id, self.district.pk)
        self.assertEqual(church.name, "Query Param Church")

    def test_district_pastor_cannot_create_church_in_other_district(self):
        self._login("district_pastor")
        url = reverse("organization:church_create") + f"?district={self.district2.pk}"
        response = self.client.post(
            url,
            {
                "district": str(self.district2.pk),
                "name": "Cross District",
                "code": "XD1",
            },
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(Church.objects.filter(code="XD1").exists())

    def test_church_onboard_hides_full_mode_for_district_pastor(self):
        self._login("district_pastor")
        response = self.client.get(reverse("organization:church_onboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Full Setup")

    def test_church_detail_shows_stats(self):
        self._login("admin")
        response = self.client.get(reverse("organization:church_detail", kwargs={"pk": self.church.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.church.name)

    def test_church_detail_idor_other_denomination_denied(self):
        self._login("admin")
        session = self.client.session
        session["active_denomination_id"] = str(self.denomination.pk)
        session.save()
        response = self.client.get(
            reverse("organization:church_detail", kwargs={"pk": self.other_church.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_conference_detail(self):
        self._login("admin")
        response = self.client.get(reverse("organization:conference_detail", kwargs={"pk": self.conference.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.zone.name)

    def test_church_toggle_active(self):
        self._login("admin")
        response = self.client.post(
            reverse("organization:church_toggle_active", kwargs={"pk": self.church.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.church.refresh_from_db()
        self.assertFalse(self.church.is_active)

    def test_inactive_church_excluded_from_manageable_churches(self):
        # Non-superadmin church-scoped users see active churches only.
        set_church_active(self.church, False)
        manageable = get_manageable_churches(self.secretary)
        self.assertNotIn(self.church, list(manageable))
        # Institution SUPER_ADMIN includes inactive churches in denomination scope.
        self.assertIn(self.church, list(get_manageable_churches(self.admin)))

    def test_church_transfer_requires_global_admin(self):
        self._login("district_pastor")
        response = self.client.get(
            reverse("organization:church_transfer", kwargs={"pk": self.church.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_church_transfer_by_super_admin(self):
        self._login("admin")
        response = self.client.post(
            reverse("organization:church_transfer", kwargs={"pk": self.church.pk}),
            {"district": str(self.district2.pk), "reason": "Administrative"},
        )
        self.assertEqual(response.status_code, 302)
        self.church.refresh_from_db()
        self.assertEqual(self.church.district_id, self.district2.pk)
