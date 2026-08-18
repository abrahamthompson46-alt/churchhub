"""Public landing page at `/`."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings

User = get_user_model()


class PublicHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(code="LH1", name="Landing Conf")
        zone = Zone.objects.create(conference=conf, code="LHZ", name="Landing Zone")
        district = District.objects.create(zone=zone, code="LHD", name="Landing Dist")
        cls.church = Church.objects.create(district=district, code="LHC", name="Landing Church")

    def test_anonymous_root_renders_landing(self):
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff sign in")
        self.assertContains(response, reverse("login"))
        self.assertContains(response, reverse("portal:login"))

    def test_public_home_url_is_root(self):
        self.assertEqual(reverse("public_home"), "/")

    def test_staff_user_is_sent_to_dashboard(self):
        User.objects.create_user(
            username="landing_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        client = Client()
        client.login(username="landing_treasury", password="pass12345")
        response = client.get("/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:home"))

    def test_member_user_is_sent_to_portal(self):
        User.objects.create_user(
            username="landing_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        client = Client()
        client.login(username="landing_member", password="pass12345")
        response = client.get("/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("portal:home"))
