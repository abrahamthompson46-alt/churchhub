"""Portal welfare self-service tests."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from members.models import Member
from organization.models import Church, Conference, District, Zone
from remittance.models import WelfareAssistanceCase
from remittance.welfare_services import create_welfare_case, record_manual_welfare_contribution
from transactions.services import approve_transaction, open_working_day

User = get_user_model()


class PortalWelfareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="WC", name="Welfare Conf")
        cls.zone = Zone.objects.create(conference=cls.conference, code="WZ", name="Welfare Zone")
        cls.district = District.objects.create(zone=cls.zone, code="WD", name="Welfare Dist")
        cls.church = Church.objects.create(district=cls.district, code="WCH", name="Welfare Church")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Member",
            email="ada.welfare@example.com",
            date_of_birth=date(1990, 5, 21),
            gender="Female",
        )
        cls.member_user = User.objects.create_user(
            username="welfare_portal_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
            member=cls.member,
            email="ada.welfare@example.com",
        )
        cls.staff = User.objects.create_user(
            username="welfare_portal_staff",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def setUp(self):
        self.client = Client()
        open_working_day(self.church, timezone.localdate(), self.staff)
        trx, _ = record_manual_welfare_contribution(
            self.church,
            self.member,
            Decimal("50.00"),
            self.staff,
            notes="Portal test",
        )
        approve_transaction(trx, self.staff)

    def test_member_welfare_page(self):
        self.client.login(username="welfare_portal_member", password="pass12345")
        response = self.client.get(reverse("portal:welfare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My welfare")
        self.assertContains(response, "Contributed")

    def test_member_welfare_filter_entry_type(self):
        self.client.login(username="welfare_portal_member", password="pass12345")
        response = self.client.get(
            reverse("portal:welfare"),
            {"entry_type": "CONTRIBUTION"},
        )
        self.assertEqual(response.status_code, 200)

    def test_welfare_request_submission(self):
        self.client.login(username="welfare_portal_member", password="pass12345")
        response = self.client.post(
            reverse("portal:welfare_request"),
            {
                "assistance_type": "MEDICAL",
                "amount_requested": "250.00",
                "priority": "NORMAL",
                "reason": "Need support for medical bills this month for my family.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WelfareAssistanceCase.objects.filter(member=self.member).count(), 1)

    def test_member_cannot_view_other_case(self):
        other_case = create_welfare_case(
            self.church,
            self.member,
            Decimal("10.00"),
            "Other case for isolation test",
            self.staff,
        )
        other_member = self.member.__class__.objects.create(
            church=self.church,
            first_name="Other",
            last_name="Person",
            email="other@example.com",
            gender="Male",
        )
        from accounts.models import UserRole
        from django.contrib.auth import get_user_model

        User = get_user_model()
        other_user = User.objects.create_user(
            username="other_portal",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
            member=other_member,
            email="other@example.com",
        )
        self.client.login(username="other_portal", password="pass12345")
        response = self.client.get(reverse("portal:welfare_case", kwargs={"pk": other_case.pk}))
        self.assertEqual(response.status_code, 403)

    def test_home_shows_welfare_when_enabled(self):
        self.client.login(username="welfare_portal_member", password="pass12345")
        response = self.client.get(reverse("portal:home"))
        self.assertContains(response, reverse("portal:welfare"))
