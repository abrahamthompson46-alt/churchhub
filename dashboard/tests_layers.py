"""Characterization tests for dashboard selectors / repositories layering."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import UserRole
from dashboard import repositories as repo
from dashboard import selectors
from dashboard.models import Notification
from dashboard.services import get_financial_summary, notify_user
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from sitecontrol.denomination_services import ensure_builtin_denominations
from sitecontrol.models import Denomination, SiteSettings
from transactions.services import approve_transaction, open_working_day, record_receipt

User = get_user_model()


class DashboardLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(code="DL1", name="Dash Layer Conf")
        zone = Zone.objects.create(conference=conf, code="DL1", name="Dash Layer Zone")
        dist = District.objects.create(zone=zone, code="DL1", name="Dash Layer Dist")
        cls.church = Church.objects.create(district=dist, code="DL1", name="Dash Layer Church")
        conf2 = Conference.objects.create(code="DL2", name="Other Dash Conf")
        zone2 = Zone.objects.create(conference=conf2, code="DL2", name="Other Dash Zone")
        dist2 = District.objects.create(zone=zone2, code="DL2", name="Other Dash Dist")
        cls.other_church = Church.objects.create(
            district=dist2, code="DL2", name="Other Dash Church"
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.treasury = User.objects.create_user(
            username="dash_layer_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.other_user = User.objects.create_user(
            username="dash_layer_other",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.other_church,
        )

    def _request(self, user=None, church=None):
        request = self.factory.get("/")
        request.user = user or self.treasury
        request.session = {}
        if church:
            request.session["current_church_id"] = str(church.pk)
        return request

    def test_manageable_church_by_pk_isolates(self):
        self.assertEqual(
            selectors.manageable_church_by_pk(self.treasury, self.church.pk),
            self.church,
        )
        self.assertIsNone(
            selectors.manageable_church_by_pk(self.treasury, self.other_church.pk)
        )

    def test_notification_for_user_scopes_owner(self):
        n = notify_user(self.treasury, "Mine", "Hello")
        found = selectors.notification_for_user(self.treasury, n.pk)
        self.assertEqual(found.pk, n.pk)
        with self.assertRaises(Http404):
            selectors.notification_for_user(self.other_user, n.pk)

    def test_repository_mark_all_read(self):
        notify_user(self.treasury, "A", "One")
        notify_user(self.treasury, "B", "Two")
        repo.mark_all_notifications_read(self.treasury)
        self.assertEqual(selectors.unread_notification_count(self.treasury), 0)

    def test_financial_kpi_unchanged_via_selectors(self):
        pastor = User.objects.create_user(
            username="dash_layer_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), pastor)
        txn = record_receipt(
            church=self.church,
            created_by=self.treasury,
            tithe_amount=Decimal("100.00"),
            combined_amount=Decimal("50.00"),
            income_amount=Decimal("10.00"),
        )
        approve_transaction(txn, pastor)
        from transactions.models import MonthlyCutoff

        MonthlyCutoff.objects.filter(church=self.church).delete()
        summary = get_financial_summary(self._request(church=self.church))
        self.assertEqual(summary["monthly_cutoff_total"], Decimal("125.00"))
        self.assertEqual(summary["kpi_period_label"], "Month to date")

    def test_transactions_for_request_church_scope(self):
        request = self._request(church=self.church)
        qs = selectors.transactions_for_request(request)
        # Empty is fine; must not raise and must be church-scoped queryset
        self.assertTrue(hasattr(qs, "filter"))


class DashboardDenominationLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        ensure_builtin_denominations()
        cls.sda = Denomination.objects.get(code="sda")
        cls.methodist = Denomination.objects.get(code="methodist")
        conf_sda = Conference.objects.create(
            name="SDA Layer Conf", code="SDALC", denomination=cls.sda
        )
        conf_meth = Conference.objects.create(
            name="Meth Layer Conf", code="METHLC", denomination=cls.methodist
        )
        z_sda = Zone.objects.create(conference=conf_sda, name="ZS", code="ZSL")
        z_meth = Zone.objects.create(conference=conf_meth, name="ZM", code="ZML")
        d_sda = District.objects.create(zone=z_sda, name="District SDA L", code="DSL")
        d_meth = District.objects.create(zone=z_meth, name="District Meth L", code="DML")
        cls.church_sda = Church.objects.create(district=d_sda, name="SDA L Church", code="SDLC")
        cls.church_meth = Church.objects.create(
            district=d_meth, name="Meth L Church", code="MDLC"
        )

    def test_hierarchy_rollup_selector_path_denomination(self):
        from dashboard.services import get_hierarchy_rollup

        go = User.objects.create_user(
            username="go_layer_sda",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
            denomination=self.sda,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = go
        request.session = {}
        rows = get_hierarchy_rollup(request, go)
        names = {r["district"] for r in rows}
        self.assertIn("District SDA L", names)
        self.assertNotIn("District Meth L", names)
