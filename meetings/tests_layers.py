"""Characterization tests for meetings selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from meetings import repositories as repo
from meetings import selectors
from meetings.models import (
    AttendanceEvent,
    Meeting,
    MeetingAttachment,
    MeetingAttendance,
    MeetingDecision,
    MeetingType,
)
from meetings.services import record_meeting_attendance
from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix

User = get_user_model()


class MeetingsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        conf_a = Conference.objects.create(code="MLCA", name="Meet Layer Conf A")
        zone_a = Zone.objects.create(conference=conf_a, code="MLZA", name="Meet Zone A")
        dist_a = District.objects.create(zone=zone_a, code="MLDA", name="Meet Dist A")
        cls.church_a = Church.objects.create(
            district=dist_a, code="MLCHA", name="Meet Church A"
        )

        conf_b = Conference.objects.create(code="MLCB", name="Meet Layer Conf B")
        zone_b = Zone.objects.create(conference=conf_b, code="MLZB", name="Meet Zone B")
        dist_b = District.objects.create(zone=zone_b, code="MLDB", name="Meet Dist B")
        cls.church_b = Church.objects.create(
            district=dist_b, code="MLCHB", name="Meet Church B"
        )

        cls.member_a = Member.objects.create(
            church=cls.church_a,
            first_name="Alpha",
            last_name="Member",
            gender="Male",
            is_active=True,
        )
        cls.member_b = Member.objects.create(
            church=cls.church_b,
            first_name="Beta",
            last_name="Member",
            gender="Female",
            is_active=True,
        )

        cls.meeting_a = Meeting.objects.create(
            church=cls.church_a,
            title="Layer Board A",
            meeting_type=MeetingType.BOARD,
            scheduled_at=timezone.now(),
        )
        cls.meeting_b = Meeting.objects.create(
            church=cls.church_b,
            title="Layer Board B",
            meeting_type=MeetingType.BOARD,
            scheduled_at=timezone.now(),
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.user_a = User.objects.create_user(
            username="meet_layer_a",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church_a,
        )
        self.user_b = User.objects.create_user(
            username="meet_layer_b",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church_b,
        )

    def _request(self, user):
        request = self.factory.get("/meetings/")
        request.user = user
        return request

    def test_selector_meeting_reads_scoped(self):
        qs_a = selectors.meetings_for_request(self._request(self.user_a))
        ids = set(qs_a.values_list("pk", flat=True))
        self.assertIn(self.meeting_a.pk, ids)
        self.assertNotIn(self.meeting_b.pk, ids)

    def test_selector_filter_meetings(self):
        qs = selectors.filter_meetings_queryset(
            Meeting.objects.all(),
            {"q": "Layer Board A", "meeting_type": "", "status": "", "minutes_status": ""},
        )
        self.assertEqual(list(qs.values_list("pk", flat=True)), [self.meeting_a.pk])

    def test_cross_church_access_denied(self):
        with self.assertRaises(Http404):
            selectors.get_meeting_or_404(self._request(self.user_a), self.meeting_b.pk)

    def test_attendance_isolation_on_record(self):
        # Foreign church member id must not create a row for church A meeting.
        count = record_meeting_attendance(
            self.meeting_a,
            [self.member_a.pk, self.member_b.pk],
            [self.member_a.pk],
        )
        self.assertEqual(count, 1)
        self.assertTrue(
            MeetingAttendance.objects.filter(
                meeting=self.meeting_a, member=self.member_a
            ).exists()
        )
        self.assertFalse(
            MeetingAttendance.objects.filter(
                meeting=self.meeting_a, member=self.member_b
            ).exists()
        )

    def test_repository_save_meeting_and_decision(self):
        meeting = Meeting(
            church=self.church_a,
            title="Repo Meeting",
            meeting_type=MeetingType.GENERAL,
            scheduled_at=timezone.now(),
        )
        repo.save_meeting(meeting)
        self.assertTrue(Meeting.objects.filter(pk=meeting.pk).exists())

        decision = MeetingDecision(
            meeting=meeting,
            decision_text="Approve budget",
            vote_result="Carried",
        )
        repo.save_decision(decision)
        self.assertTrue(
            MeetingDecision.objects.filter(
                meeting=meeting, decision_text="Approve budget"
            ).exists()
        )

    def test_repository_attachment_handling(self):
        upload = SimpleUploadedFile(
            "notes.txt", b"layer notes", content_type="text/plain"
        )
        attachment = MeetingAttachment(
            meeting=self.meeting_a,
            label="Notes",
            file=upload,
            uploaded_by=self.user_a,
        )
        repo.save_meeting_attachment(attachment)
        pk = attachment.pk
        self.assertTrue(MeetingAttachment.objects.filter(pk=pk).exists())
        found = selectors.get_meeting_attachment_or_404(
            meeting=self.meeting_a, pk=pk
        )
        self.assertEqual(found.label, "Notes")
        repo.delete_meeting_attachment(found)
        self.assertFalse(MeetingAttachment.objects.filter(pk=pk).exists())

    def test_attendance_update_behavior_preserves_rows(self):
        record_meeting_attendance(
            self.meeting_a, [self.member_a.pk], [self.member_a.pk]
        )
        first_pk = MeetingAttendance.objects.get(
            meeting=self.meeting_a, member=self.member_a
        ).pk
        record_meeting_attendance(
            self.meeting_a, [self.member_a.pk], [self.member_a.pk]
        )
        second_pk = MeetingAttendance.objects.get(
            meeting=self.meeting_a, member=self.member_a
        ).pk
        self.assertEqual(first_pk, second_pk)

    def test_selector_attendance_event_reads(self):
        event = AttendanceEvent.objects.create(
            church=self.church_a,
            title="Worship",
            event_date=timezone.localdate(),
        )
        AttendanceEvent.objects.create(
            church=self.church_b,
            title="Other Worship",
            event_date=timezone.localdate(),
        )
        events = selectors.attendance_events_for_request(self._request(self.user_a))
        ids = set(events.values_list("pk", flat=True))
        self.assertIn(event.pk, ids)
        self.assertEqual(len(ids), 1)
        with self.assertRaises(Http404):
            selectors.get_attendance_event_or_404(
                self._request(self.user_b), event.pk
            )
