"""Tests for members app — directory, records, transfers, departments, families."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

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
    cancel_transfer,
    complete_transfer,
    create_member,
    reject_transfer,
    request_transfer,
    user_can_view_transfer,
)
from organization.models import Church, Conference, District, Zone
from sitecontrol.models import Denomination
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

    def test_complete_transfer_blocked_when_phone_taken_at_destination(self):
        Member.objects.create(
            church=self.other_church,
            first_name="Pat",
            last_name="Taken",
            gender=Gender.FEMALE,
            phone=self.member.phone,
        )
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.source_user,
        )
        with self.assertRaises(ValueError):
            complete_transfer(transfer, self.user)

    def test_requester_cannot_complete_own_transfer(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.user,
        )
        with self.assertRaises(PermissionDenied):
            complete_transfer(transfer, self.user)

    def test_reject_transfer_requires_notes(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.source_user,
        )
        with self.assertRaises(ValueError):
            reject_transfer(transfer, self.user, notes="")
        reject_transfer(transfer, self.user, notes="Not in good standing")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferStatus.REJECTED)

    def test_sending_church_can_cancel_pending_transfer(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.source_user,
        )
        cancel_transfer(transfer, self.source_user, notes="Member stayed")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TransferStatus.CANCELLED)

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
        self.assertContains(response, 'href="tel:0244111000"')
        self.assertContains(response, ">Call</a>")

    def test_add_member_uses_compact_field_grid(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "col-6 col-md-4")
        self.assertContains(response, "col-md-8")

    def test_record_add_uses_short_purpose_columns(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:record_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "col-6 col-md-3")
        self.assertContains(response, 'name="certificate_number"')

    def test_member_cannot_add(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:add"))
        self.assertEqual(response.status_code, 403)

    def test_baptism_register_viewable_by_member(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:baptism_register"))
        self.assertEqual(response.status_code, 200)

    def test_baptism_register_add_cta_for_secretary(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:baptism_register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add baptism")
        self.assertContains(response, "record_type=Baptism")

    def test_record_add_shows_member_select(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:record_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="member"')
        self.assertNotContains(response, 'type="hidden" name="member"')

    def test_baptism_add_locks_type_and_shows_member_select(self):
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(
            reverse("members:record_add"), {"record_type": RecordType.BAPTISM}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add baptism")
        self.assertContains(response, 'name="member"')
        self.assertContains(response, 'type="hidden" name="record_type"')

    def test_member_cannot_add_baptism_record(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(
            reverse("members:record_add"), {"record_type": RecordType.BAPTISM}
        )
        self.assertEqual(response.status_code, 403)

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
                "dest_conference": str(self.conference.pk),
                "dest_district": str(self.district.pk),
                "to_church": str(self.other_church.pk),
                "transfer_date": date.today().isoformat(),
                "reason": "Moving",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(MemberTransfer.objects.filter(member=self.member).exists())

    def test_transfer_form_cascades_conference_district_church(self):
        self.client.login(username="secretary", password="pass12345")
        page = self.client.get(reverse("members:transfer_create"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="dest_conference"')
        self.assertContains(page, 'name="dest_district"')
        self.assertContains(page, 'data-dest-level="church"')

        conferences = self.client.get(reverse("members:transfer_destinations"))
        self.assertEqual(conferences.status_code, 200)
        conf_ids = [row["id"] for row in conferences.json()["conferences"]]
        self.assertIn(str(self.conference.pk), conf_ids)

        districts = self.client.get(
            reverse("members:transfer_destinations"),
            {"conference": str(self.conference.pk)},
        )
        self.assertEqual(districts.status_code, 200)
        dist_ids = [row["id"] for row in districts.json()["districts"]]
        self.assertIn(str(self.district.pk), dist_ids)

        churches = self.client.get(
            reverse("members:transfer_destinations"),
            {
                "conference": str(self.conference.pk),
                "district": str(self.district.pk),
            },
        )
        self.assertEqual(churches.status_code, 200)
        church_ids = [row["id"] for row in churches.json()["churches"]]
        self.assertIn(str(self.other_church.pk), church_ids)
        self.assertNotIn(str(self.church.pk), church_ids)

    def test_transfer_create_rejects_church_outside_selected_district(self):
        other_district = District.objects.create(
            zone=self.zone, code="D9", name="Other District"
        )
        far_church = Church.objects.create(
            district=other_district, code="C9", name="Far Church"
        )
        self.client.login(username="secretary", password="pass12345")
        response = self.client.post(
            reverse("members:transfer_create"),
            {
                "member": str(self.member.pk),
                "dest_conference": str(self.conference.pk),
                "dest_district": str(self.district.pk),
                "to_church": str(far_church.pk),
                "transfer_date": date.today().isoformat(),
                "reason": "Wrong district",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MemberTransfer.objects.filter(member=self.member).exists())

    def test_transfer_destinations_include_other_conference_same_denomination(self):
        denom = Denomination.objects.create(code="xfer-sda", name="Transfer SDA")
        self.conference.denomination = denom
        self.conference.save(update_fields=["denomination"])
        other_conf = Conference.objects.create(
            code="T2", name="Second Conference", denomination=denom
        )
        other_zone = Zone.objects.create(
            conference=other_conf, code="Z2", name="Second Zone"
        )
        other_district = District.objects.create(
            zone=other_zone, code="D2", name="Second District"
        )
        dest_church = Church.objects.create(
            district=other_district, code="C3", name="Second Church"
        )
        self.client.login(username="secretary", password="pass12345")
        conferences = self.client.get(reverse("members:transfer_destinations"))
        conf_ids = [row["id"] for row in conferences.json()["conferences"]]
        self.assertIn(str(other_conf.pk), conf_ids)
        districts = self.client.get(
            reverse("members:transfer_destinations"),
            {"conference": str(other_conf.pk)},
        )
        dist_ids = [row["id"] for row in districts.json()["districts"]]
        self.assertEqual(dist_ids, [str(other_district.pk)])
        churches = self.client.get(
            reverse("members:transfer_destinations"),
            {
                "conference": str(other_conf.pk),
                "district": str(other_district.pk),
            },
        )
        church_ids = [row["id"] for row in churches.json()["churches"]]
        self.assertEqual(church_ids, [str(dest_church.pk)])

    def test_transfer_list_filters_outgoing_pending(self):
        request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.secretary,
        )
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(
            reverse("members:transfer_list"),
            {"direction": "out", "status": "Pending"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane")
        self.assertContains(response, "Incoming (to this church)")

    def test_transfer_letter_and_pending_profile_badge(self):
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.secretary,
        )
        self.client.login(username="secretary", password="pass12345")
        letter = self.client.get(reverse("members:transfer_letter", kwargs={"pk": transfer.pk}))
        self.assertEqual(letter.status_code, 200)
        self.assertContains(letter, "Letter of transfer")
        detail = self.client.get(
            reverse("members:detail", kwargs={"member_id": self.member.pk})
        )
        self.assertContains(detail, "Transfer pending")
        self.assertContains(detail, "Pending transfer")
        add = self.client.get(reverse("members:transfer_create"), {"member": str(self.member.pk)})
        self.assertEqual(add.status_code, 302)

    def test_member_cannot_load_transfer_destinations(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:transfer_destinations"))
        self.assertEqual(response.status_code, 403)

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

    def test_export_denied_when_override_blocks_export(self):
        from permissions.models import Permission
        from permissions.services import create_override

        perm = Permission.objects.get(codename="export_members")
        create_override(self.secretary, perm, granted=False, reason="Test deny export")
        self.client.login(username="secretary", password="pass12345")
        response = self.client.get(reverse("members:list"), {"export": "csv"})
        self.assertEqual(response.status_code, 403)

    def test_baptism_export_requires_export_permission(self):
        self.client.login(username="member", password="pass12345")
        response = self.client.get(reverse("members:baptism_register"), {"export": "csv"})
        self.assertEqual(response.status_code, 403)

    def test_department_edit_and_delete(self):
        self.client.login(username="secretary", password="pass12345")
        dept = Department.objects.create(church=self.church, name="Ushering")
        response = self.client.post(
            reverse("members:department_edit", kwargs={"pk": dept.pk}),
            {"name": "Usher Board", "description": "Updated"},
        )
        self.assertEqual(response.status_code, 302)
        dept.refresh_from_db()
        self.assertEqual(dept.name, "Usher Board")
        response = self.client.post(
            reverse("members:department_delete", kwargs={"pk": dept.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Department.objects.filter(pk=dept.pk).exists())

    def test_stale_visitor_follow_up_reminder(self):
        from datetime import timedelta

        from dashboard.models import Notification
        from members.models import Visitor
        from members.notifications import remind_stale_visitor_follow_ups

        Visitor.objects.create(
            church=self.church,
            first_name="Sam",
            last_name="Guest",
            visit_date=timezone.localdate() - timedelta(days=20),
        )
        result = remind_stale_visitor_follow_ups(stale_days=14)
        self.assertGreaterEqual(result["churches"], 1)
        self.assertTrue(
            Notification.objects.filter(
                event_key__startswith=f"visitors.stale.{self.church.pk}."
            ).exists()
        )
