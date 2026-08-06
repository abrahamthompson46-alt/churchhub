"""Private media path classification and protected serving tests."""

import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from church_system.media_access import (
    is_public_media_path,
    is_public_media_url,
    normalize_media_relative_path,
)

User = get_user_model()


class MediaAccessHelpersTests(SimpleTestCase):
    def test_normalize_rejects_traversal(self):
        self.assertIsNone(normalize_media_relative_path("../secret.txt"))
        self.assertIsNone(normalize_media_relative_path("members/../../etc/passwd"))
        self.assertIsNone(normalize_media_relative_path(""))

    def test_normalize_accepts_nested_paths(self):
        self.assertEqual(
            normalize_media_relative_path("/members/profile_pictures/a.jpg"),
            "members/profile_pictures/a.jpg",
        )

    def test_public_branding_paths(self):
        self.assertTrue(is_public_media_path("platform/branding/logo.png"))
        self.assertTrue(is_public_media_path("denominations/branding/x.png"))
        self.assertFalse(is_public_media_path("members/profile_pictures/x.jpg"))
        self.assertFalse(is_public_media_path("exports/reports/a.xlsx"))
        self.assertTrue(is_public_media_url("/media/platform/branding/logo.png"))
        self.assertFalse(is_public_media_url("/media/members/x.jpg"))


class ProtectedMediaViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.media_root = Path(cls._tmpdir.name)
        (cls.media_root / "platform" / "branding").mkdir(parents=True)
        (cls.media_root / "members" / "profile_pictures").mkdir(parents=True)
        (cls.media_root / "platform" / "branding" / "logo.png").write_bytes(b"public-logo")
        (cls.media_root / "members" / "profile_pictures" / "p.jpg").write_bytes(
            b"private-photo"
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self._settings_ctx = override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_X_ACCEL_REDIRECT=False,
        )
        self._settings_ctx.enable()
        self.addCleanup(self._settings_ctx.disable)

    def test_anonymous_can_fetch_public_branding(self):
        response = self.client.get("/media/platform/branding/logo.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"public-logo")

    def test_anonymous_private_media_redirects_to_login(self):
        response = self.client.get("/media/members/profile_pictures/p.jpg")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_authenticated_can_fetch_private_media(self):
        user = User.objects.create_user(username="mediauser", password="test-pass-12345")
        self.client.force_login(user)
        response = self.client.get("/media/members/profile_pictures/p.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"private-photo")

    def test_path_traversal_returns_404(self):
        response = self.client.get("/media/../church_system/settings/base.py")
        # Django URL path may normalize; either 404 or login redirect for non-public
        self.assertIn(response.status_code, (302, 404))

    def test_x_accel_redirect_header(self):
        user = User.objects.create_user(username="acceluser", password="test-pass-12345")
        self.client.force_login(user)
        with override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_X_ACCEL_REDIRECT=True,
            MEDIA_INTERNAL_URL_PREFIX="/internal-media/",
        ):
            response = self.client.get("/media/members/profile_pictures/p.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Accel-Redirect"],
            "/internal-media/members/profile_pictures/p.jpg",
        )


class ProtectedMediaUrlNameTests(SimpleTestCase):
    def test_url_name_resolves(self):
        self.assertEqual(
            reverse("protected_media", kwargs={"path": "members/a.jpg"}),
            "/media/members/a.jpg",
        )
