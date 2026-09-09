"""Membership dashboard snapshot — KPIs, demographics, trends, quality."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from dashboard.member_summary import build_member_dashboard, parse_trend_months
from dashboard.services import get_member_summary
from members.models import Gender, MembershipStatus, Member, MemberTransfer, TransferStatus
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class MemberDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="mdash", name="Member Dash Denom", is_active=True
        )
        cls.conference = Conference.objects.create(
            code="MD", name="MD Conf", denomination=cls.denomination
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z", name="Z")
        cls.district = District.objects.create(zone=cls.zone, code="D", name="D")
        cls.church = Church.objects.create(district=cls.district, code="C1", name="Alpha")
        cls.other = Church.objects.create(district=cls.district, code="C2", name="Beta")
        today = timezone.localdate()
        cls.today = today
        cls.secretary = User.objects.create_user(
            username="md_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
            denomination=cls.denomination,
        )
        cls.treasury = User.objects.create_user(
            username="md_treas",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
            denomination=cls.denomination,
        )
        from permissions.models import Permission
        from permissions.services import create_override

        for code in ("view_members", "manage_members"):
            perm = Permission.objects.get(codename=code)
            create_override(cls.treasury, perm, granted=False, reason="dashboard isolation test")
        cls.outsider = User.objects.create_user(
            username="md_out",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.other,
            denomination=cls.denomination,
        )
        Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Active",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
            date_of_birth=date(today.year - 40, 6, 1),
            date_joined=today.replace(day=1),
            baptism_date=date(today.year - 10, 3, 1),
            phone="0244000001",
            email="ada@example.com",
        )
        Member.objects.create(
            church=cls.church,
            first_name="Ben",
            last_name="Inactive",
            gender=Gender.MALE,
            membership_status=MembershipStatus.INACTIVE,
            date_of_birth=date(today.year - 16, 1, 15),
            date_joined=today - timedelta(days=400),
            phone="",
            email="",
        )
        transferred = Member.objects.create(
            church=cls.church,
            first_name="Cara",
            last_name="Moved",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.TRANSFERRED,
            date_joined=today - timedelta(days=800),
        )
        Member.objects.create(
            church=cls.church,
            first_name="Dan",
            last_name="Unknown",
            gender="",
            membership_status=MembershipStatus.ACTIVE,
            date_of_birth=None,
            date_joined=None,
        )
        Member.objects.create(
            church=cls.other,
            first_name="Eve",
            last_name="Other",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
            date_joined=today,
        )
        MemberTransfer.objects.create(
            member=transferred,
            from_church=cls.church,
            to_church=cls.other,
            status=TransferStatus.COMPLETED,
            transfer_date=today.replace(day=1),
            requested_by=cls.secretary,
        )

    def _request(self, user, path="/dashboard/?member_months=12"):
        factory = RequestFactory()
        request = factory.get(path)
        request.user = user
        request.session = {"current_church_id": str(self.church.id)}
        return request

    def test_parse_trend_months(self):
        self.assertEqual(parse_trend_months("12"), 12)
        self.assertEqual(parse_trend_months("6"), 6)
        self.assertEqual(parse_trend_months("99"), 12)
        self.assertEqual(parse_trend_months("nope"), 12)

    def test_kpis_and_demographics(self):
        snap = build_member_dashboard(self._request(self.secretary), church_ids=[self.church.id])
        self.assertIsNotNone(snap)
        self.assertEqual(snap["kpis"]["total"], 4)
        self.assertEqual(snap["kpis"]["active"], 2)
        self.assertEqual(snap["kpis"]["inactive"], 1)
        self.assertEqual(snap["kpis"]["left"], 1)
        self.assertEqual(snap["kpis"]["baptized"], 1)
        self.assertEqual(snap["kpis"]["unbaptized"], 3)
        self.assertEqual(snap["kpis"]["new_this_month"], 1)
        gender = {row["code"]: row["count"] for row in snap["gender_rows"]}
        self.assertEqual(gender[Gender.FEMALE], 2)
        self.assertEqual(gender[Gender.MALE], 1)
        self.assertEqual(gender["unknown"], 1)
        self.assertEqual(snap["age_missing_dob"], 2)
        quality = {row["key"]: row["count"] for row in snap["quality"]}
        self.assertGreaterEqual(quality["phone"], 1)
        self.assertGreaterEqual(quality["email"], 1)
        self.assertGreaterEqual(quality["dob"], 1)
        self.assertGreaterEqual(quality["gender"], 1)
        self.assertGreaterEqual(quality["joined"], 1)

    def test_does_not_count_other_church(self):
        snap = build_member_dashboard(self._request(self.secretary), church_ids=[self.church.id])
        names = [item["title"] for item in snap["activity"]]
        self.assertFalse(any("Eve" in n for n in names))

    def test_trend_empty_months_and_joins(self):
        snap = build_member_dashboard(
            self._request(self.secretary, "/dashboard/?member_months=6"),
            church_ids=[self.church.id],
        )
        self.assertEqual(snap["trend_months"], 6)
        import json

        labels = json.loads(snap["trend"]["labels_json"])
        news = json.loads(snap["trend"]["new_json"])
        self.assertEqual(len(labels), 6)
        self.assertEqual(len(news), 6)
        self.assertEqual(sum(news), 1)

    def test_treasury_without_member_permission(self):
        snap = build_member_dashboard(self._request(self.treasury), church_ids=[self.church.id])
        self.assertIsNone(snap)

    def test_get_member_summary_legacy_keys(self):
        payload = get_member_summary(self._request(self.secretary), church_ids=[self.church.id])
        self.assertIn("member_count", payload)
        self.assertIn("member_dashboard", payload)
        self.assertEqual(payload["member_count"], 2)

    def test_home_shows_summary_for_secretary(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from sitecontrol.models import SiteSettings

        SiteSettings.objects.update_or_create(
            singleton_id=1, defaults={"mfa_required_for_privileged": False}
        )
        enable_mfa_for_user(self.secretary, generate_totp_secret(), [])
        client = Client()
        client.login(username="md_sec", password="pass12345")
        session = client.session
        session[SESSION_MFA_VERIFIED] = True
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member Summary")
        self.assertContains(response, "Membership trend")
        self.assertNotContains(response, "Statement of position")
        self.assertNotContains(response, "transactions ledger")
        self.assertNotContains(response, "System command center")

    def test_home_hides_summary_for_treasury(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from sitecontrol.models import SiteSettings

        SiteSettings.objects.update_or_create(
            singleton_id=1, defaults={"mfa_required_for_privileged": False}
        )
        enable_mfa_for_user(self.treasury, generate_totp_secret(), [])
        client = Client()
        client.login(username="md_treas", password="pass12345")
        session = client.session
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        response = client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Member Summary")

    def test_home_requires_login(self):
        response = Client().get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
