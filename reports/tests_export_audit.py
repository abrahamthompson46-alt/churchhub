"""Regression: domain CSV/Excel/PDF exports write ReportAccessAuditLog."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from reports.models import ReportAccessAuditLog
from reports.services import audit_export
from sitecontrol.models import SiteSettings

User = get_user_model()


class AuditExportHelperTests(TestCase):
    def test_audit_export_writes_report_access_log(self):
        user = User.objects.create_user(username="audit_exp", password="pass12345")
        before = ReportAccessAuditLog.objects.count()
        audit_export(
            user=user,
            report_key="giving_statement",
            export_format="csv",
            row_count=3,
            params={"year": 2024},
        )
        self.assertEqual(ReportAccessAuditLog.objects.count(), before + 1)
        log = ReportAccessAuditLog.objects.latest("created_at")
        self.assertEqual(log.report_key, "giving_statement")
        self.assertEqual(log.action, ReportAccessAuditLog.ACTION_EXPORT)
        self.assertEqual(log.export_format, "csv")
        self.assertEqual(log.row_count, 3)
        self.assertEqual(log.user_id, user.pk)


class DomainExportAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(name="Exp Conf", code="EXPC")
        zone = Zone.objects.create(conference=conf, name="Exp Zone", code="EXPZ")
        dist = District.objects.create(zone=zone, name="Exp Dist", code="EXPD")
        cls.church = Church.objects.create(district=dist, name="Exp Church", code="EXPCH")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Export",
            last_name="Member",
            gender="Male",
        )
        cls.treasury = User.objects.create_user(
            username="exp_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.secretary = User.objects.create_user(
            username="exp_secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.admin = User.objects.create_user(
            username="exp_admin",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=cls.church,
            is_superuser=True,
        )

    def setUp(self):
        self.client = Client()

    def _assert_export_logged(self, report_key, export_format="csv"):
        log = (
            ReportAccessAuditLog.objects.filter(
                report_key=report_key,
                action=ReportAccessAuditLog.ACTION_EXPORT,
                export_format=export_format,
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(log, f"Expected ReportAccessAuditLog for {report_key}")
        return log

    def test_giving_statement_export_audited(self):
        self.client.login(username="exp_treasury", password="pass12345")
        response = self.client.get(
            reverse("giving:member_statement", args=[self.member.pk]),
            {"export": "csv", "year": 2024},
        )
        self.assertEqual(response.status_code, 200)
        log = self._assert_export_logged("giving_statement")
        self.assertEqual(log.church_id, self.church.pk)

    def test_transaction_list_export_audited(self):
        self.client.login(username="exp_treasury", password="pass12345")
        response = self.client.get(
            reverse("transactions:transaction_list"),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self._assert_export_logged("transactions_list")

    def test_ledger_entries_export_audited(self):
        self.client.login(username="exp_treasury", password="pass12345")
        response = self.client.get(reverse("ledger:entries"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self._assert_export_logged("ledger_entries")

    def test_organization_hierarchy_export_audited(self):
        self.client.login(username="exp_admin", password="pass12345")
        response = self.client.get(
            reverse("organization:hierarchy"),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self._assert_export_logged("organization_hierarchy")

    def test_member_directory_export_audited(self):
        self.client.login(username="exp_secretary", password="pass12345")
        response = self.client.get(
            reverse("members:list"),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self._assert_export_logged("member_directory")
