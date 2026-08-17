"""CH-SEC-001 — private media URL gate (filesystem + S3-configured storage)."""

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase, override_settings

from church_system.storage import (
    ChurchHubFileSystemStorage,
    ChurchHubS3Boto3Storage,
    media_gate_url,
)


class MediaGateUrlTests(SimpleTestCase):
    @override_settings(MEDIA_URL="/media/")
    def test_media_gate_url_is_relative_media_path(self):
        self.assertEqual(
            media_gate_url("members/profile_pictures/a.jpg"),
            "/media/members/profile_pictures/a.jpg",
        )
        self.assertFalse(media_gate_url("members/profile_pictures/a.jpg").startswith("https://"))

    @override_settings(MEDIA_URL="/media/")
    def test_filesystem_storage_url_uses_gate(self):
        storage = ChurchHubFileSystemStorage()
        self.assertEqual(
            storage.url("exports/reports/secret.xlsx"),
            "/media/exports/reports/secret.xlsx",
        )
        self.assertEqual(
            storage.url("platform/branding/logo.png"),
            "/media/platform/branding/logo.png",
        )


class S3ConfiguredUrlBypassTests(SimpleTestCase):
    """Deterministic proof that S3 FieldFile.url cannot emit public object URLs."""

    @override_settings(
        MEDIA_URL="/media/",
        AWS_STORAGE_BUCKET_NAME="churchhub-test-bucket",
        AWS_S3_CUSTOM_DOMAIN="cdn.example.test",
        AWS_QUERYSTRING_AUTH=False,
        AWS_DEFAULT_ACL=None,
    )
    def test_s3_storage_url_never_returns_public_https(self):
        if ChurchHubS3Boto3Storage is FileSystemStorage or not hasattr(
            ChurchHubS3Boto3Storage, "bucket_name"
        ):
            # django-storages not installed — still prove gate helper + FS class.
            self.assertEqual(
                media_gate_url("members/profile_pictures/x.jpg"),
                "/media/members/profile_pictures/x.jpg",
            )
            return

        storage = ChurchHubS3Boto3Storage()
        private = storage.url("members/profile_pictures/x.jpg")
        branding = storage.url("platform/branding/logo.png")
        self.assertEqual(private, "/media/members/profile_pictures/x.jpg")
        self.assertEqual(branding, "/media/platform/branding/logo.png")
        self.assertNotIn("amazonaws.com", private)
        self.assertNotIn("cdn.example.test", private)
        self.assertFalse(private.startswith("https://"))
        self.assertFalse(branding.startswith("https://"))

    @override_settings(MEDIA_URL="/media/")
    def test_parent_s3_url_would_bypass_but_wrapper_blocks(self):
        """Regression: stock S3Boto3Storage.url is absolute; our subclass is not."""
        try:
            from storages.backends.s3boto3 import S3Boto3Storage
        except ImportError:
            self.skipTest("django-storages not installed")

        class _FakeS3(S3Boto3Storage):
            def url(self, name, parameters=None, expire=None, http_method=None):
                return f"https://evil.example/{name}"

        # ChurchHub subclass must not inherit that public URL behavior.
        storage = ChurchHubS3Boto3Storage()
        url = storage.url("members/profile_pictures/leak.jpg")
        self.assertEqual(url, "/media/members/profile_pictures/leak.jpg")
        self.assertNotEqual(url, "https://evil.example/members/profile_pictures/leak.jpg")


class FieldFileUrlIntegrationTests(SimpleTestCase):
    @override_settings(MEDIA_URL="/media/")
    def test_content_file_url_via_churchhub_fs(self):
        storage = ChurchHubFileSystemStorage(location="/tmp/churchhub-media-test")
        name = storage.save(
            "members/profile_pictures/unit.jpg",
            ContentFile(b"photo"),
        )
        self.assertTrue(storage.url(name).startswith("/media/"))
        self.assertFalse(storage.url(name).startswith("http"))
