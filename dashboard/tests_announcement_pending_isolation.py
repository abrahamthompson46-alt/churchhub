"""Dashboard pending-announcement denomination isolation (Phase 2 final fix)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from announcements.models import Announcement
from dashboard.selectors import pending_announcements_for_admin
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class PendingAnnouncementsForAdminIsolationTests(TestCase):
    """INV-ANN-01: dashboard pending feed must not cross denominations."""

    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(
            name="Dash Ann Denom A", code="dash-ann-a", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Dash Ann Denom B", code="dash-ann-b", is_active=True
        )
        conf_a = Conference.objects.create(
            code="DACA", name="Dash Ann Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="DACB", name="Dash Ann Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="DAZA", name="Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="DAZB", name="Zone B")
        dist_a = District.objects.create(zone=zone_a, code="DADA", name="Dist A")
        dist_b = District.objects.create(zone=zone_b, code="DADB", name="Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="DACHA", name="Dash Church A"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="DACHB", name="Dash Church B"
        )

        cls.creator_a = User.objects.create_user(
            username="dash_ann_creator_a",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church_a,
            denomination=cls.denom_a,
        )
        cls.creator_b = User.objects.create_user(
            username="dash_ann_creator_b",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church_b,
            denomination=cls.denom_b,
        )
        cls.anchored_admin = User.objects.create_user(
            username="dash_ann_admin_a",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            denomination=cls.denom_a,
        )
        # Unanchored Django superuser — must fail closed (no denomination).
        cls.unanchored_super = User.objects.create_superuser(
            username="dash_ann_unanchored",
            password="pass12345",
            email="unanchored@example.com",
        )
        cls.unanchored_super.role = UserRole.SUPER_ADMIN
        cls.unanchored_super.denomination = None
        cls.unanchored_super.church = None
        cls.unanchored_super.is_platform_user = False
        cls.unanchored_super.save()

        cls.pending_a = Announcement.objects.create(
            title="Pending A",
            content="Body A",
            visibility="church",
            church=cls.church_a,
            denomination=cls.denom_a,
            created_by=cls.creator_a,
            is_approved=False,
            status=Announcement.STATUS_PENDING,
        )
        cls.pending_b = Announcement.objects.create(
            title="Pending B",
            content="Body B",
            visibility="church",
            church=cls.church_b,
            denomination=cls.denom_b,
            created_by=cls.creator_b,
            is_approved=False,
            status=Announcement.STATUS_PENDING,
        )
        cls.pending_general_a = Announcement.objects.create(
            title="Pending General A",
            content="Body GA",
            visibility="general",
            church=None,
            denomination=cls.denom_a,
            created_by=cls.anchored_admin,
            is_approved=False,
            status=Announcement.STATUS_PENDING,
        )

    def test_unanchored_superuser_receives_zero_pending(self):
        qs = pending_announcements_for_admin(
            self.unanchored_super,
            church_ids=[self.church_a.pk, self.church_b.pk],
        )
        self.assertEqual(qs.count(), 0)
        self.assertFalse(qs.filter(pk=self.pending_a.pk).exists())
        self.assertFalse(qs.filter(pk=self.pending_b.pk).exists())

    def test_anchored_admin_sees_only_own_denomination(self):
        qs = pending_announcements_for_admin(
            self.anchored_admin,
            church_ids=[self.church_a.pk],
        )
        self.assertTrue(qs.filter(pk=self.pending_a.pk).exists())
        self.assertTrue(qs.filter(pk=self.pending_general_a.pk).exists())
        self.assertFalse(qs.filter(pk=self.pending_b.pk).exists())
        for ann in qs:
            self.assertEqual(ann.denomination_id, self.denom_a.pk)

    def test_other_denomination_excluded_even_when_church_ids_list_is_wide(self):
        # Even if a caller passes foreign church IDs, denomination wall still applies.
        qs = pending_announcements_for_admin(
            self.anchored_admin,
            church_ids=[self.church_a.pk, self.church_b.pk],
        )
        self.assertFalse(qs.filter(pk=self.pending_b.pk).exists())
        self.assertTrue(qs.filter(denomination_id=self.denom_a.pk).exists())
        self.assertFalse(qs.filter(denomination_id=self.denom_b.pk).exists())
