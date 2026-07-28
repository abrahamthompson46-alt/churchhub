"""Platform access control and control room tests."""

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings
from sitecontrol.services import ensure_default_plans
from sitecontrol.test_support import SiteControlClientHarness


class PlatformAccessTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        conf = Conference.objects.create(name="C", code="C1")
        zone = Zone.objects.create(name="Z", code="Z1", conference=conf)
        district = District.objects.create(name="D", code="D1", zone=zone)
        self.church = Church.objects.create(name="Ch", code="CH1", district=district)

        self.platform_user = User.objects.create_user(
            username="platform",
            password="pass12345",
            is_platform_user=True,
            is_superuser=True,
            is_staff=True,
            platform_role="OWNER",
        )
        self.institution_user = User.objects.create_user(
            username="treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
            is_staff=False,
        )

    def test_platform_user_redirected_from_dashboard(self):
        self.client.login(username="platform", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/platform/", response.url)

    def test_platform_user_can_logout_from_control_room(self):
        self.client.login(username="platform", password="pass12345")
        response = self.client.get(reverse("dashboard:logout"), follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "logged_out.html")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_institution_user_blocked_from_platform(self):
        self.client.login(username="treasury", password="pass12345")
        response = self.client.get(reverse("sitecontrol:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/", response.url)

    def test_institution_user_blocked_from_admin(self):
        self.client.login(username="treasury", password="pass12345")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 403)

    def test_platform_login_redirects_to_control_room(self):
        response = self.client.post(
            reverse("login"),
            {"username": "platform", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("sitecontrol:dashboard"))

    def test_institution_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "treasury", "password": "pass12345"},
        )
        self.assertRedirects(response, reverse("dashboard:home"))

    def test_platform_dashboard_accessible(self):
        self.client.login(username="platform", password="pass12345")
        response = self.client.get(reverse("sitecontrol:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Control Room")

    def test_site_settings_singleton(self):
        settings_obj = SiteSettings.load()
        self.assertEqual(settings_obj.site_name, "ChurchHub")


class PlatformServiceTests(TestCase):
    def setUp(self):
        ensure_default_plans()
        conf = Conference.objects.create(name="C", code="C2")
        zone = Zone.objects.create(name="Z", code="Z2", conference=conf)
        district = District.objects.create(name="D", code="D2", zone=zone)
        self.church = Church.objects.create(name="Ch", code="CH2", district=district)

    def test_default_plans_created(self):
        from sitecontrol.models import SubscriptionPlan

        self.assertGreaterEqual(SubscriptionPlan.objects.count(), 3)

    def test_church_subscription_auto_created(self):
        from sitecontrol.models import TenantSubscription
        from sitecontrol.services import ensure_church_subscription

        sub = ensure_church_subscription(self.church)
        self.assertIsInstance(sub, TenantSubscription)

    def test_feature_flag_when_enforcement_off(self):
        """Soft mode: operational tenants get known features when enforce is off."""
        from sitecontrol.services import church_has_feature, clear_settings_cache, ensure_church_subscription

        ensure_church_subscription(self.church)
        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save()
        clear_settings_cache()
        self.assertTrue(church_has_feature(self.church, "payroll"))

    def test_suspended_denies_features_when_enforce_off(self):
        from sitecontrol.services import (
            church_has_feature,
            clear_settings_cache,
            ensure_church_subscription,
            suspend_tenant,
        )

        ensure_church_subscription(self.church)
        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save()
        clear_settings_cache()
        actor = User.objects.create_user(
            username="owner_suspend",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        suspend_tenant(self.church, actor, reason="test")
        self.assertFalse(church_has_feature(self.church, "payroll"))

    def test_unknown_feature_fails_closed(self):
        from sitecontrol.services import church_has_feature, ensure_church_subscription

        ensure_church_subscription(self.church)
        self.assertFalse(church_has_feature(self.church, "not_a_real_feature"))

    def test_lifecycle_suspend_reactivate(self):
        from sitecontrol.services import (
            ensure_church_subscription,
            reactivate_tenant,
            suspend_tenant,
        )

        sub = ensure_church_subscription(self.church)
        actor = User.objects.create_user(
            username="lifecycle_op",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        suspend_tenant(self.church, actor, reason="nonpayment")
        sub.refresh_from_db()
        self.assertEqual(sub.status, "SUSPENDED")
        self.assertIsNotNone(sub.suspended_at)
        reactivate_tenant(self.church, actor)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "ACTIVE")
        self.assertIsNone(sub.suspended_at)


class PlatformRBACTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination

        ensure_builtin_denominations()
        self.cop = Denomination.objects.get(code="cop")
        self.sda = Denomination.objects.get(code="sda")

        conf = Conference.objects.create(name="COP", code="COPR", denomination=self.cop)
        zone = Zone.objects.create(name="Z", code="ZR", conference=conf)
        district = District.objects.create(name="D", code="DR", zone=zone)
        self.cop_church = Church.objects.create(name="COP Ch", code="COPRCH", district=district)

        conf2 = Conference.objects.create(name="SDA", code="SDAR", denomination=self.sda)
        zone2 = Zone.objects.create(name="ZS", code="ZSR", conference=conf2)
        district2 = District.objects.create(name="DS", code="DSR", zone=zone2)
        self.sda_church = Church.objects.create(name="SDA Ch", code="SDARCH", district=district2)

        self.owner = User.objects.create_user(
            username="owner_rbac",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        self.readonly = User.objects.create_user(
            username="readonly_rbac",
            password="pass12345",
            is_platform_user=True,
            platform_role="READONLY",
        )
        self.readonly.managed_denominations.add(self.cop)
        self.support = User.objects.create_user(
            username="support_rbac",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
        )
        self.support.managed_denominations.add(self.cop)
        self.empty_non_owner = User.objects.create_user(
            username="empty_scope",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
        )

    def test_non_owner_empty_managed_denoms_not_global(self):
        from sitecontrol.platform_access import get_operator_denominations, operator_has_global_access

        self.assertFalse(operator_has_global_access(self.empty_non_owner))
        self.assertEqual(list(get_operator_denominations(self.empty_non_owner)), [])

    def test_scoped_operator_cannot_see_other_denom_tenants(self):
        client = Client()
        client.login(username="support_rbac", password="pass12345")
        response = client.get(reverse("sitecontrol:tenant_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COP Ch")
        self.assertNotContains(response, "SDA Ch")

        response = client.get(reverse("sitecontrol:tenant_detail", kwargs={"pk": self.sda_church.pk}))
        self.assertEqual(response.status_code, 403)

    def test_readonly_cannot_post_settings(self):
        client = Client()
        client.login(username="readonly_rbac", password="pass12345")
        response = client.get(reverse("sitecontrol:settings"))
        self.assertEqual(response.status_code, 403)
        response = client.post(reverse("sitecontrol:settings"), {"site_name": "Hacked"})
        self.assertEqual(response.status_code, 403)

    def test_feature_overrides_honored(self):
        from sitecontrol.services import (
            church_has_feature,
            clear_settings_cache,
            ensure_church_subscription,
            set_tenant_feature_overrides,
        )

        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = True
        settings_obj.save()
        clear_settings_cache()
        sub = ensure_church_subscription(self.cop_church)
        set_tenant_feature_overrides(sub, {"payroll": True})
        self.assertTrue(church_has_feature(self.cop_church, "payroll"))
        set_tenant_feature_overrides(sub, {"payroll": False})
        self.assertFalse(church_has_feature(self.cop_church, "payroll"))

    def test_readonly_can_browse_tenants(self):
        client = Client()
        client.login(username="readonly_rbac", password="pass12345")
        response = client.get(reverse("sitecontrol:tenant_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COP Ch")

    def test_offboard_deactivates_users(self):
        from sitecontrol.services import ensure_church_subscription, offboard_tenant

        ensure_church_subscription(self.cop_church)
        inst = User.objects.create_user(
            username="cop_user",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.cop_church,
        )
        offboard_tenant(self.cop_church, self.owner, reason="contract ended")
        inst.refresh_from_db()
        self.cop_church.refresh_from_db()
        self.assertFalse(inst.is_active)
        self.assertFalse(self.cop_church.is_active)
        self.assertEqual(self.cop_church.subscription.status, "EXPIRED")

    def test_ip_allowlist_blocks_unknown(self):
        from sitecontrol.services import clear_settings_cache, ip_allowed_for_platform

        settings_obj = SiteSettings.load()
        previous = settings_obj.platform_ip_allowlist
        try:
            settings_obj.platform_ip_allowlist = "10.0.0.1\n# comment\n"
            settings_obj.save(update_fields=["platform_ip_allowlist"])
            clear_settings_cache()
            self.assertTrue(ip_allowed_for_platform("10.0.0.1"))
            self.assertFalse(ip_allowed_for_platform("10.0.0.99"))
        finally:
            settings_obj.platform_ip_allowlist = previous
            settings_obj.save(update_fields=["platform_ip_allowlist"])
            clear_settings_cache()

    def test_smtp_password_encrypted_on_save(self):
        from sitecontrol.crypto import decrypt_secret, resolve_smtp_password
        from sitecontrol.forms import EmailSettingsForm

        settings_obj = SiteSettings.load()
        form = EmailSettingsForm(
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "mailer",
                "smtp_password": "s3cret-pass",
                "smtp_use_tls": True,
                "default_from_email": "noreply@example.com",
            },
            instance=settings_obj,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        settings_obj.refresh_from_db()
        self.assertEqual(settings_obj.smtp_password, "")
        self.assertTrue(settings_obj.smtp_password_encrypted)
        self.assertEqual(decrypt_secret(settings_obj.smtp_password_encrypted), "s3cret-pass")
        self.assertEqual(resolve_smtp_password(settings_obj), "s3cret-pass")


class RegistrationWorkflowTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination

        ensure_builtin_denominations()
        self.denomination = Denomination.objects.filter(is_active=True, allow_public_registration=True).first()
        conf = Conference.objects.create(name="RegConf", code="RC1", denomination=self.denomination)
        zone = Zone.objects.create(name="RegZone", code="RZ1", conference=conf)
        self.district = District.objects.create(name="RegDist", code="RD1", zone=zone)
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = True
        settings_obj.mfa_required_for_privileged = False
        settings_obj.save()
        from sitecontrol.services import clear_settings_cache
        clear_settings_cache()

        self.platform_user = User.objects.create_user(
            username="platform2",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )

    def test_public_apply_when_enabled(self):
        response = self.client.get("/apply/")
        self.assertEqual(response.status_code, 200)

    def test_public_apply_blocked_when_disabled(self):
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = False
        settings_obj.save()
        from sitecontrol.services import clear_settings_cache
        clear_settings_cache()
        response = self.client.get("/apply/")
        self.assertEqual(response.status_code, 403)

    def test_submit_and_approve_application(self):
        from sitecontrol.registration_services import submit_tenant_application, approve_tenant_application

        app = submit_tenant_application({
            "application_type": "EXISTING_DISTRICT",
            "denomination": self.denomination,
            "church_name": "New Chapel",
            "church_code": "NC01",
            "district": self.district,
            "contact_name": "Pastor Joe",
            "contact_email": "joe@example.com",
            "applicant_username": "pastorjoe",
        })
        self.assertEqual(app.status, "PENDING")

        app, church, invitation = approve_tenant_application(app, self.platform_user)
        self.assertEqual(app.status, "APPROVED")
        self.assertEqual(church.name, "New Chapel")
        self.assertIsNotNone(invitation)

    def test_institution_invite_blocked_when_disabled(self):
        settings_obj = SiteSettings.load()
        settings_obj.allow_institution_user_invites = False
        settings_obj.save()
        from sitecontrol.services import clear_settings_cache
        clear_settings_cache()

        church = Church.objects.create(name="C", code="C1", district=self.district)
        user = User.objects.create_user(
            username="instadmin2",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=church,
        )
        self.client.login(username="instadmin2", password="pass12345")
        response = self.client.get("/accounts/users/invite/")
        self.assertEqual(response.status_code, 302)


class BillingProvisioningTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination
        from sitecontrol.services import clear_settings_cache, ensure_default_payment_methods

        ensure_builtin_denominations()
        ensure_default_payment_methods()
        self.denomination = Denomination.objects.filter(is_active=True).first()
        self.denomination.allow_public_registration = True
        self.denomination.save(update_fields=["allow_public_registration"])
        conf = Conference.objects.create(name="ProvConf", code="PC1", denomination=self.denomination)
        zone = Zone.objects.create(name="ProvZone", code="PZ1", conference=conf)
        self.district = District.objects.create(name="ProvDist", code="PD1", zone=zone)
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = True
        settings_obj.mfa_required_for_privileged = False
        settings_obj.save()
        clear_settings_cache()

        self.platform_user = User.objects.create_user(
            username="billingowner",
            password="pass12345",
            is_platform_user=True,
            is_superuser=True,
            platform_role="OWNER",
        )

    def test_plan_pricing_fields(self):
        from sitecontrol.models import SubscriptionPlan

        plan = SubscriptionPlan.objects.filter(is_active=True).first()
        plan.currency = "GHS"
        plan.price_monthly = 100
        plan.price_yearly = 1000
        plan.trial_days = 30
        plan.save()
        plan.refresh_from_db()
        self.assertEqual(plan.effective_yearly_price, 1000)

    def test_provision_tenant_wizard(self):
        from sitecontrol.models import SubscriptionPlan, TenantSubscription
        from sitecontrol.provisioning_services import provision_tenant

        plan = SubscriptionPlan.objects.filter(is_active=True).first()
        church, sub, invitation = provision_tenant(
            setup_mode="EXISTING_DISTRICT",
            denomination=self.denomination,
            district=self.district,
            church_name="Provisioned Church",
            church_code="PRV1",
            admin_email="admin@prov.test",
            admin_username="provadmin",
            plan=plan,
            status="TRIAL",
            reviewer=self.platform_user,
        )
        self.assertEqual(church.name, "Provisioned Church")
        self.assertTrue(church.financials_provisioned)
        self.assertIsInstance(sub, TenantSubscription)
        self.assertEqual(sub.status, "TRIAL")
        self.assertTrue(sub.price_snapshot)
        self.assertIsNotNone(invitation)

    @patch("sitecontrol.views.send_invitation_email", return_value=True)
    def test_tenant_provision_view_sends_invitation_email(self, mock_send):
        from sitecontrol.models import SubscriptionPlan

        plan = SubscriptionPlan.objects.filter(is_active=True).first()
        self.client.login(username="billingowner", password="pass12345")
        response = self.client.post(
            reverse("sitecontrol:tenant_provision"),
            {
                "setup_mode": "EXISTING_DISTRICT",
                "denomination": str(self.denomination.pk),
                "district": str(self.district.pk),
                "church_name": "Emailed Church",
                "church_code": "EML1",
                "admin_email": "admin@email.test",
                "admin_username": "emailadmin",
                "plan": str(plan.pk),
                "status": "TRIAL",
                "billing_interval": "MONTHLY",
                "send_invite": "on",
                "admin_role": "LOCAL_PASTOR",
            },
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        invitation = mock_send.call_args.args[0]
        self.assertEqual(invitation.email, "admin@email.test")

    @patch("sitecontrol.views.resend_invitation")
    def test_tenant_resend_invitation_view(self, mock_resend):
        from accounts.models import UserInvitation
        from sitecontrol.models import SubscriptionPlan
        from sitecontrol.provisioning_services import provision_tenant

        plan = SubscriptionPlan.objects.filter(is_active=True).first()
        church, _sub, invitation = provision_tenant(
            setup_mode="EXISTING_DISTRICT",
            denomination=self.denomination,
            district=self.district,
            church_name="Resend Church",
            church_code="RSN1",
            admin_email="resend@prov.test",
            admin_username="resendadmin",
            plan=plan,
            status="TRIAL",
            reviewer=self.platform_user,
        )
        mock_resend.return_value = (invitation, True)
        self.client.login(username="billingowner", password="pass12345")
        response = self.client.post(
            reverse(
                "sitecontrol:tenant_resend_invitation",
                kwargs={"pk": church.pk, "invite_pk": invitation.pk},
            ),
        )
        self.assertEqual(response.status_code, 302)
        mock_resend.assert_called_once()
        self.assertTrue(UserInvitation.objects.filter(pk=invitation.pk).exists())

    def test_payment_method_crud_view(self):
        self.client.login(username="billingowner", password="pass12345")
        response = self.client.get(reverse("sitecontrol:payment_method_list"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("sitecontrol:tenant_provision"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provision Tenant")

    def test_approve_application_with_plan(self):
        from sitecontrol.models import PlatformPaymentMethod, SubscriptionPlan, TenantSubscription
        from sitecontrol.registration_services import approve_tenant_application, submit_tenant_application

        plan = SubscriptionPlan.objects.filter(code="starter").first() or SubscriptionPlan.objects.first()
        payment = PlatformPaymentMethod.objects.filter(is_active=True).first()
        app = submit_tenant_application({
            "application_type": "EXISTING_DISTRICT",
            "denomination": self.denomination,
            "church_name": "Plan Church",
            "church_code": "PLC1",
            "district": self.district,
            "contact_name": "Pastor",
            "contact_email": "plan@example.com",
            "applicant_username": "planpastor",
        })
        app, church, _ = approve_tenant_application(
            app,
            self.platform_user,
            plan=plan,
            status="TRIAL",
            payment_method=payment,
            payment_reference="REF-001",
            trial_days=7,
        )
        sub = TenantSubscription.objects.get(church=church)
        self.assertEqual(sub.plan_id, plan.pk)
        self.assertEqual(sub.payment_reference, "REF-001")
        self.assertEqual(sub.status, "TRIAL")

    def test_expire_due_subscriptions(self):
        from datetime import timedelta

        from django.utils import timezone

        from sitecontrol.models import TenantSubscription
        from sitecontrol.services import assign_subscription, expire_due_subscriptions, get_default_plan

        church = Church.objects.create(name="Expire Me", code="EX1", district=self.district)
        plan = get_default_plan()
        sub = assign_subscription(
            church,
            plan,
            status="TRIAL",
            expires_at=timezone.now().date() - timedelta(days=1),
        )
        count = expire_due_subscriptions()
        sub.refresh_from_db()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(sub.status, "EXPIRED")


class MfaSecurityPolicyTests(SiteControlClientHarness, TestCase):
    """Platform owners configure optional MFA audiences under Security Policy."""

    def setUp(self):
        self.disable_privileged_mfa()
        self.owner = User.objects.create_user(
            username="mfa_policy_owner",
            password="pass12345",
            is_platform_user=True,
            is_superuser=True,
            is_staff=True,
            platform_role="OWNER",
        )

    def test_security_settings_saves_mfa_audiences(self):
        self.client.login(username="mfa_policy_owner", password="pass12345")
        response = self.client.post(
            reverse("sitecontrol:security_settings"),
            {
                "password_min_length": 8,
                "password_require_uppercase": "on",
                "mfa_required_for_privileged": "on",
                "mfa_include_django_superusers": "on",
                "mfa_institution_roles": ["SECRETARY", "TREASURY"],
                "mfa_platform_roles": ["OWNER"],
                "platform_ip_allowlist": "",
                "maintenance_block_apply": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings_obj = SiteSettings.load()
        self.assertTrue(settings_obj.mfa_required_for_privileged)
        self.assertEqual(set(settings_obj.mfa_institution_roles), {"SECRETARY", "TREASURY"})
        self.assertEqual(set(settings_obj.mfa_platform_roles), {"OWNER"})
        self.assertTrue(settings_obj.mfa_include_django_superusers)
