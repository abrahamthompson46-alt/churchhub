"""Attendance re-record sync (no full roll wipe)."""

from django.test import TestCase
from django.utils import timezone

from meetings.models import AttendanceEvent, Meeting, MeetingAttendance
from meetings.services import record_event_attendance, record_meeting_attendance
from members.models import Member
from organization.models import Church, Conference, District, Zone


class AttendanceSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Att Conf", code="ATTC")
        zone = Zone.objects.create(conference=conf, name="Att Z", code="ATTZ")
        dist = District.objects.create(zone=zone, name="Att D", code="ATTD")
        cls.church = Church.objects.create(district=dist, name="Att Church", code="ATTCH")
        cls.m1 = Member.objects.create(
            church=cls.church, first_name="One", last_name="Member", gender="Male"
        )
        cls.m2 = Member.objects.create(
            church=cls.church, first_name="Two", last_name="Member", gender="Female"
        )
        cls.meeting = Meeting.objects.create(
            church=cls.church,
            title="Board",
            scheduled_at=timezone.now(),
        )

    def test_meeting_attendance_preserves_row_on_rerecord(self):
        record_meeting_attendance(self.meeting, [self.m1.pk, self.m2.pk], [self.m1.pk])
        first_ids = list(
            MeetingAttendance.objects.filter(meeting=self.meeting).values_list("pk", flat=True)
        )
        record_meeting_attendance(self.meeting, [self.m1.pk, self.m2.pk], [self.m1.pk, self.m2.pk])
        second_ids = list(
            MeetingAttendance.objects.filter(meeting=self.meeting).values_list("pk", flat=True)
        )
        self.assertEqual(set(first_ids), set(second_ids))
        self.assertEqual(
            MeetingAttendance.objects.get(meeting=self.meeting, member=self.m2).is_present,
            True,
        )

    def test_event_attendance_drops_removed_members_only(self):
        event = AttendanceEvent.objects.create(
            church=self.church,
            title="Worship",
            event_date=timezone.localdate(),
        )
        record_event_attendance(event, [self.m1.pk, self.m2.pk], [self.m1.pk])
        self.assertEqual(event.records.count(), 2)
        record_event_attendance(event, [self.m1.pk], [self.m1.pk])
        self.assertEqual(event.records.count(), 1)
        self.assertTrue(event.records.filter(member=self.m1).exists())
