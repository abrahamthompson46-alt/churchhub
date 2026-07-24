"""Tests for announcements services and views."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test.client import ContextList
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from announcements.models import Announcement, AnnouncementAuditLog
from announcements.services import (
    approve_announcement,
    archive_announcement,
    can_approve_announcement,
    create_announcement,
    pending_for_user,
    reject_announcement,
    visible_announcements,
)
from dashboard.models import Notification
from organization.models import Church, Conference, District, Zone

User = get_user_model()


class AnnouncementTestMixin:
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
        cls.conference = Conference.objects.create(code="T1", name="Test Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z1", name="Test Zone")
        cls.district = District.objects.create(zone=cls.zone, code="D1", name="Test District")
        cls.church = Church.objects.create(district=cls.district, code="C1", name="Test Church")
        cls.other_church = Church.objects.create(district=cls.district, code="C2", name="Other Church")
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()


class ServiceTests(AnnouncementTestMixin, TestCase):
    def setUp(self):
        self.secretary = User.objects.create_user(
            username="sec1",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pastor1",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.admin = User.objects.create_user(
            username="admin1",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
        )

    def _pending(self, **kwargs):
        defaults = {
            "title": "Test Announcement",
            "content": "Body text",
            "visibility": "church",
            "church": self.church,
            "created_by": self.secretary,
            "is_approved": False,
            "is_rejected": False,
            "status": Announcement.STATUS_PENDING,
        }
        defaults.update(kwargs)
        return Announcement.objects.create(**defaults)

    def test_local_pastor_can_approve_church_announcement(self):
        ann = self._pending()
        self.assertTrue(can_approve_announcement(self.pastor, ann))

    def test_local_pastor_cannot_approve_other_church(self):
        ann = self._pending(church=self.other_church)
        self.assertFalse(can_approve_announcement(self.pastor, ann))

    def test_approve_and_archive(self):
        ann = self._pending()
        approve_announcement(ann, self.pastor)
        ann.refresh_from_db()
        self.assertTrue(ann.is_approved)
        self.assertEqual(ann.approved_by, self.pastor)
        self.assertEqual(ann.status, Announcement.STATUS_APPROVED)
        self.assertTrue(
            AnnouncementAuditLog.objects.filter(announcement=ann, action="APPROVE").exists()
        )
        archive_announcement(ann, self.pastor)
        ann.refresh_from_db()
        self.assertTrue(ann.is_archived)
        self.assertEqual(ann.status, Announcement.STATUS_ARCHIVED)

    def test_reject_soft_keeps_record(self):
        ann = self._pending()
        pk = ann.pk
        creator, title, rejected = reject_announcement(
            ann, self.pastor, reason="Needs clearer date."
        )
        self.assertEqual(creator, self.secretary)
        self.assertEqual(title, "Test Announcement")
        self.assertTrue(Announcement.objects.filter(pk=pk).exists())
        rejected.refresh_from_db()
        self.assertTrue(rejected.is_rejected)
        self.assertEqual(rejected.rejection_reason, "Needs clearer date.")
        self.assertEqual(rejected.status, Announcement.STATUS_REJECTED)
        self.assertFalse(visible_announcements(self.secretary).filter(pk=pk).exists())

    def test_pending_for_pastor_scoped_to_church(self):
        self._pending()
        self._pending(church=self.other_church, title="Other")
        self.assertEqual(pending_for_user(self.pastor).count(), 1)

    def test_visible_excludes_unapproved(self):
        self._pending()
        approved = self._pending(title="Live", is_approved=True, approved_by=self.pastor)
        visible = visible_announcements(self.secretary)
        self.assertEqual(visible.count(), 1)
        self.assertEqual(visible.first().pk, approved.pk)

    def test_create_service_pending_for_secretary(self):
        ann = create_announcement(
            self.secretary,
            title="Service Create",
            content="Body",
            visibility="church",
            church=self.church,
        )
        self.assertFalse(ann.is_approved)
        self.assertEqual(ann.status, Announcement.STATUS_PENDING)

    def test_create_service_stays_pending_for_pastor_sod(self):
        """Maker-checker: even approvers submit to the pending queue by default."""
        ann = create_announcement(
            self.pastor,
            title="Pastor Post",
            content="Body",
            visibility="church",
            church=self.church,
        )
        self.assertFalse(ann.is_approved)
        self.assertEqual(ann.status, Announcement.STATUS_PENDING)

    def test_create_service_explicit_auto_approve(self):
        ann = create_announcement(
            self.pastor,
            title="Immediate",
            content="Body",
            visibility="church",
            church=self.church,
            auto_approve=True,
        )
        self.assertTrue(ann.is_approved)
        self.assertEqual(ann.approved_by, self.pastor)

    def test_district_pastor_sees_district_churches(self):
        district_pastor = User.objects.create_user(
            username="dp1",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
        )
        Announcement.objects.create(
            title="Other Church News",
            content="Hello",
            visibility="church",
            church=self.other_church,
            created_by=self.pastor,
            is_approved=True,
            approved_by=self.pastor,
            status=Announcement.STATUS_APPROVED,
        )
        visible = visible_announcements(district_pastor)
        self.assertTrue(visible.filter(title="Other Church News").exists())


class ViewTests(AnnouncementTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.secretary = User.objects.create_user(
            username="sec2",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pastor2",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.member = User.objects.create_user(
            username="member1",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )

    def test_create_submits_pending(self):
        self.client.login(username="sec2", password="pass12345")
        response = self.client.post(reverse("announcements:create_announcement"), {
            "title": "New Event",
            "content": "Join us Sunday",
            "visibility": "church",
            "church": self.church.pk,
            "auto_expire": False,
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 302)
        ann = Announcement.objects.get(title="New Event")
        self.assertFalse(ann.is_approved)
        self.assertTrue(
            AnnouncementAuditLog.objects.filter(announcement=ann, action="CREATE").exists()
        )

    def test_pending_approvals_requires_leadership(self):
        self.client.login(username="member1", password="pass12345")
        response = self.client.get(reverse("announcements:pending_approvals"))
        self.assertEqual(response.status_code, 403)

    def test_approve_publishes_and_notifies(self):
        ann = Announcement.objects.create(
            title="Approve Me",
            content="Content",
            visibility="church",
            church=self.church,
            created_by=self.secretary,
        )
        self.client.login(username="pastor2", password="pass12345")
        response = self.client.post(reverse("announcements:approve_announcement", args=[ann.pk]))
        self.assertEqual(response.status_code, 302)
        ann.refresh_from_db()
        self.assertTrue(ann.is_approved)
        self.assertEqual(
            Notification.objects.filter(user=self.secretary, title="Announcement approved").count(),
            1,
        )

    def test_reject_requires_reason_and_keeps_record(self):
        ann = Announcement.objects.create(
            title="Reject Me",
            content="Content",
            visibility="church",
            church=self.church,
            created_by=self.secretary,
        )
        self.client.login(username="pastor2", password="pass12345")
        response = self.client.post(
            reverse("announcements:reject_announcement", args=[ann.pk]),
            {"reason": "Please add an event date."},
        )
        self.assertEqual(response.status_code, 302)
        ann.refresh_from_db()
        self.assertTrue(ann.is_rejected)
        self.assertEqual(ann.rejection_reason, "Please add an event date.")
        self.assertEqual(
            Notification.objects.filter(user=self.secretary, title="Announcement rejected").count(),
            1,
        )

    def test_approved_visible_on_list(self):
        Announcement.objects.create(
            title="Published",
            content="Hello",
            visibility="church",
            church=self.church,
            created_by=self.pastor,
            is_approved=True,
            approved_by=self.pastor,
            status=Announcement.STATUS_APPROVED,
        )
        self.client.login(username="member1", password="pass12345")
        response = self.client.get(reverse("announcements:announcement_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published")

    def test_list_export_csv(self):
        self.client.login(username="pastor2", password="pass12345")
        response = self.client.get(reverse("announcements:announcement_list"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_archive_hides_from_list(self):
        ann = Announcement.objects.create(
            title="Old News",
            content="Hello",
            visibility="church",
            church=self.church,
            created_by=self.pastor,
            is_approved=True,
            approved_by=self.pastor,
            status=Announcement.STATUS_APPROVED,
        )
        self.client.login(username="pastor2", password="pass12345")
        response = self.client.post(reverse("announcements:archive_announcement", args=[ann.pk]))
        self.assertEqual(response.status_code, 302)
        ann.refresh_from_db()
        self.assertTrue(ann.is_archived)
        self.client.login(username="member1", password="pass12345")
        response = self.client.get(reverse("announcements:announcement_list"))
        titles = [a.title for a in response.context["announcements"]]
        self.assertNotIn("Old News", titles)

    def test_my_announcements_shows_pending(self):
        Announcement.objects.create(
            title="Waiting",
            content="Pending",
            visibility="church",
            church=self.church,
            created_by=self.secretary,
        )
        self.client.login(username="sec2", password="pass12345")
        response = self.client.get(reverse("announcements:my_announcements") + "?status=pending")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting")


class CalendarServiceTests(AnnouncementTestMixin, TestCase):
    def setUp(self):
        from datetime import date, timedelta

        from members.models import Member

        self.today = timezone.now().date()
        self.member_user = User.objects.create_user(
            username="memcal",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        Member.objects.create(
            church=self.church,
            first_name="Jane",
            last_name="Doe",
            gender="Female",
            date_of_birth=date(self.today.year - 30, self.today.month, self.today.day),
            is_active=True,
        )
        Member.objects.create(
            church=self.church,
            first_name="Far",
            last_name="Away",
            gender="Male",
            date_of_birth=date(1990, 1, 1),
            is_active=True,
        )
        self.future_bday = self.today + timedelta(days=10)
        Member.objects.create(
            church=self.church,
            first_name="Soon",
            last_name="Birthday",
            gender="Female",
            date_of_birth=date(2000, self.future_bday.month, self.future_bday.day),
            is_active=True,
        )

    def test_upcoming_birthdays_include_today_and_window(self):
        from django.test import RequestFactory

        from announcements.calendar_services import get_upcoming_birthdays

        request = RequestFactory().get("/")
        request.user = self.member_user
        request.session = {}
        items = get_upcoming_birthdays(request, days=30)
        names = [row["title"] for row in items]
        self.assertIn("Jane Doe", names)
        self.assertIn("Soon Birthday", names)
        self.assertNotIn("Far Away", names)

    def test_calendar_view_renders(self):
        self.client = Client()
        self.client.login(username="memcal", password="pass12345")
        response = self.client.get(reverse("announcements:upcoming_calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming Events")
        self.assertContains(response, "Jane Doe")
