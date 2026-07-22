"""Tests for meetings workflow and views."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.client import ContextList
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from meetings.models import Meeting, MeetingStatus, MeetingType, MinutesStatus
from organization.models import Church, Conference, District, Zone

User = get_user_model()


class MeetingsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Python 3.14 + Django test client: Context.__copy__ crashes in
        # store_rendered_templates. Skip the copy; status/content asserts still work.

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
        conf = Conference.objects.create(code="M1", name="M Conf")
        zone = Zone.objects.create(conference=conf, code="M1", name="M Zone")
        dist = District.objects.create(zone=zone, code="M1", name="M Dist")
        cls.church = Church.objects.create(district=dist, code="M1", name="M Church")
        from permissions.services import ensure_permission_matrix
        ensure_permission_matrix()

    def setUp(self):
        self.client = Client()
        self.secretary = User.objects.create_user(
            username="sec_m", password="pass12345", role=UserRole.SECRETARY, church=self.church
        )
        self.pastor = User.objects.create_user(
            username="pastor_m", password="pass12345", role=UserRole.LOCAL_PASTOR, church=self.church
        )

    def _meeting(self, **kwargs):
        defaults = {
            "church": self.church,
            "title": "Board Meeting",
            "meeting_type": MeetingType.BOARD,
            "agenda": "Budget review",
            "location": "Main hall",
            "scheduled_at": timezone.now(),
            "status": MeetingStatus.SCHEDULED,
            "created_by": self.secretary,
        }
        defaults.update(kwargs)
        return Meeting.objects.create(**defaults)

    def test_meeting_list_with_search(self):
        self._meeting(title="Finance Board")
        self.client.login(username="sec_m", password="pass12345")
        response = self.client.get(reverse("meetings:list"), {"q": "Finance"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finance Board")

    def test_create_board_meeting(self):
        self.client.login(username="sec_m", password="pass12345")
        response = self.client.post(reverse("meetings:create"), {
            "title": "Board Meeting",
            "meeting_type": MeetingType.BOARD,
            "agenda": "Budget review",
            "location": "Main hall",
            "scheduled_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "status": MeetingStatus.SCHEDULED,
        })
        self.assertEqual(response.status_code, 302)
        meeting = Meeting.objects.get(title="Board Meeting")
        self.assertEqual(meeting.meeting_type, MeetingType.BOARD)

    def test_minutes_maker_checker_flow(self):
        meeting = self._meeting(status=MeetingStatus.HELD)
        self.client.login(username="sec_m", password="pass12345")
        response = self.client.post(reverse("meetings:action", args=[meeting.pk]), {
            "action": "submit_minutes",
            "status": MeetingStatus.HELD,
            "minutes_deliberations": "Budget approved for Q3.",
        })
        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.minutes_status, MinutesStatus.PENDING_APPROVAL)
        self.assertEqual(meeting.minutes_submitted_by, self.secretary)

        self.client.login(username="pastor_m", password="pass12345")
        response = self.client.post(reverse("meetings:action", args=[meeting.pk]), {
            "action": "approve_minutes",
        })
        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.minutes_status, MinutesStatus.APPROVED)
        self.assertTrue(meeting.minutes_locked)
        self.assertEqual(meeting.minutes_approved_by, self.pastor)

    def test_submitter_cannot_approve_own_minutes(self):
        meeting = self._meeting(
            status=MeetingStatus.HELD,
            minutes_status=MinutesStatus.PENDING_APPROVAL,
            minutes_submitted_by=self.pastor,
            minutes_deliberations="Notes",
        )
        self.client.login(username="pastor_m", password="pass12345")
        response = self.client.post(reverse("meetings:action", args=[meeting.pk]), {
            "action": "approve_minutes",
        })
        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.minutes_status, MinutesStatus.PENDING_APPROVAL)

    def test_pending_minutes_queue(self):
        self._meeting(
            status=MeetingStatus.HELD,
            minutes_status=MinutesStatus.PENDING_APPROVAL,
            minutes_submitted_by=self.secretary,
            minutes_submitted_at=timezone.now(),
            minutes_deliberations="Ready",
        )
        self.client.login(username="pastor_m", password="pass12345")
        response = self.client.get(reverse("meetings:pending_minutes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Board Meeting")

    def test_meeting_detail_shows_structured_minutes(self):
        meeting = self._meeting(
            minutes_opening="Called to order.",
            minutes_deliberations="Reports received.",
            minutes_status=MinutesStatus.APPROVED,
            minutes_locked=True,
        )
        self.client.login(username="sec_m", password="pass12345")
        response = self.client.get(reverse("meetings:detail", args=[meeting.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Called to order.")
        self.assertContains(response, "Reports received.")
