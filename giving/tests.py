"""Tests for giving app."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.models import Member
from organization.models import Church, Conference, District, Zone

User = get_user_model()


class GivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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
