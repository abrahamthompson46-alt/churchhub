"""Private media path classification and protected serving tests.

INV-MED-01 / INV-MED-02: authentication is not authorization.
"""

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
from church_system.media_authorization import user_may_access_media
from members.models import Gender, Member, MembershipStatus
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from reports.models import ReportExportJob
from sitecontrol.models import Denomination, SiteSettings
from sitecontrol.services import clear_settings_cache

User = get_user_model()


def _body(response) -> bytes:
    if getattr(response, "streaming", False):
        return b"".join(response.streaming_content)
    return response.content


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
    """INV-MED-01: cross-tenant private media is 404 with zero bytes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.media_root = Path(cls._tmpdir.name)
        (cls.media_root / "platform" / "branding").mkdir(parents=True)
        (cls.media_root / "members" / "profile_pictures").mkdir(parents=True)
        (cls.media_root / "exports" / "reports").mkdir(parents=True)
        (cls.media_root / "orphan").mkdir(parents=True)
        (cls.media_root / "platform" / "branding" / "logo.png").write_bytes(b"public-logo")
        (cls.media_root / "members" / "profile_pictures" / "a.jpg").write_bytes(b"photo-a")
        (cls.media_root / "members" / "profile_pictures" / "b.jpg").write_bytes(b"photo-b")
        (cls.media_root / "members" / "profile_pictures" / "c.jpg").write_bytes(b"photo-c")
        (cls.media_root / "exports" / "reports" / "secret.xlsx").write_bytes(b"export-a")
        (cls.media_root / "orphan" / "x.bin").write_bytes(b"unknown-prefix")

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        denom_a = Denomination.objects.create(code="med-a", name="Media Denom A")
        denom_b = Denomination.objects.create(code="med-b", name="Media Denom B")
        conf_a = Conference.objects.create(
            name="Media Conf A", code="MCA", denomination=denom_a
        )
        conf_b = Conference.objects.create(
            name="Media Conf B", code="MCB", denomination=denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="MZA", name="Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="MZB", name="Zone B")
        dist_a = District.objects.create(zone=zone_a, code="MDA", name="Dist A")
        dist_b = District.objects.create(zone=zone_b, code="MDB", name="Dist B")
        cls.church_a = Church.objects.create(district=dist_a, code="CHA", name="Church A")
        cls.church_b = Church.objects.create(district=dist_b, code="CHB", name="Church B")
        cls.staff_a = User.objects.create_user(
            username="media_staff_a",
            password="test-pass-12345",
            role=UserRole.SECRETARY,
            church=cls.church_a,
        )
        cls.staff_b = User.objects.create_user(
            username="media_staff_b",
            password="test-pass-12345",
            role=UserRole.SECRETARY,
            church=cls.church_b,
        )
        cls.unscoped = User.objects.create_user(
            username="media_unscoped",
            password="test-pass-12345",
            role=UserRole.SECRETARY,
        )
        cls.member_user = User.objects.create_user(
            username="media_member_a",
            password="test-pass-12345",
            role=UserRole.MEMBER,
            church=cls.church_a,
        )
        cls.member_a = Member.objects.create(
            church=cls.church_a,
            first_name="Alice",
            last_name="A",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
        )
        cls.member_a.profile_picture.name = "members/profile_pictures/a.jpg"
        cls.member_a.save(update_fields=["profile_picture"])
        cls.member_user.member = cls.member_a
        cls.member_user.save(update_fields=["member"])
        cls.member_b = Member.objects.create(
            church=cls.church_b,
            first_name="Bob",
            last_name="B",
            gender=Gender.MALE,
            membership_status=MembershipStatus.ACTIVE,
        )
        cls.member_b.profile_picture.name = "members/profile_pictures/b.jpg"
        cls.member_b.save(update_fields=["profile_picture"])
        cls.member_c = Member.objects.create(
            church=cls.church_a,
            first_name="Cara",
            last_name="C",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
        )
        cls.member_c.profile_picture.name = "members/profile_pictures/c.jpg"
        cls.member_c.save(update_fields=["profile_picture"])
        cls.export_a = ReportExportJob.objects.create(
            user=cls.staff_a,
            report_key="members",
            export_format="xlsx",
            status=ReportExportJob.STATUS_COMPLETE,
            content_type="application/vnd.ms-excel",
        )
        cls.export_a.export_file.name = "exports/reports/secret.xlsx"
        cls.export_a.save(update_fields=["export_file"])

    def setUp(self):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        clear_settings_cache()
        self.client = Client()
        self._settings_ctx = override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_X_ACCEL_REDIRECT=False,
        )
        self._settings_ctx.enable()
        self.addCleanup(self._settings_ctx.disable)

    def _login(self, username):
        self.assertTrue(self.client.login(username=username, password="test-pass-12345"))

    def _assert_private_media_denied(self, response, secret: bytes):
        """INV-MED-02: 404 and none of the private file bytes."""
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(secret, _body(response))
        self.assertFalse(response.has_header("X-Accel-Redirect"))

    def test_anonymous_can_fetch_public_branding(self):
        response = self.client.get("/media/platform/branding/logo.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), b"public-logo")

    def test_anonymous_private_media_redirects_to_login(self):
        response = self.client.get("/media/members/profile_pictures/a.jpg")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_same_tenant_staff_can_fetch_member_photo(self):
        self._login("media_staff_a")
        response = self.client.get("/media/members/profile_pictures/a.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), b"photo-a")

    def test_cross_tenant_staff_member_photo_is_404(self):
        self._login("media_staff_a")
        response = self.client.get("/media/members/profile_pictures/b.jpg")
        self._assert_private_media_denied(response, b"photo-b")

    def test_portal_member_can_fetch_own_photo(self):
        self._login("media_member_a")
        response = self.client.get("/media/members/profile_pictures/a.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), b"photo-a")

    def test_portal_member_other_denomination_photo_is_404(self):
        self._login("media_member_a")
        response = self.client.get("/media/members/profile_pictures/b.jpg")
        self._assert_private_media_denied(response, b"photo-b")

    def test_wrong_role_cannot_fetch_other_member_photo(self):
        self._login("media_member_a")
        response = self.client.get("/media/members/profile_pictures/c.jpg")
        self._assert_private_media_denied(response, b"photo-c")

    def test_unscoped_user_private_media_is_404(self):
        self._login("media_unscoped")
        response = self.client.get("/media/members/profile_pictures/a.jpg")
        self._assert_private_media_denied(response, b"photo-a")

    def test_unknown_prefix_is_404(self):
        self._login("media_staff_a")
        response = self.client.get("/media/orphan/x.bin")
        self._assert_private_media_denied(response, b"unknown-prefix")

    def test_export_owner_can_fetch_file(self):
        self._login("media_staff_a")
        response = self.client.get("/media/exports/reports/secret.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), b"export-a")

    def test_wrong_role_cannot_fetch_others_export(self):
        self._login("media_member_a")
        response = self.client.get("/media/exports/reports/secret.xlsx")
        self._assert_private_media_denied(response, b"export-a")

    def test_path_traversal_returns_404(self):
        response = self.client.get("/media/../church_system/settings/base.py")
        self.assertIn(response.status_code, (302, 404))

    def test_x_accel_redirect_header_after_allow(self):
        self._login("media_staff_a")
        with override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_X_ACCEL_REDIRECT=True,
            MEDIA_INTERNAL_URL_PREFIX="/internal-media/",
        ):
            response = self.client.get("/media/members/profile_pictures/a.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Accel-Redirect"],
            "/internal-media/members/profile_pictures/a.jpg",
        )

    def test_x_accel_not_set_on_cross_tenant_deny(self):
        self._login("media_staff_a")
        with override_settings(
            MEDIA_ROOT=str(self.media_root),
            MEDIA_X_ACCEL_REDIRECT=True,
            MEDIA_INTERNAL_URL_PREFIX="/internal-media/",
        ):
            response = self.client.get("/media/members/profile_pictures/b.jpg")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.has_header("X-Accel-Redirect"))
        self.assertNotIn(b"photo-b", _body(response))

    def test_user_may_access_media_unit_rules(self):
        self.assertTrue(
            user_may_access_media(self.staff_a, "members/profile_pictures/a.jpg")
        )
        self.assertFalse(
            user_may_access_media(self.staff_a, "members/profile_pictures/b.jpg")
        )
        self.assertFalse(user_may_access_media(self.unscoped, "members/profile_pictures/a.jpg"))
        self.assertFalse(user_may_access_media(self.staff_a, "orphan/x.bin"))
        self.assertFalse(user_may_access_media(self.member_user, "exports/reports/secret.xlsx"))
        self.assertFalse(user_may_access_media(self.member_user, "members/profile_pictures/c.jpg"))


class ProtectedMediaUrlNameTests(SimpleTestCase):
    def test_url_name_resolves(self):
        self.assertEqual(
            reverse("protected_media", kwargs={"path": "members/a.jpg"}),
            "/media/members/a.jpg",
        )
