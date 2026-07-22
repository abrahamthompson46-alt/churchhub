"""Regression tests for auth POST rate limiting (P0-6)."""

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings
from sitecontrol.services import clear_settings_cache
from sitecontrol.test_support import SiteControlClientHarness


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "login-rate-limit-tests",
        }
    }
)
class LoginRateLimitMiddlewareTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        cache.clear()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={
                "login_max_attempts": 3,
                "login_lockout_minutes": 15,
                "mfa_required_for_privileged": False,
            },
        )
        clear_settings_cache()
        conf = Conference.objects.create(name="RL Conf", code="RLC")
        zone = Zone.objects.create(name="RL Zone", code="RLZ", conference=conf)
        district = District.objects.create(name="RL Dist", code="RLD", zone=zone)
        self.church = Church.objects.create(name="RL Church", code="RLCH", district=district)
        self.member = User.objects.create_user(
            username="portal_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.client = Client()

    def tearDown(self):
        cache.clear()
        clear_settings_cache()

    def test_portal_login_locks_after_max_failed_attempts(self):
        url = reverse("portal:login")
        for _ in range(3):
            self.client.post(url, {"username": "portal_member", "password": "wrong"})
        self.assertTrue(cache.get("login_lock:127.0.0.1"))

        response = self.client.post(url, {"username": "portal_member", "password": "wrong"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url)

    def test_staff_login_still_rate_limited(self):
        url = reverse("login")
        for _ in range(3):
            self.client.post(url, {"username": "nobody", "password": "wrong"})
        self.assertTrue(cache.get("login_lock:127.0.0.1"))

    def test_password_reset_locks_after_max_attempts(self):
        url = reverse("password_reset")
        for _ in range(3):
            self.client.post(url, {"email": "abuse@example.com"})
        self.assertTrue(cache.get("reset_lock:127.0.0.1"))

        response = self.client.post(url, {"email": "abuse@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url)

    def test_successful_portal_login_clears_fail_counter(self):
        url = reverse("portal:login")
        self.client.post(url, {"username": "portal_member", "password": "wrong"})
        self.assertEqual(cache.get("login_fail:127.0.0.1"), 1)
        self.client.post(url, {"username": "portal_member", "password": "pass12345"})
        self.assertIsNone(cache.get("login_fail:127.0.0.1"))
