"""Tests for members app — directory, records, transfers, departments, families."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.models import (
    Department,
    Family,
    Gender,
    LeadershipRole,
    Member,
    MemberAuditLog,
    MembershipStatus,
    MemberTransfer,
    Record,
    RecordType,
    TransferStatus,
)
from members.services import (
    complete_transfer,
    create_member,
    reject_transfer,
    request_transfer,
    user_can_view_transfer,
)
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix

User = get_user_model()


class MembersTestMixin:
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.conference = Conference.objects.create(code="T1", name="Test Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z1", name="Test Zone")
        cls.district = District.objects.create(zone=cls.zone, code="D1", name="Test District")
        cls.church = Church.objects.create(district=cls.district, code="C1", name="Test Church")
        cls.other_church = Church.objects.create(
            district=cls.district, code="C2", name="Other Church"
        )
        cls.department = Department.objects.create(church=cls.church, name="Youth")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Jane",
            last_name="Doe",
            gender=Gender.FEMALE,
            department=cls.department,
            phone="0244111000",
        )


class ServiceTests(MembersTestMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.other_church,
        )
        self.source_user = User.objects.create_user(
            username="sec_src",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )

    def test_request_and_complete_transfer(self):
        LeadershipRole.objects.create(
            church=self.church,
            member=self.member,
            title="Youth Leader",
            start_date=date.today(),
            is_active=True,
        )
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.source_user,
            reason="Relocation",
        )
        self.assertEqual(transfer.status, TransferStatus.PENDING)
        complete_transfer(transfer, self.user)
        self.member.refresh_from_db()
        self.assertEqual(self.member.church, self.other_church)
        self.assertIsNone(self.member.department_id)
        self.assertEqual(self.member.membership_status, MembershipStatus.ACTIVE)
        self.assertFalse(
            LeadershipRole.objects.filter(member=self.member, is_active=True).exists()
        )
        self.assertEqual(
            Record.objects.filter(member=self.member, record_type=RecordType.TRANSFER).count(),
            2,
        )
        self.assertTrue(
            MemberAuditLog.objects.filter(action="TRANSFER_COMPLETE", member=self.member).exists()
        )

    def test_complete_transfer_requires_destination_permission(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.source_user,
        )
        with self.assertRaises(PermissionDenied):
            complete_transfer(transfer, self.source_user)

    def test_create_member_rejects_duplicate_phone(self):
        with self.assertRaises(ValidationError):
            create_member(
                self.church,
                performed_by=self.source_user,
                first_name="John",
                last_name="Smith",
                gender=Gender.MALE,
                phone="0244111000",
            )


class ViewTests(MembersTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.secretary = User.objects.create_user(
            username="secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.member_user = User.objects.create_user(
            username="member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.other_secretary = User.objects.create_user(
            username="other_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.other_church,
        )

    def test_list_accessible_to_member_with_view_permission(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane")

    def test_list_with_filters(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:list"), {"q": "Jane"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane")

    def test_directory_export_csv(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:list"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_member_detail(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:detail", kwargs={"member_id": self.member.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Youth")

    def test_member_cannot_add(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:add"))
        self.assertEqual(response.status_code, 403)

    def test_baptism_register_viewable_by_member(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:baptism_register"))
        self.assertEqual(response.status_code, 200)

    def test_add_department(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:department_add"),
            {"name": "Choir", "description": "Music ministry"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Department.objects.filter(name="Choir", church=self.church).exists())

    def test_add_record(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:record_add"),
            {
                "member": str(self.member.pk),
                "record_type": RecordType.BAPTISM,
                "title": "Water Baptism",
                "description": "Baptized at main service",
                "event_date": "2024-01-15",
                "place": "Main Sanctuary",
                "officiant": "Pastor",
                "certificate_number": "BAP-001",
                "status": "Active",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Record.objects.filter(title="Water Baptism").exists())
        self.member.refresh_from_db()
        self.assertEqual(self.member.baptism_date, date(2024, 1, 15))

    def test_transfer_create(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:transfer_create"),
            {
                "member": str(self.member.pk),
                "to_church": str(self.other_church.pk),
                "transfer_date": date.today().isoformat(),
                "reason": "Moving",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(MemberTransfer.objects.filter(member=self.member).exists())

    def test_transfer_detail_idor_denied(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.secretary,
        )
        outsider = User.objects.create_user(
            username="outsider",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=Church.objects.create(
                district=self.district, code="C3", name="Third Church"
            ),
        )
        self.client.login(username="outsider", password="pass12345")
        response = self.client.get(reverse("members:transfer_detail", kwargs={"pk": transfer.pk}))
        self.assertEqual(response.status_code, 403)

    def test_transfer_detail_accessible_without_active_church_session(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.secretary,
        )
        self.assertTrue(user_can_view_transfer(self.secretary, transfer))
        self.client.login(username="secretary", password="pass12345")
        session = self.client.session
        session.pop("current_church_id", None)
        session.save()
        response = self.client.get(reverse("members:transfer_detail", kwargs={"pk": transfer.pk}))
        self.assertEqual(response.status_code, 200)

    def test_add_family(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:family_add"),
            {
                "name": "Doe Family",
                "head": str(self.member.pk),
                "address": "123 Main",
                "phone": "0244123456",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Family.objects.filter(name="Doe Family").exists())

    def test_duplicate_phone_rejected_on_add(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:add"),
            {
                "first_name": "Dup",
                "last_name": "Phone",
                "gender": Gender.MALE,
                "phone": "0244111000",
                "membership_status": MembershipStatus.ACTIVE,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(first_name="Dup").exists())
