"""Production settings smoke checks (no live secrets required)."""

from django.test import SimpleTestCase, override_settings


class ProductionHttpsModeTests(SimpleTestCase):
    def test_trusted_device_cookie_follows_session_secure_flag(self):
        from django.http import HttpResponse

        from accounts.mfa import attach_trusted_device_cookie

        response = HttpResponse()
        with override_settings(SESSION_COOKIE_SECURE=False, DEBUG=False):
            attach_trusted_device_cookie(response, "tok-http")
        self.assertFalse(response.cookies["ch_trusted_device"]["secure"])

        response2 = HttpResponse()
        with override_settings(SESSION_COOKIE_SECURE=True, DEBUG=False):
            attach_trusted_device_cookie(response2, "tok-https")
        self.assertTrue(response2.cookies["ch_trusted_device"]["secure"])
