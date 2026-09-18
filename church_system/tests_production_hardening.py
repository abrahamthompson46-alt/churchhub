"""Regression tests for production hardening (MFA key, lockout, sessions, history)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import PasswordHistory, TrustedDevice
from accounts.password_reset import StaffPasswordChangeForm
from accounts.session_security import (
    password_was_used_recently,
    trusted_device_days_for_user,
)
from church_system.crypto import decrypt_fernet, encrypt_fernet
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings
from sitecontrol.services import clear_settings_cache
from sitecontrol.test_support import SiteControlClientHarness

User = get_user_model()


class MfaEncryptionKeyTests(TestCase):
    def test_decrypt_falls_back_to_secret_key_ciphertext(self):
        with override_settings(MFA_ENCRYPTION_KEY="", SECRET_KEY="legacy-secret-key"):
            token = encrypt_fernet("totp-shared-secret")
        with override_settings(MFA_ENCRYPTION_KEY="dedicated-mfa-key", SECRET_KEY="legacy-secret-key"):
            self.assertEqual(decrypt_fernet(token), "totp-shared-secret")
            rewritten = encrypt_fernet("totp-shared-secret")
        with override_settings(MFA_ENCRYPTION_KEY="dedicated-mfa-key", SECRET_KEY="rotated-django-secret"):
            self.assertEqual(decrypt_fernet(rewritten), "totp-shared-secret")


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "prod-hardening-lockout",
        }
    },
    LOGIN_IDENTIFIER_LOCK_MIN=20,
    LOGIN_IDENTIFIER_LOCK_MULTIPLIER=5,
)
class IdentifierLockoutNotPrimaryTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        cache.clear()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"login_max_attempts": 3, "login_lockout_minutes": 15},
        )
        clear_settings_cache()
        self.client = Client()

    def tearDown(self):
        cache.clear()
        clear_settings_cache()

    def test_three_failures_lock_ip_not_username(self):
        url = reverse("login")
        for _ in range(3):
            self.client.post(url, {"username": "treasurer", "password": "wrong"})
        self.assertTrue(cache.get("login_lock:127.0.0.1"))
        self.assertIsNone(cache.get("login_lock_user:treasurer"))


class SessionAndPasswordHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="PH", name="PH Conf")
        zone = Zone.objects.create(conference=conf, code="PHZ", name="PH Zone")
        district = District.objects.create(zone=zone, code="PHD", name="PH Dist")
        cls.church = Church.objects.create(district=district, code="PHC", name="PH Church")

    def test_treasury_cannot_reuse_previous_password(self):
        user = User.objects.create_user(
            username="hist_treasury",
            password="FirstPass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        form = StaffPasswordChangeForm(
            user,
            data={
                "old_password": "FirstPass12345",
                "new_password1": "SecondPass12345",
                "new_password2": "SecondPass12345",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertTrue(PasswordHistory.objects.filter(user=user).exists())
        self.assertTrue(password_was_used_recently(user, "FirstPass12345"))
        reuse = StaffPasswordChangeForm(
            user,
            data={
                "old_password": "SecondPass12345",
                "new_password1": "FirstPass12345",
                "new_password2": "FirstPass12345",
            },
        )
        self.assertFalse(reuse.is_valid())

    def test_logout_all_invalidates_other_client(self):
        user = User.objects.create_user(
            username="epoch_user",
            password="SessionPass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        a = Client()
        b = Client()
        self.assertTrue(a.login(username="epoch_user", password="SessionPass12345"))
        self.assertTrue(b.login(username="epoch_user", password="SessionPass12345"))
        a.get(reverse("accounts:profile"))
        b.get(reverse("accounts:profile"))
        response = a.post(reverse("accounts:logout_all"))
        self.assertEqual(response.status_code, 302)
        other = b.get(reverse("accounts:profile"))
        self.assertEqual(other.status_code, 302)
        self.assertIn("/accounts/login", other.url)

    def test_privileged_trusted_device_is_seven_days(self):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={
                "mfa_required_for_privileged": True,
                "mfa_institution_roles": ["TREASURY"],
            },
        )
        clear_settings_cache()
        user = User.objects.create_user(
            username="ttl_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertEqual(trusted_device_days_for_user(user), 7)
        from django.test import RequestFactory

        from accounts.mfa import create_trusted_device

        request = RequestFactory().get("/")
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 Chrome/1.0 Windows"
        create_trusted_device(user, request)
        device = TrustedDevice.objects.get(user=user)
        delta = device.expires_at - timezone.now()
        self.assertLess(delta, timedelta(days=8))
        self.assertGreater(delta, timedelta(days=6))
