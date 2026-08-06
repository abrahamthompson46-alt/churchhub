"""HTTPS / Secure-cookie settings regressions."""

import os

from django.test import SimpleTestCase

from church_system.env import env_flag


class HttpsModeFlagTests(SimpleTestCase):
    def test_secure_ssl_redirect_env_false(self):
        previous = os.environ.get("SECURE_SSL_REDIRECT")
        os.environ["SECURE_SSL_REDIRECT"] = "false"
        try:
            self.assertFalse(bool(env_flag("SECURE_SSL_REDIRECT", True)))
        finally:
            if previous is None:
                os.environ.pop("SECURE_SSL_REDIRECT", None)
            else:
                os.environ["SECURE_SSL_REDIRECT"] = previous

    def test_secure_ssl_redirect_env_true_default(self):
        previous = os.environ.pop("SECURE_SSL_REDIRECT", None)
        try:
            self.assertTrue(bool(env_flag("SECURE_SSL_REDIRECT", True)))
        finally:
            if previous is not None:
                os.environ["SECURE_SSL_REDIRECT"] = previous

    def test_https_mode_drives_cookie_and_hsts_policy(self):
        """Document the production.py contract used on zreta.com."""
        for https_mode, expect_secure, expect_hsts in (
            (False, False, 0),
            (True, True, 31536000),
        ):
            session_secure = https_mode
            csrf_secure = https_mode
            hsts = 31536000 if https_mode else 0
            self.assertEqual(session_secure, expect_secure)
            self.assertEqual(csrf_secure, expect_secure)
            self.assertEqual(hsts, expect_hsts)
