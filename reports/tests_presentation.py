"""Statement presentation and export helpers."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from reports.exporters import export_statement_pdf
from reports.presentation import normalize_kpi_tone
from reports.services import build_report

User = get_user_model()


class ReportPresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Pres Conf", code="PRC")
        zone = Zone.objects.create(name="Pres Z", code="PRZ", conference=conf)
        district = District.objects.create(name="Pres D", code="PRD", zone=zone)
        cls.church = Church.objects.create(name="Pres Church", code="PRCH", district=district)
        cls.treasury = User.objects.create_user(
            username="pres_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def test_normalize_kpi_tone_maps_ok(self):
        self.assertEqual(normalize_kpi_tone("ok"), "success")

    def test_income_statement_has_footer_totals(self):
        request = RequestFactory().get("/")
        request.user = self.treasury
        data = build_report("income_statement", request, period="monthly")
        footer = data["statement"].get("footer_totals") or []
        labels = [row["label"] for row in footer]
        self.assertIn("Net surplus / (deficit)", labels)

    def test_statement_pdf_response(self):
        request = RequestFactory().get("/")
        request.user = self.treasury
        data = build_report("financial_summary", request, period="monthly")
        response = export_statement_pdf(data, filename="summary.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))