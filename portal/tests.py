"""Member portal smoke tests."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.models import Member
from organization.models import Church, Conference, District, Zone

User = get_user_model()


class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="PC", name="Portal Conf")
        cls.zone = Zone.objects.create(conference=cls.conference, code="PZ", name="Portal Zone")
        cls.district = District.objects.create(zone=cls.zone, code="PD", name="Portal Dist")
        cls.church = Church.objects.create(district=cls.district, code="PCH", name="Portal Church")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Member",
        )
        cls.member_user = User.objects.create_user(
            username="portal_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
            member=cls.member,
        )
        cls.staff = User.objects.create_user(
            username="portal_staff",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def test_portal_login_page(self):
        response = self.client.get(reverse("portal:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member sign in")

    def test_staff_login_links_to_portal(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("portal:login"))

    def test_member_portal_home(self):
        self.client.login(username="portal_member", password="pass12345")
        response = self.client.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Member")

    def test_staff_without_member_redirected(self):
        self.client.login(username="portal_staff", password="pass12345")
        response = self.client.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/", response.url)

    def test_login_uses_site_branding_fields(self):
        from sitecontrol.services import clear_settings_cache, get_site_settings

        settings_obj = get_site_settings()
        settings_obj.site_name = "FaithOS"
        settings_obj.site_tagline = "Secure church ops"
        settings_obj.login_highlights = "Highlight A\nHighlight B"
        settings_obj.save()
        clear_settings_cache()
        response = self.client.get(reverse("login"))
        self.assertContains(response, "FaithOS")
        self.assertContains(response, "Secure church ops")
        self.assertContains(response, "Highlight A")
