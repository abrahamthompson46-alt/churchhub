"""MFA §9: per-user/per-IP verify throttling, expiry, and replay."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.mfa import (
    MFA_PENDING_TTL_SECONDS,
    SESSION_MFA_PENDING_AT,
    SESSION_MFA_PENDING_USER,
    enable_mfa_for_user,
    generate_recovery_codes,
    generate_totp_secret,
    issue_email_otp,
    remember_used_totp,
    verify_user_mfa,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.middleware import LoginRateLimitMiddleware
from sitecontrol.models import SiteSettings
from sitecontrol.services import clear_settings_cache

User = get_user_model()


def _patch_template_store():
    from unittest.mock import patch as _patch

    from django.test.client import ContextList

    def _safe_store(store, signal, sender, template, context, **kwargs):
        store.setdefault("templates", []).append(template)
        if "context" not in store:
            store["context"] = ContextList()
        store["context"].append(context)

    return _patch("django.test.client.store_rendered_templates", _safe_store)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mfa-throttle-tests",
        }
    }
)
class MfaVerifyThrottleTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._template_store_patcher = _patch_template_store()
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="MFT", name="MFA Throttle Conf")
        zone = Zone.objects.create(conference=conf, code="MTZ", name="Zone")
        district = District.objects.create(zone=zone, code="MTD", name="District")
        cls.church = Church.objects.create(district=district, code="MTC", name="Church")

    def setUp(self):
        cache.clear()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={
                "mfa_required_for_privileged": True,
                "mfa_institution_roles": ["SUPER_ADMIN", "TREASURY"],
                "mfa_platform_roles": ["OWNER", "SECURITY"],
                "mfa_include_django_superusers": True,
                "login_max_attempts": 3,
                "login_lockout_minutes": 15,
            },
        )
        clear_settings_cache()
        self.user = User.objects.create_user(
            username="mfa_throttle_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
            email="throttle@example.com",
        )
        self.secret = generate_totp_secret()
        enable_mfa_for_user(self.user, self.secret, generate_recovery_codes())
        self.verify_url = reverse("accounts:mfa_verify")
        self.login_url = reverse("login")

    def tearDown(self):
        cache.clear()
        clear_settings_cache()

    def _start_challenge(self, username="mfa_throttle_treasury", **extra):
        client = Client()
        response = client.post(
            self.login_url,
            {"username": username, "password": "pass12345"},
            **extra,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.verify_url)
        return client

    def _totp(self):
        import pyotp

        return pyotp.TOTP(self.secret).now()

    def test_login_limiter_does_not_include_mfa_path(self):
        self.assertNotIn("/accounts/mfa", LoginRateLimitMiddleware.LOGIN_PATHS)
        self.assertNotIn("/accounts/mfa/verify", LoginRateLimitMiddleware.LOGIN_PATHS)

    def test_valid_mfa_completes_login(self):
        client = self._start_challenge()
        response = client.post(self.verify_url, {"token": self._totp()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))

    def test_invalid_mfa_stays_on_challenge(self):
        client = self._start_challenge()
        response = client.post(self.verify_url, {"token": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid code")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_repeated_invalid_mfa_throttles_per_user(self):
        client = self._start_challenge(REMOTE_ADDR="10.10.0.1")
        for _ in range(3):
            response = client.post(
                self.verify_url,
                {"token": "000000"},
                REMOTE_ADDR="10.10.0.1",
            )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many attempts", status_code=429)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_valid_code_during_user_lockout_is_denied(self):
        client = self._start_challenge(REMOTE_ADDR="10.10.0.2")
        for _ in range(3):
            client.post(self.verify_url, {"token": "000000"}, REMOTE_ADDR="10.10.0.2")
        response = client.post(
            self.verify_url,
            {"token": self._totp()},
            REMOTE_ADDR="10.10.0.2",
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many attempts", status_code=429)

    def test_per_ip_throttling_locks_other_users_on_same_ip(self):
        other = User.objects.create_user(
            username="mfa_throttle_other",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
            email="other@example.com",
        )
        other_secret = generate_totp_secret()
        enable_mfa_for_user(other, other_secret, generate_recovery_codes())

        with patch("accounts.mfa.MFA_VERIFY_IP_MAX_ATTEMPTS", 3):
            client_a = self._start_challenge(REMOTE_ADDR="10.20.0.1")
            for _ in range(3):
                client_a.post(
                    self.verify_url,
                    {"token": "111111"},
                    REMOTE_ADDR="10.20.0.1",
                )
            client_b = Client()
            login_b = client_b.post(
                self.login_url,
                {"username": "mfa_throttle_other", "password": "pass12345"},
                REMOTE_ADDR="10.20.0.1",
            )
            self.assertEqual(login_b.status_code, 302)
            import pyotp

            response = client_b.post(
                self.verify_url,
                {"token": pyotp.TOTP(other_secret).now()},
                REMOTE_ADDR="10.20.0.1",
            )
            self.assertEqual(response.status_code, 429)

    def test_different_users_same_ip_below_ip_cap_still_work(self):
        other = User.objects.create_user(
            username="mfa_throttle_peer",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
            email="peer@example.com",
        )
        other_secret = generate_totp_secret()
        enable_mfa_for_user(other, other_secret, generate_recovery_codes())

        client_a = self._start_challenge(REMOTE_ADDR="10.30.0.1")
        client_a.post(self.verify_url, {"token": "000000"}, REMOTE_ADDR="10.30.0.1")

        client_b = Client()
        client_b.post(
            self.login_url,
            {"username": "mfa_throttle_peer", "password": "pass12345"},
            REMOTE_ADDR="10.30.0.1",
        )
        import pyotp

        response = client_b.post(
            self.verify_url,
            {"token": pyotp.TOTP(other_secret).now()},
            REMOTE_ADDR="10.30.0.1",
        )
        self.assertEqual(response.status_code, 302)

    def test_same_user_lock_applies_across_ips(self):
        client = self._start_challenge(REMOTE_ADDR="10.40.0.1")
        for _ in range(3):
            client.post(self.verify_url, {"token": "000000"}, REMOTE_ADDR="10.40.0.1")
        response = client.post(
            self.verify_url,
            {"token": self._totp()},
            REMOTE_ADDR="10.40.0.9",
        )
        self.assertEqual(response.status_code, 429)

    def test_same_user_from_different_ip_before_lock_can_succeed(self):
        client = self._start_challenge(REMOTE_ADDR="10.50.0.1")
        client.post(self.verify_url, {"token": "000000"}, REMOTE_ADDR="10.50.0.1")
        response = client.post(
            self.verify_url,
            {"token": self._totp()},
            REMOTE_ADDR="10.50.0.2",
        )
        self.assertEqual(response.status_code, 302)

    def test_challenge_expiration_clears_pending_and_redirects(self):
        client = self._start_challenge()
        session = client.session
        session[SESSION_MFA_PENDING_AT] = 1.0
        session.save()
        response = client.get(self.verify_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login_url)
        self.assertIsNone(client.session.get(SESSION_MFA_PENDING_USER))

    def test_missing_pending_timestamp_is_treated_as_expired(self):
        client = self._start_challenge()
        session = client.session
        session.pop(SESSION_MFA_PENDING_AT, None)
        session.save()
        response = client.get(self.verify_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.login_url)

    def test_successful_challenge_reuse_fails(self):
        client = self._start_challenge()
        token = self._totp()
        first = client.post(self.verify_url, {"token": token})
        self.assertEqual(first.status_code, 302)
        reuse = client.post(self.verify_url, {"token": token})
        self.assertEqual(reuse.status_code, 200)
        self.assertContains(reuse, "Invalid code")
        unauth = Client()
        replay = unauth.post(self.verify_url, {"token": token})
        self.assertEqual(replay.status_code, 302)
        self.assertEqual(replay.url, self.login_url)

    def test_totp_replay_within_window_fails(self):
        client_a = self._start_challenge()
        token = self._totp()
        first = client_a.post(self.verify_url, {"token": token})
        self.assertEqual(first.status_code, 302)

        client_b = self._start_challenge()
        second = client_b.post(self.verify_url, {"token": token})
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Invalid code")

    def test_email_otp_replay_after_success_fails(self):
        code = issue_email_otp(self.user)
        ok, method = verify_user_mfa(self.user, code)
        self.assertTrue(ok)
        self.assertEqual(method, "email")
        ok_again, method_again = verify_user_mfa(self.user, code)
        self.assertFalse(ok_again)
        self.assertEqual(method_again, "")

    def test_verify_user_mfa_totp_reuse_unit(self):
        token = self._totp()
        remember_used_totp(self.user, token)
        ok, method = verify_user_mfa(self.user, token)
        self.assertFalse(ok)
        self.assertEqual(method, "")

    def test_legitimate_retry_after_throttle_period(self):
        with patch("accounts.mfa._mfa_lock_settings", return_value=(3, 1)):
            client = self._start_challenge(REMOTE_ADDR="10.60.0.1")
            for _ in range(3):
                client.post(
                    self.verify_url,
                    {"token": "000000"},
                    REMOTE_ADDR="10.60.0.1",
                )
            locked = client.post(
                self.verify_url,
                {"token": self._totp()},
                REMOTE_ADDR="10.60.0.1",
            )
            self.assertEqual(locked.status_code, 429)
            import time

            time.sleep(1.2)
            allowed = client.post(
                self.verify_url,
                {"token": self._totp()},
                REMOTE_ADDR="10.60.0.1",
            )
            self.assertEqual(allowed.status_code, 302)

    def test_throttle_message_does_not_enumerate_accounts(self):
        client = self._start_challenge(REMOTE_ADDR="10.70.0.1")
        for _ in range(3):
            client.post(self.verify_url, {"token": "000000"}, REMOTE_ADDR="10.70.0.1")
        response = client.post(
            self.verify_url,
            {"token": "000000"},
            REMOTE_ADDR="10.70.0.1",
        )
        body = response.content.decode("utf-8").lower()
        self.assertNotIn("remaining", body)
        self.assertNotIn("attempts left", body)
        self.assertIn("too many attempts", body)

    def test_pending_ttl_constant_matches_email_otp(self):
        self.assertEqual(MFA_PENDING_TTL_SECONDS, 600)
