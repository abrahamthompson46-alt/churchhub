"""Tests for reports app — security, scoping, and builders."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.test.client import ContextList
from django.urls import reverse

from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
from accounts.models import UserRole
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from reports.models import ReportAccessAuditLog
from reports.services import (
    _churches_in_scope,
    build_report,
    resolve_date_range,
    user_may_access_report,
)
from sitecontrol.models import SiteSettings

User = get_user_model()


class ReportsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

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

    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        from sitecontrol.models import Denomination

        denom = Denomination.objects.create(
            code="rep-t1", name="Reports Test Denom", is_active=True
        )
        conf = Conference.objects.create(code="R1", name="R Conf", denomination=denom)
        zone = Zone.objects.create(conference=conf, code="R1", name="R Zone")
        dist = District.objects.create(zone=zone, code="R1", name="R Dist")
        cls.church = Church.objects.create(district=dist, code="R1", name="R Church")
        conf2 = Conference.objects.create(code="R2", name="R Conf 2", denomination=denom)
        zone2 = Zone.objects.create(conference=conf2, code="R2", name="R Zone 2")
        dist2 = District.objects.create(zone=zone2, code="R2", name="R Dist 2")
        cls.other_church = Church.objects.create(district=dist2, code="R2", name="Other Church")
        cls.denomination = denom

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.treasury = User.objects.create_user(
            username="treasury_r", password="pass12345", role=UserRole.TREASURY, church=self.church
        )
        enable_mfa_for_user(self.treasury, generate_totp_secret(), [])

    def _login(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[SESSION_MFA_VERIFIED] = True
        session.save()

    def _request(self, user=None):
        request = self.factory.get("/")
        request.user = user or self.treasury
        request.session = {}
        return request

    def test_resolve_monthly_range(self):
        start, end = resolve_date_range("monthly")
        self.assertLessEqual(start, end)

    def test_financial_summary_report(self):
        data = build_report("financial_summary", self._request(), period="monthly")
        self.assertEqual(data["title"], "Financial Summary")
        self.assertIn("rows", data)
        self.assertTrue(any("Operating net" in str(r[0]) for r in data["rows"]))

    def test_report_index_requires_login(self):
        self.assertEqual(self.client.get(reverse("reports:index")).status_code, 302)

    def test_report_index_for_treasury(self):
        self._login("treasury_r")
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)

    def test_hierarchy_rollup_requires_overseer_access(self):
        overseer = User.objects.create_user(
            username="overseer_r",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
            denomination=self.denomination,
        )
        data = build_report("hierarchy_rollup", self._request(overseer), period="monthly")
        self.assertEqual(data["title"], "District Roll-up")
        self.assertEqual(data["headers"][0], "District")

    def test_hierarchy_rollup_denied_for_treasury(self):
        self._login("treasury_r")
        response = self.client.get(reverse("reports:run", args=["hierarchy_rollup"]))
        self.assertEqual(response.status_code, 403)

    def test_forged_church_id_does_not_leak_other_church(self):
        """Treasury cannot pull another church via church_id query param."""
        scoped = _churches_in_scope(self._request(), church_id=self.other_church.pk)
        self.assertEqual(scoped.count(), 0)

    def test_own_church_id_still_works(self):
        scoped = _churches_in_scope(self._request(), church_id=self.church.pk)
        self.assertEqual(list(scoped), [self.church])

    def test_non_overseer_form_has_no_hierarchy_fields(self):
        from reports.forms import ReportFilterForm
        from reports.services import get_hierarchy_context

        form = ReportFilterForm(user=self.treasury, hierarchy=get_hierarchy_context(self.treasury))
        self.assertFalse(form.show_hierarchy_filters)
        self.assertNotIn("conference", form.fields)
        self.assertNotIn("church", form.fields)

    def test_overseer_form_shows_full_hierarchy(self):
        from reports.forms import ReportFilterForm
        from reports.services import get_hierarchy_context

        overseer = User.objects.create_user(
            username="overseer_form",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
            denomination=self.denomination,
        )
        form = ReportFilterForm(user=overseer, hierarchy=get_hierarchy_context(overseer))
        self.assertTrue(form.show_hierarchy_filters)
        for key in ("conference", "zone", "district", "church"):
            self.assertIn(key, form.fields)

    def test_advanced_report_denied_without_feature(self):
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        settings_obj = SiteSettings.load()
        settings_obj.global_enable_advanced_reports = False
        settings_obj.save(update_fields=["global_enable_advanced_reports"])
        clear_settings_cache()
        self.assertFalse(
            user_may_access_report(self.treasury, "trial_balance", active_church=self.church)
        )

    def test_advanced_report_fail_closed_without_church(self):
        self.assertFalse(user_may_access_report(self.treasury, "trial_balance", active_church=None))

    def test_cash_position_not_tied_to_payroll_feature(self):
        """cash_position requires advanced_reports only, not payroll."""
        from reports.registry import REPORT_CATALOG

        meta = REPORT_CATALOG["cash_position"]
        self.assertTrue(meta.get("requires_advanced"))
        self.assertNotIn("requires_feature", meta)

    def test_run_report_writes_audit_log(self):
        self._login("treasury_r")
        before = ReportAccessAuditLog.objects.count()
        response = self.client.get(reverse("reports:run", args=["financial_summary"]), {"period": "monthly"})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(ReportAccessAuditLog.objects.count(), before)
        log = ReportAccessAuditLog.objects.latest("created_at")
        self.assertEqual(log.report_key, "financial_summary")
        self.assertEqual(log.action, ReportAccessAuditLog.ACTION_RUN)

    def test_member_without_view_reports_denied_index(self):
        # MEMBER is outside report catalog defaults; finance implies do not grant it.
        user = User.objects.create_user(
            username="no_reports",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.assertFalse(user_may_access_report(user, "financial_summary", active_church=self.church))
