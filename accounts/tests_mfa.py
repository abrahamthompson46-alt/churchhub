"""Tests for privileged-role MFA enrollment and login challenge."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.mfa import (
    enable_mfa_for_user,
    generate_recovery_codes,
    generate_totp_secret,
    user_requires_mfa,
    verify_totp,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings

User = get_user_model()


class MfaRequirementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="MFA", name="MFA Conf")
        zone = Zone.objects.create(conference=conf, code="MZ", name="MFA Zone")
        district = District.objects.create(zone=zone, code="MD", name="MFA District")
        cls.church = Church.objects.create(district=district, code="MC", name="MFA Church")

    def setUp(self):
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={
                "mfa_required_for_privileged": True,
                "mfa_institution_roles": ["SUPER_ADMIN", "TREASURY"],
                "mfa_platform_roles": ["OWNER", "SECURITY"],
                "mfa_include_django_superusers": True,
            },
        )
        clear_settings_cache()

    def test_treasury_requires_mfa(self):
        user = User.objects.create_user(
            username="mfa_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertTrue(user_requires_mfa(user))

    def test_secretary_does_not_require_mfa(self):
        user = User.objects.create_user(
            username="mfa_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.assertFalse(user_requires_mfa(user))

    def test_platform_owner_requires_mfa(self):
        user = User.objects.create_user(
            username="mfa_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        self.assertTrue(user_requires_mfa(user))

    def test_enforcement_toggle_disables_requirement(self):
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.filter(singleton_id=1).update(mfa_required_for_privileged=False)
        clear_settings_cache()
        user = User.objects.create_user(
            username="mfa_treasury2",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertFalse(user_requires_mfa(user))

    def test_custom_institution_audience(self):
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.filter(singleton_id=1).update(
            mfa_required_for_privileged=True,
            mfa_institution_roles=["SECRETARY"],
        )
        clear_settings_cache()
        secretary = User.objects.create_user(
            username="mfa_custom_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        treasury = User.objects.create_user(
            username="mfa_custom_treas",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertTrue(user_requires_mfa(secretary))
        self.assertFalse(user_requires_mfa(treasury))

    def test_mfa_optional_by_default(self):
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.filter(singleton_id=1).update(mfa_required_for_privileged=False)
        clear_settings_cache()
        from accounts.mfa import mfa_enforcement_enabled

        self.assertFalse(mfa_enforcement_enabled())


class MfaLoginFlowTests(TestCase):
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

    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="MFL", name="MFA Login Conf")
        zone = Zone.objects.create(conference=conf, code="MLZ", name="Zone")
        district = District.objects.create(zone=zone, code="MLD", name="District")
        cls.church = Church.objects.create(district=district, code="MLC", name="Church")
        cls.treasury = User.objects.create_user(
            username="mfa_login_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def setUp(self):
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={
                "mfa_required_for_privileged": True,
                "mfa_institution_roles": ["SUPER_ADMIN", "TREASURY"],
                "mfa_platform_roles": ["OWNER", "SECURITY"],
                "mfa_include_django_superusers": True,
            },
        )
        clear_settings_cache()

    def test_privileged_login_without_mfa_redirects_to_enroll(self):
        client = Client()
        response = client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:mfa_enroll"))

    def test_enrolled_login_requires_totp_before_dashboard(self):
        secret = generate_totp_secret()
        codes = generate_recovery_codes()
        enable_mfa_for_user(self.treasury, secret, codes)

        client = Client()
        response = client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:mfa_verify"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        import pyotp

        token = pyotp.TOTP(secret).now()
        verify = client.post(reverse("accounts:mfa_verify"), {"token": token})
        self.assertEqual(verify.status_code, 302)
        self.assertEqual(verify.url, reverse("dashboard:home"))

        dash = client.get(reverse("dashboard:home"))
        self.assertEqual(dash.status_code, 200)

    def test_recovery_code_completes_login(self):
        secret = generate_totp_secret()
        codes = generate_recovery_codes()
        enable_mfa_for_user(self.treasury, secret, codes)
        recovery = codes[0]

        client = Client()
        client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        verify = client.post(reverse("accounts:mfa_verify"), {"token": recovery})
        self.assertEqual(verify.status_code, 302)
        self.treasury.refresh_from_db()
        self.assertEqual(len(self.treasury.mfa_recovery_hashes), len(codes) - 1)

    def test_dashboard_blocked_until_mfa_verified(self):
        secret = generate_totp_secret()
        enable_mfa_for_user(self.treasury, secret, generate_recovery_codes())
        client = Client()
        client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        blocked = client.get(reverse("dashboard:home"))
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(blocked.url, reverse("accounts:mfa_verify"))

    def test_platform_owner_mfa_enroll_not_redirect_loop(self):
        """Platform lane must allow /accounts/mfa/* (UserScopeMiddleware)."""
        User.objects.create_user(
            username="mfa_platform_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        client = Client()
        login = client.post(
            reverse("login"),
            {"username": "mfa_platform_owner", "password": "pass12345"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.url, reverse("accounts:mfa_enroll"))
        enroll = client.get(reverse("accounts:mfa_enroll"))
        self.assertEqual(enroll.status_code, 200)
        self.assertContains(enroll, 'alt="QR code to enroll authenticator app"')
        self.assertContains(enroll, "data:image/png;base64,")
        platform = client.get(reverse("sitecontrol:dashboard"))
        self.assertEqual(platform.status_code, 302)
        self.assertEqual(platform.url, reverse("accounts:mfa_enroll"))

    def test_email_otp_and_trusted_device_skip_challenge(self):
        from accounts.mfa import (
            TRUSTED_DEVICE_COOKIE,
            enable_mfa_for_user,
            generate_recovery_codes,
            generate_totp_secret,
            issue_email_otp,
        )

        self.treasury.email = "treasury@example.com"
        self.treasury.save(update_fields=["email"])
        secret = generate_totp_secret()
        enable_mfa_for_user(self.treasury, secret, generate_recovery_codes())

        # Email OTP path
        code = issue_email_otp(self.treasury)
        client = Client()
        client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        verify = client.post(
            reverse("accounts:mfa_verify"),
            {"token": code, "action": "verify", "remember_device": "1"},
        )
        self.assertEqual(verify.status_code, 302)
        self.assertEqual(verify.url, reverse("dashboard:home"))
        self.assertIn(TRUSTED_DEVICE_COOKIE, verify.cookies)
        trusted = verify.cookies[TRUSTED_DEVICE_COOKIE].value

        # Logout and login again — trusted cookie should skip MFA challenge
        client.logout()
        client.cookies[TRUSTED_DEVICE_COOKIE] = trusted
        again = client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        self.assertEqual(again.status_code, 302)
        self.assertEqual(again.url, reverse("dashboard:home"))
        dash = client.get(reverse("dashboard:home"))
        self.assertEqual(dash.status_code, 200)

    def test_enroll_page_shows_scannable_qr(self):
        client = Client()
        client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        enroll = client.get(reverse("accounts:mfa_enroll"))
        self.assertEqual(enroll.status_code, 200)
        self.assertContains(enroll, "data:image/png;base64,")
        self.assertContains(enroll, "Scan the QR code")

    def test_enroll_secret_stable_across_reload_and_accepts_code(self):
        import pyotp

        from accounts.mfa import SESSION_MFA_ENROLL_SECRET

        client = Client()
        client.post(
            reverse("login"),
            {"username": "mfa_login_treasury", "password": "pass12345"},
        )
        first = client.get(reverse("accounts:mfa_enroll"))
        self.assertEqual(first.status_code, 200)
        secret = client.session[SESSION_MFA_ENROLL_SECRET]
        second = client.get(reverse("accounts:mfa_enroll"))
        self.assertEqual(second.status_code, 200)
        self.assertEqual(client.session[SESSION_MFA_ENROLL_SECRET], secret)

        code = pyotp.TOTP(secret).now()
        enable = client.post(reverse("accounts:mfa_enroll"), {"token": code})
        self.assertEqual(enable.status_code, 200)
        self.assertContains(enable, "recovery")
        self.treasury.refresh_from_db()
        self.assertTrue(self.treasury.mfa_enabled)