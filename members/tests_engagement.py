"""Attendance-first engagement review."""

from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from meetings.models import AttendanceEvent, AttendanceRecord, Meeting, MeetingAttendance
from members.engagement_services import (
    apply_engagement_candidate,
    auto_apply_missing_for_church,
    dismiss_engagement_candidate,
    evaluate_church_engagement,
    get_or_create_engagement_policy,
)
from members.models import Member, MemberAuditLog, MembershipStatus
from members.tests import MembersTestMixin, User
from permissions.services import ensure_permission_matrix
from transactions.models import Transaction


AS_OF = date(2026, 11, 10)


def _dt(day):
    naive = datetime.combine(day, time(10, 0))
    return timezone.make_aware(naive)


class EngagementTests(MembersTestMixin, TestCase):
    def setUp(self):
        ensure_permission_matrix()
        self.clerk = User.objects.create_user(
            username="eng_clerk",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.regular = Member.objects.create(
            church=self.church,
            first_name="Rina",
            last_name="Regular",
            gender="Female",
            date_joined=AS_OF - timedelta(days=200),
        )
        self.stale = Member.objects.create(
            church=self.church,
            first_name="Sam",
            last_name="Stale",
            gender="Male",
            date_joined=AS_OF - timedelta(days=200),
        )
        self.transferred = Member.objects.create(
            church=self.church,
            first_name="Ted",
            last_name="Transferred",
            gender="Male",
            membership_status=MembershipStatus.TRANSFERRED,
            date_joined=AS_OF - timedelta(days=200),
        )

    def _event(self, day, member, present=True):
        event = AttendanceEvent.objects.create(
            church=self.church,
            title=f"Worship {day}",
            event_date=day,
        )
        AttendanceRecord.objects.create(event=event, member=member, is_present=present)
        return event

    def _enough_roll(self):
        self._event(AS_OF - timedelta(days=7), self.regular)
        self._event(AS_OF, self.regular)
        self._event(AS_OF - timedelta(days=70), self.stale)

    def test_thin_attendance_holds_missing(self):
        self._event(AS_OF - timedelta(days=70), self.stale)
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        self.assertTrue(review.attendance_too_thin)
        ids = {row.member.pk for row in review.candidates}
        self.assertNotIn(self.stale.pk, ids)

    def test_active_becomes_missing_after_window(self):
        self._enough_roll()
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        by_id = {row.member.pk: row for row in review.candidates}
        self.assertIn(self.stale.pk, by_id)
        self.assertEqual(by_id[self.stale.pk].suggested_status, MembershipStatus.MISSING)
        self.assertNotIn(self.transferred.pk, by_id)
        self.assertNotIn(self.regular.pk, by_id)

    def test_new_member_grace(self):
        self._enough_roll()
        newbie = Member.objects.create(
            church=self.church,
            first_name="New",
            last_name="Join",
            gender="Female",
            date_joined=AS_OF - timedelta(days=10),
        )
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        ids = {row.member.pk for row in review.candidates}
        self.assertNotIn(newbie.pk, ids)

    def test_giving_protects_missing(self):
        self._enough_roll()
        Transaction.objects.create(
            church=self.church,
            member=self.stale,
            transaction_type="RECEIPT",
            approval_status="APPROVED",
            date=AS_OF - timedelta(days=3),
            description="Tithe",
        )
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        ids = {row.member.pk for row in review.candidates}
        self.assertNotIn(self.stale.pk, ids)

    def test_apply_missing_audits_status(self):
        self._enough_roll()
        apply_engagement_candidate(
            church=self.church,
            member=self.stale,
            suggested_status=MembershipStatus.MISSING,
            performed_by=self.clerk,
        )
        self.stale.refresh_from_db()
        self.assertEqual(self.stale.membership_status, MembershipStatus.MISSING)
        self.assertFalse(self.stale.is_active)
        self.assertTrue(
            MemberAuditLog.objects.filter(
                member=self.stale, action="STATUS"
            ).exists()
        )

    def test_dismiss_hides_until_last_seen_changes(self):
        self._enough_roll()
        dismiss_engagement_candidate(
            church=self.church, member=self.stale, performed_by=self.clerk
        )
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        ids = {row.member.pk for row in review.candidates}
        self.assertNotIn(self.stale.pk, ids)
        self.stale.membership_status = MembershipStatus.MISSING
        self.stale.save()
        self._event(AS_OF, self.stale)
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        by_id = {row.member.pk: row for row in review.candidates}
        self.assertEqual(by_id[self.stale.pk].suggested_status, MembershipStatus.ACTIVE)

    def test_present_restores_missing_to_active(self):
        self._enough_roll()
        self.stale.membership_status = MembershipStatus.MISSING
        self.stale.save()
        self._event(AS_OF, self.stale)
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        by_id = {row.member.pk: row for row in review.candidates}
        self.assertEqual(by_id[self.stale.pk].suggested_status, MembershipStatus.ACTIVE)

    def test_auto_apply_missing_not_inactive(self):
        self._enough_roll()
        self.stale.membership_status = MembershipStatus.MISSING
        self.stale.save()
        self.stale.date_joined = AS_OF - timedelta(days=400)
        self.stale.save(update_fields=["date_joined"])
        AttendanceRecord.objects.filter(member=self.stale).delete()
        policy = get_or_create_engagement_policy(self.church)
        policy.auto_apply_missing = True
        policy.save()
        applied = auto_apply_missing_for_church(self.church, as_of=AS_OF)
        self.stale.refresh_from_db()
        self.assertEqual(applied, 0)
        self.assertEqual(self.stale.membership_status, MembershipStatus.MISSING)

        self.stale.membership_status = MembershipStatus.ACTIVE
        self.stale.save()
        self._event(AS_OF - timedelta(days=70), self.stale)
        applied = auto_apply_missing_for_church(self.church, as_of=AS_OF)
        self.stale.refresh_from_db()
        self.assertGreaterEqual(applied, 1)
        self.assertEqual(self.stale.membership_status, MembershipStatus.MISSING)

    def test_meeting_attendance_counts_as_last_seen(self):
        self._event(AS_OF - timedelta(days=7), self.regular)
        meeting = Meeting.objects.create(
            church=self.church,
            title="Prayer",
            scheduled_at=_dt(AS_OF),
        )
        MeetingAttendance.objects.create(meeting=meeting, member=self.regular, is_present=True)
        self.stale.date_joined = AS_OF - timedelta(days=200)
        self.stale.save(update_fields=["date_joined"])
        review = evaluate_church_engagement(self.church, as_of=AS_OF)
        self.assertFalse(review.attendance_too_thin)

    def test_review_page_and_other_church(self):
        self._enough_roll()
        self.client.force_login(self.clerk)
        url = reverse("members:engagement_review")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sam Stale")
        other = User.objects.create_user(
            username="other_eng",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.other_church,
        )
        self.client.force_login(other)
        response = self.client.post(
            url,
            {"action": "apply", "member_ids": [str(self.stale.pk)], f"suggested_{self.stale.pk}": "Missing"},
        )
        self.assertEqual(response.status_code, 404)
        self.stale.refresh_from_db()
        self.assertEqual(self.stale.membership_status, MembershipStatus.ACTIVE)
