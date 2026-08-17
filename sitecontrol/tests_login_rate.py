"""Regression tests for auth POST rate limiting (P0-6)."""

from datetime import date

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from members.models import Member
from organization.models import Church, Conference, District, Zone
from portal.services import canonical_dob_password
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
        self.portal_dob = date(1988, 3, 14)
        self.portal_email = "rl.member@example.com"
        self.member = Member.objects.create(
            church=self.church,
            first_name="Rate",
            last_name="Limited",
            email=self.portal_email,
            date_of_birth=self.portal_dob,
            gender="Male",
        )
        self.client = Client()

    def tearDown(self):
        cache.clear()
        clear_settings_cache()

    def test_portal_login_locks_after_max_failed_attempts(self):
        url = reverse("portal:login")
        for _ in range(3):
            self.client.post(url, {"username": self.portal_email, "password": "wrong"})
        self.assertTrue(cache.get("login_lock:127.0.0.1"))

        response = self.client.post(url, {"username": self.portal_email, "password": "wrong"})
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

    @override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
    def test_successful_portal_login_clears_fail_counter(self):
        url = reverse("portal:login")
        self.client.post(url, {"username": self.portal_email, "password": "wrong"})
        self.assertEqual(cache.get("login_fail:127.0.0.1"), 1)
        # Valid portal credentials reach pending-confirmation / success path.
        self.client.post(
            url,
            {
                "username": self.portal_email,
                "password": canonical_dob_password(self.portal_dob),
            },
        )
        self.assertIsNone(cache.get("login_fail:127.0.0.1"))
