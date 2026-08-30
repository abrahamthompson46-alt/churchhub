"""Public 30-day demo: auto-provision, identity lock, hard expiry cutoff."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings, TenantApplication, TenantSubscription
from sitecontrol.registration_services import (
    DEMO_IDENTITY_ERROR,
    PUBLIC_DEMO_TRIAL_DAYS_CAP,
    submit_tenant_application,
)
from sitecontrol.services import (
    assign_subscription,
    clear_settings_cache,
    ensure_default_plans,
    get_default_plan,
)
from sitecontrol.test_support import SiteControlClientHarness

User = get_user_model()

DEMO_PASSWORD = "Tr1alLocked!"


class PublicDemoTrialTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination

        ensure_builtin_denominations()
        self.denomination = Denomination.objects.get(code="demo")
        conf = Conference.objects.create(
            name="DemoConf", code="DC1", denomination=self.denomination
        )
        zone = Zone.objects.create(name="DemoZone", code="DZ1", conference=conf)
        self.district = District.objects.create(name="DemoDist", code="DD1", zone=zone)
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = True
        settings_obj.auto_provision_public_trials = True
        settings_obj.public_demo_trial_days = 30
        settings_obj.mfa_required_for_privileged = False
        settings_obj.save()
        clear_settings_cache()

    def _payload(self, **overrides):
        data = {
            "application_type": "EXISTING_DISTRICT",
            "denomination": self.denomination,
            "church_name": "Demo Chapel",
            "church_code": "DM01",
            "district": self.district,
            "contact_name": "Pastor Ada",
            "contact_email": "ada@demo.test",
            "contact_phone": "+233 24 111 2222",
            "applicant_username": "pastorada",
            "password": DEMO_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_auto_provision_creates_trial_user_and_freezes_30_days(self):
        plan = get_default_plan()
        plan.trial_days = 90
        plan.save(update_fields=["trial_days"])

        app = submit_tenant_application(self._payload())
        self.assertEqual(app.status, "APPROVED")
        self.assertIsNone(app.invitation_id)
        church = app.created_church
        self.assertEqual(church.name, "Demo Chapel")
        sub = TenantSubscription.objects.get(church=church)
        self.assertEqual(sub.status, "TRIAL")
        self.assertEqual(sub.started_at, timezone.now().date())
        self.assertEqual(
            sub.expires_at,
            sub.started_at + timedelta(days=PUBLIC_DEMO_TRIAL_DAYS_CAP),
        )
        self.assertTrue(sub.is_operational)
        user = User.objects.get(username="pastorada")
        self.assertEqual(user.role, UserRole.LOCAL_PASTOR)
        self.assertEqual(user.church_id, church.pk)
        self.assertEqual(church.denomination.code, "demo")
        self.assertTrue(user.check_password(DEMO_PASSWORD))
        self.assertLessEqual((sub.expires_at - sub.started_at).days, 30)

    def test_posted_foreign_denomination_is_ignored(self):
        from sitecontrol.models import Denomination

        sda = Denomination.objects.get(code="sda")
        app = submit_tenant_application(self._payload(denomination=sda))
        self.assertEqual(app.denomination.code, "demo")
        self.assertEqual(app.created_church.denomination.code, "demo")

    def test_plan_trial_days_cannot_stretch_public_demo(self):
        plan = get_default_plan()
        plan.trial_days = 14
        plan.save(update_fields=["trial_days"])
        app = submit_tenant_application(self._payload())
        sub = TenantSubscription.objects.get(church=app.created_church)
        self.assertEqual((sub.expires_at - sub.started_at).days, 30)

    def test_identity_lock_blocks_email_username_and_phone(self):
        submit_tenant_application(self._payload())
        with self.assertRaisesMessage(ValueError, DEMO_IDENTITY_ERROR):
            submit_tenant_application(
                self._payload(
                    church_code="DM02",
                    applicant_username="otheruser",
                    contact_phone="+233 20 000 0000",
                )
            )
        with self.assertRaisesMessage(ValueError, DEMO_IDENTITY_ERROR):
            submit_tenant_application(
                self._payload(
                    church_code="DM03",
                    contact_email="other@demo.test",
                    contact_phone="+233 20 000 0001",
                )
            )
        with self.assertRaisesMessage(ValueError, DEMO_IDENTITY_ERROR):
            submit_tenant_application(
                self._payload(
                    church_code="DM04",
                    contact_email="third@demo.test",
                    applicant_username="thirduser",
                    contact_phone="233241112222",
                )
            )

    def test_changing_trial_days_setting_does_not_extend_existing_demo(self):
        app = submit_tenant_application(self._payload())
        sub = TenantSubscription.objects.get(church=app.created_church)
        original = sub.expires_at
        settings_obj = SiteSettings.load()
        settings_obj.public_demo_trial_days = 30
        settings_obj.save(update_fields=["public_demo_trial_days"])
        plan = sub.plan
        plan.trial_days = 90
        plan.save(update_fields=["trial_days"])
        sub.refresh_from_db()
        self.assertEqual(sub.expires_at, original)

    def test_trial_without_expiry_is_not_operational(self):
        church = Church.objects.create(
            name="No Expiry", code="NX1", district=self.district
        )
        assign_subscription(
            church, get_default_plan(), status="TRIAL", expires_at=None
        )
        sub = TenantSubscription.objects.get(church=church)
        self.assertFalse(sub.is_operational)

    def test_hard_cutoff_on_expiry_date_without_expire_job(self):
        app = submit_tenant_application(self._payload())
        sub = TenantSubscription.objects.get(church=app.created_church)
        user = User.objects.get(username="pastorada")
        sub.expires_at = timezone.now().date()
        sub.save(update_fields=["expires_at"])
        self.assertEqual(sub.status, "TRIAL")
        self.assertFalse(sub.is_operational)

        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("subscription_expired"))

        members = self.client.get("/members/", follow=False)
        self.assertEqual(members.status_code, 302)
        self.assertEqual(members.url, reverse("subscription_expired"))

        expired = self.client.get(reverse("subscription_expired"))
        self.assertEqual(expired.status_code, 200)
        self.assertContains(expired, "Your access has ended")

        logout = self.client.post(reverse("logout"))
        self.assertIn(logout.status_code, (200, 302))

    def test_active_demo_can_open_dashboard(self):
        submit_tenant_application(self._payload())
        self.assertTrue(self.client.login(username="pastorada", password=DEMO_PASSWORD))
        response = self.client.get(reverse("dashboard:home"))
        if response.status_code == 302:
            self.assertNotIn("subscription-expired", response.url)
        else:
            self.assertEqual(response.status_code, 200)

    def test_apply_view_logs_in_and_does_not_queue(self):
        response = self.client.post(
            reverse("church_apply"),
            {
                "denomination": str(self.denomination.pk),
                "application_type": "EXISTING_DISTRICT",
                "church_name": "View Demo",
                "church_code": "VW01",
                "district": str(self.district.pk),
                "contact_name": "View Pastor",
                "contact_email": "view@demo.test",
                "contact_phone": "0243334444",
                "applicant_username": "viewpastor",
                "password": DEMO_PASSWORD,
                "password_confirm": DEMO_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))
        self.assertEqual(TenantApplication.objects.filter(status="PENDING").count(), 0)
        self.assertTrue(User.objects.filter(username="viewpastor").exists())

    def test_public_demo_ignores_district_branch_limit(self):
        plan = get_default_plan()
        plan.max_branches = 1
        plan.save(update_fields=["max_branches"])
        existing = Church.objects.create(
            name="Already There", code="AT1", district=self.district
        )
        assign_subscription(existing, plan, status="ACTIVE")
        app = submit_tenant_application(self._payload())
        self.assertEqual(app.status, "APPROVED")
        self.assertNotEqual(app.created_church_id, existing.pk)

    def test_queued_mode_stays_pending(self):
        settings_obj = SiteSettings.load()
        settings_obj.auto_provision_public_trials = False
        settings_obj.save(update_fields=["auto_provision_public_trials"])
        clear_settings_cache()
        data = self._payload()
        data.pop("password")
        app = submit_tenant_application(data)
        self.assertEqual(app.status, "PENDING")
        self.assertFalse(User.objects.filter(username="pastorada").exists())
