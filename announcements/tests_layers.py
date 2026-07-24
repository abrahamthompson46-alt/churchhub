"""Characterization tests for announcements selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from announcements import repositories as repo
from announcements import selectors
from announcements.models import Announcement, AnnouncementAuditLog, AnnouncementView
from announcements.services import (
    approve_announcement,
    create_announcement,
    mark_viewed,
    visible_announcements,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class AnnouncementsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(
            name="Ann Layer Denom A", code="alda", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Ann Layer Denom B", code="aldb", is_active=True
        )
        conf_a = Conference.objects.create(
            code="ALCA", name="Ann Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="ALCB", name="Ann Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="ALZA", name="Ann Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="ALZB", name="Ann Zone B")
        dist_a = District.objects.create(zone=zone_a, code="ALDA", name="Ann Dist A")
        dist_b = District.objects.create(zone=zone_b, code="ALDB", name="Ann Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="ALCHA", name="Ann Church A"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="ALCHB", name="Ann Church B"
        )

    def setUp(self):
        self.sec_a = User.objects.create_user(
            username="ann_layer_sec_a",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.pastor_a = User.objects.create_user(
            username="ann_layer_pastor_a",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.sec_b = User.objects.create_user(
            username="ann_layer_sec_b",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church_b,
            denomination=self.denom_b,
        )

    def test_selector_reads_pending_and_list(self):
        pending = Announcement.objects.create(
            title="Pending A",
            content="Body",
            visibility="church",
            church=self.church_a,
            created_by=self.sec_a,
            status=Announcement.STATUS_PENDING,
        )
        qs = selectors.pending_announcements_base_qs()
        self.assertIn(pending, qs)
        mine = selectors.my_announcements_qs(self.sec_a, status="pending")
        self.assertIn(pending, mine)

    def test_church_isolation_visible_announcements(self):
        ann_a = create_announcement(
            self.pastor_a,
            title="Church A Notice",
            content="For A only",
            visibility="church",
            church=self.church_a,
            auto_approve=True,
        )
        self.assertTrue(ann_a.is_approved)
        visible_b = visible_announcements(self.sec_b)
        self.assertFalse(visible_b.filter(pk=ann_a.pk).exists())
        visible_a = visible_announcements(self.sec_a)
        self.assertTrue(visible_a.filter(pk=ann_a.pk).exists())

    def test_denomination_isolation_via_church_scope(self):
        # Church B sits under denom B; pastor A must not see church-B-only posts.
        ann_b = Announcement.objects.create(
            title="Denom B Notice",
            content="Scoped",
            visibility="church",
            church=self.church_b,
            created_by=self.sec_b,
            is_approved=True,
            status=Announcement.STATUS_APPROVED,
            approved_by=self.sec_b,
            approved_at=timezone.now(),
        )
        self.assertFalse(
            visible_announcements(self.pastor_a).filter(pk=ann_b.pk).exists()
        )
        self.assertTrue(
            visible_announcements(self.sec_b).filter(pk=ann_b.pk).exists()
        )

    def test_publishing_workflow_via_service(self):
        ann = create_announcement(
            self.sec_a,
            title="Needs Approval",
            content="Please review",
            visibility="church",
            church=self.church_a,
        )
        self.assertFalse(ann.is_approved)
        self.assertEqual(ann.status, Announcement.STATUS_PENDING)
        approve_announcement(ann, self.pastor_a)
        ann.refresh_from_db()
        self.assertTrue(ann.is_approved)
        self.assertEqual(ann.status, Announcement.STATUS_APPROVED)
        self.assertTrue(
            AnnouncementAuditLog.objects.filter(
                announcement=ann, action="APPROVE"
            ).exists()
        )

    def test_repository_writes_and_audit(self):
        ann = repo.create_announcement_instance(
            title="Repo Ann",
            content="Body",
            visibility="church",
            church=self.church_a,
            created_by=self.sec_a,
            status=Announcement.STATUS_PENDING,
            is_approved=False,
            is_rejected=False,
            is_archived=False,
        )
        self.assertTrue(Announcement.objects.filter(pk=ann.pk).exists())
        repo.create_audit_log(
            announcement=ann,
            church=self.church_a,
            action="CREATE",
            performed_by=self.sec_a,
            details={"via": "tests_layers"},
        )
        self.assertTrue(
            AnnouncementAuditLog.objects.filter(
                announcement=ann, action="CREATE", details__via="tests_layers"
            ).exists()
        )

    def test_view_tracking(self):
        ann = create_announcement(
            self.pastor_a,
            title="Track Me",
            content="Views",
            visibility="church",
            church=self.church_a,
        )
        obj, created = mark_viewed(self.sec_a, ann)
        self.assertTrue(created)
        self.assertTrue(
            AnnouncementView.objects.filter(user=self.sec_a, announcement=ann).exists()
        )
        _, created_again = mark_viewed(self.sec_a, ann)
        self.assertFalse(created_again)
        self.assertEqual(selectors.announcement_view_count(ann), 1)
        viewed = selectors.viewed_announcement_ids_for_user(self.sec_a, [ann.pk])
        self.assertIn(ann.pk, viewed)

    def test_selector_get_or_404(self):
        ann = Announcement.objects.create(
            title="Lookup",
            content="Body",
            visibility="church",
            church=self.church_a,
            created_by=self.sec_a,
        )
        found = selectors.get_announcement_or_404(ann.pk)
        self.assertEqual(found.pk, ann.pk)
        with self.assertRaises(Http404):
            selectors.get_announcement_or_404(999999)
