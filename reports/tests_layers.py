"""Characterization tests for reports selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase

from accounts.models import UserRole
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from reports import repositories as repo
from reports import selectors
from reports.models import ReportAccessAuditLog, ReportExportJob
from reports.services import (
    _churches_in_scope,
    audit_export,
    build_report,
    user_may_access_report,
)
from sitecontrol.models import SiteSettings

User = get_user_model()


class ReportsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(code="RL1", name="Layer Conf")
        zone = Zone.objects.create(conference=conf, code="RL1", name="Layer Zone")
        dist = District.objects.create(zone=zone, code="RL1", name="Layer Dist")
        cls.church = Church.objects.create(district=dist, code="RL1", name="Layer Church")
        conf2 = Conference.objects.create(code="RL2", name="Other Layer Conf")
        zone2 = Zone.objects.create(conference=conf2, code="RL2", name="Other Layer Zone")
        dist2 = District.objects.create(zone=zone2, code="RL2", name="Other Layer Dist")
        cls.other_church = Church.objects.create(
            district=dist2, code="RL2", name="Other Layer Church"
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.treasury = User.objects.create_user(
            username="rpt_layer_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.member_user = User.objects.create_user(
            username="rpt_layer_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )

    def _request(self, user=None):
        request = self.factory.get("/")
        request.user = user or self.treasury
        request.session = {}
        return request

    def test_selector_churches_in_scope_defaults_to_active_church(self):
        request = self._request()
        qs = selectors.churches_in_scope(request)
        self.assertIn(self.church, qs)
        self.assertNotIn(self.other_church, qs)

    def test_selector_forged_church_id_empty(self):
        request = self._request()
        qs = selectors.churches_in_scope(request, church_id=self.other_church.pk)
        self.assertFalse(qs.exists())

    def test_service_churches_in_scope_matches_selector(self):
        request = self._request()
        self.assertEqual(
            list(_churches_in_scope(request).values_list("pk", flat=True)),
            list(selectors.churches_in_scope(request).values_list("pk", flat=True)),
        )

    def test_financial_summary_via_selectors_path(self):
        data = build_report("financial_summary", self._request(), period="monthly")
        self.assertEqual(data["title"], "Financial Summary")
        self.assertIn("rows", data)

    def test_unauthorized_user_cannot_access_finance_report(self):
        self.assertFalse(
            user_may_access_report(self.member_user, "financial_summary", self.church)
        )

    def test_audit_export_via_repository(self):
        before = ReportAccessAuditLog.objects.count()
        audit_export(
            user=self.treasury,
            report_key="financial_summary",
            export_format="csv",
            row_count=2,
            church=self.church,
        )
        self.assertEqual(ReportAccessAuditLog.objects.count(), before + 1)
        log = ReportAccessAuditLog.objects.latest("created_at")
        self.assertEqual(log.action, ReportAccessAuditLog.ACTION_EXPORT)
        self.assertEqual(log.export_format, "csv")

    def test_repository_create_export_job(self):
        job = repo.create_export_job(
            user=self.treasury,
            report_key="financial_summary",
            export_format="csv",
            params={"period": "monthly"},
        )
        self.assertEqual(job.status, ReportExportJob.STATUS_PENDING)
        self.assertEqual(job.user_id, self.treasury.pk)

    def test_export_job_for_user_scopes_owner(self):
        job = repo.create_export_job(
            user=self.treasury,
            report_key="tithe_report",
            export_format="excel",
        )
        found = selectors.export_job_for_user(self.treasury, job.pk)
        self.assertEqual(found.pk, job.pk)
        with self.assertRaises(Http404):
            selectors.export_job_for_user(self.member_user, job.pk)
