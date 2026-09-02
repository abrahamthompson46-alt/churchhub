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
        self.assertContains(expired, "Your demo has ended")
        self.assertContains(expired, "Continue to payment")
        self.assertContains(expired, "Your records are kept")
        self.assertContains(expired, reverse("subscription_pay"))
        self.assertNotContains(expired, reverse("subscription_subscribe"))
        self.assertNotContains(expired, "mailto:")
        self.assertNotContains(expired, "support@churchhub.local")
        self.assertNotContains(expired, "Send your church name")

        pay = self.client.get(reverse("subscription_pay"))
        self.assertEqual(pay.status_code, 200)
        self.assertContains(pay, "Complete payment")
        self.assertContains(pay, "I have completed this payment")
        self.assertContains(pay, "DM01")
        self.assertContains(pay, "data-copy-target")
        blocked = self.client.get(reverse("subscription_subscribe"))
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.url, reverse("subscription_pay"))

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

    def _expire_demo_user(self):
        app = submit_tenant_application(self._payload())
        sub = TenantSubscription.objects.get(church=app.created_church)
        user = User.objects.get(username="pastorada")
        sub.expires_at = timezone.now().date()
        sub.save(update_fields=["expires_at"])
        self.client.force_login(user)
        return app, sub, user

    def test_subscribe_form_creates_request_and_notifies_platform(self):
        from dashboard.models import Notification
        from sitecontrol.models import SubscriptionActivationRequest
        from sitecontrol.services import tenant_health_alerts

        owner = User.objects.create_user(
            username="platowner",
            password="pass12345",
            email="owner@hub.test",
            is_platform_user=True,
            is_superuser=True,
            is_staff=True,
            platform_role="OWNER",
        )
        app, sub, user = self._expire_demo_user()

        skipped = self.client.get(reverse("subscription_subscribe"))
        self.assertEqual(skipped.status_code, 302)
        self.assertEqual(skipped.url, reverse("subscription_pay"))

        unpaid = self.client.post(
            reverse("subscription_pay"),
            {"billing_interval": "YEARLY"},
        )
        self.assertEqual(unpaid.status_code, 200)
        self.assertContains(unpaid, "I have completed this payment")

        paid = self.client.post(
            reverse("subscription_pay"),
            {"billing_interval": "YEARLY", "payment_completed": "on"},
        )
        self.assertEqual(paid.status_code, 302)
        self.assertEqual(paid.url, reverse("subscription_subscribe"))

        get_form = self.client.get(reverse("subscription_subscribe"))
        self.assertEqual(get_form.status_code, 200)
        self.assertContains(get_form, "Payment reference")
        self.assertContains(get_form, "Demo Chapel")

        missing_ref = self.client.post(
            reverse("subscription_subscribe"),
            {
                "church_name": "Demo Chapel",
                "church_code": "DM01",
                "church_address": "1 Demo St",
                "contact_name": "Pastor Ada",
                "contact_email": "ada@demo.test",
                "contact_phone": "0241112222",
                "payment_reference": "",
                "notes": "",
            },
        )
        self.assertEqual(missing_ref.status_code, 200)
        self.assertEqual(SubscriptionActivationRequest.objects.count(), 0)

        posted = self.client.post(
            reverse("subscription_subscribe"),
            {
                "church_name": "Demo Chapel",
                "church_code": "DM01",
                "church_address": "1 Demo St",
                "contact_name": "Pastor Ada",
                "contact_email": "ada@demo.test",
                "contact_phone": "0241112222",
                "payment_reference": "TRX-10482",
                "notes": "Paid via bank",
            },
        )
        self.assertEqual(posted.status_code, 302)
        self.assertEqual(posted.url, reverse("subscription_subscribe"))
        req = SubscriptionActivationRequest.objects.get()
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(req.payment_reference, "TRX-10482")
        self.assertEqual(req.church_id, app.created_church_id)
        self.assertEqual(req.submitted_by_id, user.pk)
        self.assertEqual(req.billing_interval, "YEARLY")
        self.assertEqual(req.payment_reference_normalized, "TRX-10482")

        note = Notification.objects.get(user=owner)
        self.assertEqual(note.title, "Full version request")
        self.assertIn("TRX-10482", note.message)
        self.assertIn(str(req.pk), note.action_url)

        alerts = tenant_health_alerts(owner)
        titles = [a["title"] for a in alerts]
        self.assertIn("Full version requests", titles)

        self.client.force_login(owner)
        platform_list = self.client.get(reverse("sitecontrol:activation_request_list"))
        self.assertEqual(platform_list.status_code, 200)
        self.assertContains(platform_list, "TRX-10482")
        self.assertContains(platform_list, "full-version request")
        if req.plan_name:
            self.assertContains(platform_list, req.plan_name)

    def test_active_subscription_cannot_open_subscribe_form(self):
        submit_tenant_application(self._payload())
        user = User.objects.get(username="pastorada")
        self.client.force_login(user)
        response = self.client.get(reverse("subscription_subscribe"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))
        pay = self.client.get(reverse("subscription_pay"))
        self.assertEqual(pay.status_code, 302)
        self.assertEqual(pay.url, reverse("dashboard:home"))

    def test_seven_day_warning_allows_pay_flow(self):
        from dashboard.models import Notification

        submit_tenant_application(self._payload())
        user = User.objects.get(username="pastorada")
        sub = TenantSubscription.objects.get(church=user.church)
        sub.expires_at = timezone.now().date() + timedelta(days=5)
        sub.save(update_fields=["expires_at"])
        self.assertTrue(sub.is_operational)
        self.client.force_login(user)

        home = self.client.get(reverse("dashboard:home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Pay now, then send upgrade details")
        self.assertTrue(
            Notification.objects.filter(
                user=user, title="Subscription ending soon"
            ).exists()
        )

        pay = self.client.get(reverse("subscription_pay"))
        self.assertEqual(pay.status_code, 200)
        skipped = self.client.get(reverse("subscription_subscribe"))
        self.assertEqual(skipped.url, reverse("subscription_pay"))

    def test_duplicate_payment_reference_rejected_across_churches(self):
        from sitecontrol.models import SubscriptionActivationRequest

        first, _sub, _user = self._expire_demo_user()
        self.client.post(
            reverse("subscription_pay"),
            {"billing_interval": "MONTHLY", "payment_completed": "on"},
        )
        posted = self.client.post(
            reverse("subscription_subscribe"),
            {
                "church_name": "Demo Chapel",
                "church_code": "DM01",
                "contact_name": "Pastor Ada",
                "contact_email": "ada@demo.test",
                "payment_reference": "SHARED-REF-1",
            },
        )
        self.assertEqual(posted.status_code, 302)
        self.assertEqual(SubscriptionActivationRequest.objects.count(), 1)

        self.client.logout()
        submit_tenant_application(
            self._payload(
                church_name="Second Chapel",
                church_code="DM02",
                contact_email="ada2@demo.test",
                contact_phone="+233 24 999 0000",
                applicant_username="pastorada2",
            )
        )
        other = User.objects.get(username="pastorada2")
        other_sub = TenantSubscription.objects.get(church=other.church)
        other_sub.expires_at = timezone.now().date()
        other_sub.save(update_fields=["expires_at"])
        self.client.force_login(other)
        self.client.post(
            reverse("subscription_pay"),
            {"billing_interval": "MONTHLY", "payment_completed": "on"},
        )
        rejected = self.client.post(
            reverse("subscription_subscribe"),
            {
                "church_name": "Second Chapel",
                "church_code": "DM02",
                "contact_name": "Pastor Two",
                "contact_email": "ada2@demo.test",
                "payment_reference": "shared-ref-1",
            },
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(rejected, "already used for another church")
        self.assertEqual(SubscriptionActivationRequest.objects.count(), 1)
