"""Tests for dashboard services and views."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from dashboard.models import Notification
from dashboard.metrics import pct_change
from dashboard.services import (
    filter_action_queue_for_control_center,
    get_action_queue,
    get_alerts,
    get_dashboard_role,
    get_executive_kpis,
    get_financial_summary,
    get_hierarchy_rollup,
    get_quick_actions,
    get_role_focus,
    notify_user,
)
from dashboard.utils import safe_internal_redirect
from organization.models import Church, Conference, District, Zone
from sitecontrol.denomination_services import ensure_builtin_denominations
from sitecontrol.models import Denomination
from transactions.models import MonthlyCutoff
from transactions.services import approve_transaction, open_working_day, record_receipt

User = get_user_model()


class DashboardTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="T1", name="Test Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z1", name="Test Zone")
        cls.district = District.objects.create(zone=cls.zone, code="D1", name="Test District")
        cls.church = Church.objects.create(district=cls.district, code="C1", name="Test Church")


class SafeRedirectTests(TestCase):
    def test_allows_relative_path(self):
        self.assertEqual(safe_internal_redirect("/members/", "/"), "/members/")

    def test_blocks_open_redirect(self):
        self.assertEqual(safe_internal_redirect("https://evil.example/", "/safe/"), "/safe/")
        self.assertEqual(safe_internal_redirect("//evil.example/", "/safe/"), "/safe/")
        self.assertEqual(safe_internal_redirect("", "/safe/"), "/safe/")


class ServiceTests(DashboardTestMixin, TestCase):
    def test_notify_user_creates_notification(self):
        user = User.objects.create_user(
            username="u1", password="pass12345", role=UserRole.MEMBER, church=self.church
        )
        n = notify_user(user, "Test", "Hello world", category="INFO")
        self.assertIsNotNone(n)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_dashboard_role_treasury(self):
        user = User.objects.create_user(
            username="t1", password="pass12345", role=UserRole.TREASURY, church=self.church
        )
        self.assertEqual(get_dashboard_role(user), "treasury")

    def test_dashboard_role_secretary(self):
        user = User.objects.create_user(
            username="s1", password="pass12345", role=UserRole.SECRETARY, church=self.church
        )
        self.assertEqual(get_dashboard_role(user), "secretary")

    def test_secretary_role_even_with_manage_finances(self):
        """SECRETARY identity wins over manage_finances permission."""
        user = User.objects.create_user(
            username="s_fin", password="pass12345", role=UserRole.SECRETARY, church=self.church
        )
        self.assertEqual(get_dashboard_role(user), "secretary")
        self.assertNotEqual(get_dashboard_role(user), "finance")

    def test_local_pastor_is_leadership(self):
        user = User.objects.create_user(
            username="pastor1", password="pass12345", role=UserRole.LOCAL_PASTOR, church=self.church
        )
        self.assertEqual(get_dashboard_role(user), "leadership")

    def test_district_pastor_is_district_overseer(self):
        user = User.objects.create_user(
            username="dp1", password="pass12345", role=UserRole.DISTRICT_PASTOR, church=self.church
        )
        self.assertEqual(get_dashboard_role(user), "district_overseer")
        focus = get_role_focus("district_overseer")
        self.assertIn("District", focus["headline"])

    def test_monthly_cutoff_total_uses_payable_types(self):
        treasury = User.objects.create_user(
            username="t_kpi", password="pass12345", role=UserRole.TREASURY, church=self.church
        )
        pastor = User.objects.create_user(
            username="p_kpi", password="pass12345", role=UserRole.LOCAL_PASTOR, church=self.church
        )
        open_working_day(self.church, timezone.localdate(), pastor)
        txn = record_receipt(
            church=self.church,
            created_by=treasury,
            tithe_amount=Decimal("100.00"),
            combined_amount=Decimal("50.00"),
            income_amount=Decimal("10.00"),
        )
        approve_transaction(txn, pastor)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = treasury
        request.session = {"current_church_id": str(self.church.id)}

        # Avoid creating MonthlyCutoff so KPI computes from payable lines
        MonthlyCutoff.objects.filter(church=self.church).delete()
        summary = get_financial_summary(request)
        # Tithe remittance payable 100 + combined remittance payable 25 (50% of 50)
        self.assertEqual(summary["monthly_cutoff_total"], Decimal("125.00"))
        self.assertEqual(summary["tithe_total"], Decimal("100.00"))
        self.assertEqual(summary["combined_total"], Decimal("50.00"))
        self.assertEqual(summary["kpi_period_label"], "Month to date")
        self.assertEqual(summary["cutoff_metric_label"], "Remittance payable (MTD)")

        kpis = get_executive_kpis(
            request,
            treasury,
            church_ids=[self.church.id],
            active_church=self.church,
        )
        self.assertEqual(kpis["mtd_remittance_payable"], summary["monthly_cutoff_total"])
        self.assertEqual(kpis["mtd_tithe"], summary["tithe_total"])
        self.assertEqual(kpis["mtd_combined"], summary["combined_total"])

    def test_quick_actions_capped_and_no_duplicate_org(self):
        admin = User.objects.create_user(
            username="dashadmin",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        actions = get_quick_actions(admin)
        labels = [a["label"] for a in actions]
        self.assertLessEqual(len(actions), 6)
        self.assertEqual(labels.count("Organization"), 1)
        self.assertNotIn("Churches", labels)
        self.assertNotIn("Upcoming", labels)

    def test_alerts_use_currency_symbol(self):
        from unittest.mock import MagicMock, patch

        treasury = User.objects.create_user(
            username="alerttreasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = treasury
        request.session = {}
        overdue = MagicMock()
        overdue.total_payable = Decimal("1250.50")
        with patch("dashboard.services.get_active_church", return_value=self.church), patch(
            "dashboard.selectors.overdue_cutoff_for_church", return_value=overdue
        ), patch(
            "transactions.services.get_working_day_status",
            return_value={"is_open": True},
        ), patch(
            "dashboard.selectors.locked_period_exists", return_value=False
        ), patch(
            "church_system.currency.currency_symbol", return_value="GHS "
        ):
            alerts = get_alerts(request, treasury)
        remittance = [a for a in alerts if "Remittance overdue" in a["text"]]
        self.assertTrue(remittance)
        self.assertIn("GHS ", remittance[0]["text"])
        self.assertNotIn("₵", remittance[0]["text"])


class HierarchyScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_denominations()
        cls.sda = Denomination.objects.get(code="sda")
        cls.methodist = Denomination.objects.get(code="methodist")

        conf_sda = Conference.objects.create(name="SDA Dash Conf", code="SDADC", denomination=cls.sda)
        conf_meth = Conference.objects.create(name="Meth Dash Conf", code="METHDC", denomination=cls.methodist)
        z_sda = Zone.objects.create(conference=conf_sda, name="ZS", code="ZS")
        z_meth = Zone.objects.create(conference=conf_meth, name="ZM", code="ZM")
        d_sda = District.objects.create(zone=z_sda, name="District SDA", code="DS")
        d_meth = District.objects.create(zone=z_meth, name="District Meth", code="DM")
        cls.church_sda = Church.objects.create(district=d_sda, name="SDA Dash Church", code="SDC")
        cls.church_meth = Church.objects.create(district=d_meth, name="Meth Dash Church", code="MDC")

    def test_hierarchy_rollup_only_manageable_churches(self):
        go = User.objects.create_user(
            username="go_sda",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
            denomination=self.sda,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = go
        rows = get_hierarchy_rollup(request, go)
        names = {r["district"] for r in rows}
        self.assertIn("District SDA", names)
        self.assertNotIn("District Meth", names)
        self.assertTrue(all("remittance_payable" in r for r in rows))


class NavigationDensityTests(DashboardTestMixin, TestCase):
    def test_home_module_has_no_sticky_tabs(self):
        from church_system.navigation import get_module_tabs

        treasury = User.objects.create_user(
            username="hometabs",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        key, tabs = get_module_tabs(treasury, "dashboard", "dashboard:home", active_church=self.church)
        self.assertIsNone(key)
        self.assertIsNone(tabs)

    def test_finance_tabs_pruned_for_treasury(self):
        from church_system.navigation import get_module_tabs

        treasury = User.objects.create_user(
            username="tabtreasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        key, tabs = get_module_tabs(treasury, "ledger", "ledger:entry", active_church=self.church)
        self.assertEqual(key, "finance")
        names = {t["url_name"] for t in tabs}
        self.assertIn("ledger:entry", names)
        self.assertIn("transactions:transaction_list", names)
        self.assertNotIn("ledger:accounts", names)
        self.assertNotIn("ledger:categories", names)

    def test_page_eyebrow_for_finance_pending(self):
        from church_system.navigation import get_module_tabs, get_page_eyebrow

        treasury = User.objects.create_user(
            username="eyebrowtreasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        key, tabs = get_module_tabs(
            treasury, "transactions", "transactions:pending_approvals", active_church=self.church
        )
        eyebrow = get_page_eyebrow(key, tabs, "transactions:pending_approvals")
        self.assertEqual(eyebrow["section"], "Finance")
        self.assertEqual(eyebrow["page"], "Pending")


class ViewTests(DashboardTestMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        from sitecontrol.models import SiteSettings

        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        self.client = Client()
        self.treasury = User.objects.create_user(
            username="treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        enable_mfa_for_user(self.treasury, generate_totp_secret(), [])
        self._mfa_key = SESSION_MFA_VERIFIED

    def _login(self, username):
        from accounts.mfa import enable_mfa_for_user, generate_totp_secret

        user = User.objects.get(username=username)
        if not getattr(user, "mfa_enabled", False):
            try:
                enable_mfa_for_user(user, generate_totp_secret(), [])
            except Exception:
                pass
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[self._mfa_key] = True
        session.save()

    def test_home_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)

    def test_home_renders_for_treasury(self):
        self._login("treasury")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Good day")
        self.assertFalse(response.context["suppress_workspace_cash"])
        self.assertLessEqual(len(response.context["quick_actions"]), 3)
        self.assertEqual(response.context["quick_actions_more"], [])

    def test_home_renders_alerts_banner(self):
        from unittest.mock import patch

        self._login("treasury")
        fake_alerts = [
            {"level": "warning", "text": "2 transaction(s) awaiting approval.", "url_name": "transactions:pending_approvals"},
            {"level": "danger", "text": "Remittance overdue.", "url_name": "dashboard:cutoff"},
            {"level": "info", "text": "Period locked.", "url_name": "transactions:period_list"},
            {"level": "secondary", "text": "Extra alert.", "url_name": "dashboard:home"},
        ]
        with patch("dashboard.services.get_alerts", return_value=fake_alerts):
            response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "awaiting approval")
        self.assertContains(response, "+1 more")

    def test_notification_inbox(self):
        notify_user(self.treasury, "Alert", "Test message")
        self._login("treasury")
        response = self.client.get(reverse("dashboard:notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test message")

    def test_mark_all_read(self):
        notify_user(self.treasury, "A", "One")
        notify_user(self.treasury, "B", "Two")
        self._login("treasury")
        response = self.client.post(reverse("dashboard:notification_mark_all_read"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(user=self.treasury, read=False).count(), 0
        )

    def test_notification_count_api(self):
        notify_user(self.treasury, "A", "One")
        self._login("treasury")
        response = self.client.get(reverse("dashboard:notification_count"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_cutoff_page(self):
        self._login("treasury")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = self.client.get(reverse("dashboard:cutoff"))
        self.assertEqual(response.status_code, 200)

    def test_cutoff_get_does_not_create_monthly_cutoff(self):
        self._login("treasury")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        before = MonthlyCutoff.objects.filter(church=self.church).count()
        response = self.client.get(reverse("dashboard:cutoff"))
        self.assertEqual(response.status_code, 200)
        after = MonthlyCutoff.objects.filter(church=self.church).count()
        self.assertEqual(before, after)

    def test_cutoff_without_finance_forbidden(self):
        member = User.objects.create_user(
            username="member_no_fin",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self._login("member_no_fin")
        response = self.client.get(reverse("dashboard:cutoff"))
        self.assertEqual(response.status_code, 403)

    def test_switcher_clears_session_with_empty_church(self):
        self._login("treasury")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = self.client.get(reverse("dashboard:switch_church") + "?church=")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("current_church_id", self.client.session)

    def test_home_clears_church_with_all(self):
        self._login("treasury")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = self.client.get(reverse("dashboard:home") + "?church=all", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("current_church_id", self.client.session)

    def test_open_redirect_blocked_on_notification_follow(self):
        n = notify_user(
            self.treasury,
            "Phish",
            "Click me",
            action_url="https://evil.example/steal",
        )
        self._login("treasury")
        response = self.client.post(
            reverse("dashboard:notification_mark_read", kwargs={"pk": n.pk}),
            {"follow": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response.url)
        self.assertTrue(
            response.url.endswith(reverse("dashboard:notifications"))
            or response.url == reverse("dashboard:notifications")
        )

    def test_notification_follow_allows_internal_path(self):
        n = notify_user(
            self.treasury,
            "Go",
            "Internal",
            action_url="/dashboard/notifications/",
        )
        self._login("treasury")
        response = self.client.post(
            reverse("dashboard:notification_mark_read", kwargs={"pk": n.pk}),
            {"follow": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/notifications/")

    def test_home_shows_hierarchy_rollup_for_overseer(self):
        overseer = User.objects.create_user(
            username="overseer",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
        )
        self._login("overseer")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "District Roll-up")
        self.assertContains(response, "Mission Control")
        self.assertContains(response, "Action queue")

    def test_executive_kpis_for_overseer(self):
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination

        ensure_builtin_denominations()
        sda = Denomination.objects.get(code="sda")
        self.conference.denomination = sda
        self.conference.save(update_fields=["denomination"])
        overseer = User.objects.create_user(
            username="go_kpi",
            password="pass12345",
            role=UserRole.GENERAL_OVERSEER,
            denomination=sda,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = overseer
        request.session = {}
        kpis = get_executive_kpis(request, overseer)
        self.assertIsNotNone(kpis)
        self.assertGreaterEqual(kpis["church_count"], 1)

    def test_action_queue_structure(self):
        treasury = User.objects.create_user(
            username="t_queue",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = treasury
        request.session = {"current_church_id": str(self.church.id)}
        queue = get_action_queue(request, treasury)
        self.assertIsInstance(queue, list)

    def test_pct_change_handles_zero_prior(self):
        self.assertIsNone(pct_change(Decimal("0"), Decimal("0")))
        self.assertEqual(pct_change(Decimal("10"), Decimal("0")), 100.0)

    def test_control_center_filters_duplicate_queue_items(self):
        raw = [
            {"kind": "transaction_approvals", "title": "Transaction approvals"},
            {"kind": "announcement_approvals", "title": "Announcement approvals"},
            {"kind": "overdue_remittances", "title": "Overdue remittances"},
        ]
        filtered = filter_action_queue_for_control_center(raw)
        kinds = {item["kind"] for item in filtered}
        self.assertEqual(kinds, {"announcement_approvals"})

    def test_home_shows_secretary_meetings_panel(self):
        secretary = User.objects.create_user(
            username="secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self._login("secretary")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming Meetings")

    def test_home_200_for_overseer_and_secretary(self):
        overseer = User.objects.create_user(
            username="ov2", password="pass12345", role=UserRole.GENERAL_OVERSEER
        )
        secretary = User.objects.create_user(
            username="sec2", password="pass12345", role=UserRole.SECRETARY, church=self.church
        )
        for username in ("treasury", "ov2", "sec2"):
            self._login(username)
            response = self.client.get(reverse("dashboard:home"))
            self.assertEqual(response.status_code, 200, username)


class HealthCheckTests(TestCase):
    def test_health_includes_database_ok(self):
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["checks"]["database"], "ok")


class PurgeNotificationsCommandTests(DashboardTestMixin, TestCase):
    def test_purge_old_notifications(self):
        from django.core.management import call_command

        user = User.objects.create_user(
            username="purge_u", password="pass12345", role=UserRole.MEMBER, church=self.church
        )
        old_read = notify_user(user, "Old", "read")
        old_read.read = True
        old_read.save(update_fields=["read"])
        Notification.objects.filter(pk=old_read.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )
        fresh = notify_user(user, "Fresh", "keep")
        call_command("purge_old_notifications")
        self.assertFalse(Notification.objects.filter(pk=old_read.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=fresh.pk).exists())


class ThisWeekPulseTests(DashboardTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        super().setUpTestData()
        from members.models import Visitor, VisitorFollowUpStatus

        cls.secretary = User.objects.create_user(
            username="pulse_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.treasury = User.objects.create_user(
            username="pulse_treas",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        Visitor.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Visitor",
            visit_date=timezone.localdate() - timedelta(days=2),
            follow_up_status=VisitorFollowUpStatus.NEW,
        )

    def setUp(self):
        from accounts.mfa import SESSION_MFA_VERIFIED

        self.client = Client()
        self._mfa_key = SESSION_MFA_VERIFIED

    def _login(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[self._mfa_key] = True
        session["current_church_id"] = str(self.church.id)
        session.save()

    def test_secretary_home_shows_this_week_pulse(self):
        self._login("pulse_sec")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_this_week_pulse"])
        self.assertIsNotNone(response.context["this_week_pulse"])
        self.assertContains(response, "This week")
        self.assertContains(response, "Visitors")
        self.assertGreaterEqual(response.context["this_week_pulse"]["counts"]["visitors"], 1)

    def test_treasury_without_member_focus_hides_pulse(self):
        self._login("pulse_treas")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        # Treasury layout does not enable the pastoral pulse panel.
        self.assertFalse(response.context.get("show_this_week_pulse"))


class DashboardScopeAndWidgetTests(DashboardTestMixin, TestCase):
    def test_resolve_scope_focuses_active_church_finance(self):
        from dashboard.scope import resolve_dashboard_scope

        user = User.objects.create_user(
            username="scope_u",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.session = {"current_church_id": str(self.church.id)}

        scope = resolve_dashboard_scope(request)
        self.assertEqual(scope.level, "CHURCH")
        self.assertEqual(scope.finance_church_ids, (self.church.pk,))

    def test_build_kpi_widgets_orders_pastoral_profile(self):
        from dashboard.scope import DashboardScope
        from dashboard.widgets import build_kpi_widgets

        scope = DashboardScope(
            level="CHURCH",
            church_ids=(self.church.pk,),
            primary_church=self.church,
            label=self.church.name,
            finance_church_ids=(self.church.pk,),
            finance_scope_label=self.church.name,
        )
        user = User.objects.create_user(
            username="pastor_widgets",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        widgets = build_kpi_widgets(
            user=user,
            dashboard_role="leadership",
            scope=scope,
            finance_bundle={"member_count": 3},
            pending_transfers=1,
            is_control_center=False,
        )
        ids = [w["id"] for w in widgets]
        self.assertIn("active_members", ids)
        self.assertIn("pending_transfers", ids)
        self.assertLess(ids.index("pending_transfers"), ids.index("active_members"))

    def test_pastor_home_renders_unified_kpi_strip(self):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        User.objects.create_user(
            username="pastor_home",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        client = Client()
        client.login(username="pastor_home", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church.id)
        from accounts.mfa import SESSION_MFA_VERIFIED

        session[SESSION_MFA_VERIFIED] = True
        session.save()

        response = client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        widgets = response.context.get("dashboard_kpi_widgets") or []
        self.assertTrue(widgets)
        self.assertContains(response, "Active Members")
        self.assertTrue(response.context.get("show_finance_charts"))
