"""Tests for giving app."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.client import ContextList
from django.urls import reverse

from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings

User = get_user_model()


class GivingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(code="G1", name="G Conf")
        zone = Zone.objects.create(conference=conf, code="G1", name="G Zone")
        dist = District.objects.create(zone=zone, code="G1", name="G Dist")
        cls.church = Church.objects.create(district=dist, code="G1", name="G Church")
        cls.member = Member.objects.create(
            church=cls.church, first_name="John", last_name="Doe", gender="Male"
        )

    def setUp(self):
        self.client = Client()
        self.treasury = User.objects.create_user(
            username="treasury_g", password="pass12345", role=UserRole.TREASURY, church=self.church
        )

    def test_giving_index(self):
        self.client.login(username="treasury_g", password="pass12345")
        response = self.client.get(reverse("giving:index"))
        self.assertEqual(response.status_code, 200)

    def test_member_statement(self):
        self.client.login(username="treasury_g", password="pass12345")
        response = self.client.get(reverse("giving:member_statement", args=[self.member.pk]))
        self.assertEqual(response.status_code, 200)
