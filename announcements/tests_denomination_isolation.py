"""HTTP / service tests for announcement denomination isolation (CH-SEC-002 / 008)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.test.client import ContextList
from django.urls import reverse
from django.utils import timezone

from announcements.models import Announcement, AnnouncementImage
from announcements.services import (
    approve_announcement,
    can_approve_announcement,
    create_announcement,
    visible_announcements,
)
from church_system.media_authorization import user_may_access_media
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination, SiteSettings
from sitecontrol.services import clear_settings_cache

User = get_user_model()


class AnnouncementDenominationIsolationTests(TestCase):
    """Prove cross-denomination announcement and media isolation at HTTP level."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

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
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        clear_settings_cache()

        cls.denom_a = Denomination.objects.create(
            name="Ann Iso Denom A", code="ann-iso-a", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Ann Iso Denom B", code="ann-iso-b", is_active=True
        )
        conf_a = Conference.objects.create(
            code="AICA", name="Ann Iso Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="AICB", name="Ann Iso Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="AIZA", name="Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="AIZB", name="Zone B")
        dist_a = District.objects.create(zone=zone_a, code="AIDA", name="Dist A")
        dist_b = District.objects.create(zone=zone_b, code="AIDB", name="Dist B")
        cls.church_a1 = Church.objects.create(
            district=dist_a, code="AICH1", name="Church A1"
        )
        cls.church_a2 = Church.objects.create(
            district=dist_a, code="AICH2", name="Church A2"
        )
        cls.church_b1 = Church.objects.create(
            district=dist_b, code="AICHB1", name="Church B1"
        )

        cls.pastor_a = User.objects.create_user(
            username="ann_iso_pastor_a",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church_a1,
            denomination=cls.denom_a,
        )
        cls.pastor_b = User.objects.create_user(
            username="ann_iso_pastor_b",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church_b1,
            denomination=cls.denom_b,
        )
        cls.sec_a2 = User.objects.create_user(
            username="ann_iso_sec_a2",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church_a2,
            denomination=cls.denom_a,
        )
        cls.member_a = User.objects.create_user(
            username="ann_iso_member_a",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church_a1,
            denomination=cls.denom_a,
        )
        cls.board_a = User.objects.create_user(
            username="ann_iso_board_a",
            password="pass12345",
            role=UserRole.BOARD_MEMBER,
            church=cls.church_a1,
            denomination=cls.denom_a,
        )
        cls.top_a = User.objects.create_user(
            username="ann_iso_top_a",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            denomination=cls.denom_a,
        )
        cls.top_b = User.objects.create_user(
            username="ann_iso_top_b",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            denomination=cls.denom_b,
        )
        cls.district_pastor_a = User.objects.create_user(
            username="ann_iso_dp_a",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church_a1,
            denomination=cls.denom_a,
        )

    def setUp(self):
        self.client = Client()

    def _login(self, user):
        self.client.login(username=user.username, password="pass12345")
        session = self.client.session
        if user.church_id:
            session["current_church_id"] = str(user.church_id)
        denom = user.denomination_id or (
            user.church.district.zone.conference.denomination_id if user.church_id else None
        )
        if denom:
            session["active_denomination_id"] = str(denom)
        session.save()

    def _approved_general(self, *, denom, creator, title="General Notice"):
        return Announcement.objects.create(
            title=title,
            content=f"Body for {title}",
            visibility="general",
            church=None,
            denomination=denom,
            created_by=creator,
            is_approved=True,
            approved_by=creator,
            approved_at=timezone.now(),
            status=Announcement.STATUS_APPROVED,
        )

    def _approved_church(self, *, church, creator, title="Church Notice"):
        denom = church.district.zone.conference.denomination
        return Announcement.objects.create(
            title=title,
            content=f"Body for {title}",
            visibility="church",
            church=church,
            denomination=denom,
            created_by=creator,
            is_approved=True,
            approved_by=creator,
            approved_at=timezone.now(),
            status=Announcement.STATUS_APPROVED,
        )

    def _pending_church(self, *, church, creator, title="Pending Notice"):
        denom = church.district.zone.conference.denomination
        return Announcement.objects.create(
            title=title,
            content=f"Body for {title}",
            visibility="church",
            church=church,
            denomination=denom,
            created_by=creator,
            is_approved=False,
            status=Announcement.STATUS_PENDING,
        )

    def test_01_denom_a_cannot_list_denom_b_general(self):
        gen_b = self._approved_general(
            denom=self.denom_b, creator=self.top_b, title="Secret B General"
        )
        self._login(self.pastor_a)
        response = self.client.get(reverse("announcements:announcement_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secret B General")
        self.assertFalse(
            visible_announcements(self.pastor_a).filter(pk=gen_b.pk).exists()
        )

    def test_02_denom_a_cannot_detail_denom_b_announcement(self):
        gen_b = self._approved_general(
            denom=self.denom_b, creator=self.top_b, title="B Detail Blocked"
        )
        self._login(self.pastor_a)
        response = self.client.get(
            reverse("announcements:announcement_detail", args=[gen_b.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_03_view_all_churches_does_not_cross_denomination(self):
        gen_b = self._approved_general(
            denom=self.denom_b, creator=self.top_b, title="B Super Scope"
        )
        church_b = self._approved_church(
            church=self.church_b1, creator=self.pastor_b, title="B Church Only"
        )
        self.assertFalse(
            visible_announcements(self.top_a).filter(pk=gen_b.pk).exists()
        )
        self.assertFalse(
            visible_announcements(self.top_a).filter(pk=church_b.pk).exists()
        )
        self._login(self.top_a)
        response = self.client.get(reverse("announcements:announcement_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "B Super Scope")
        self.assertNotContains(response, "B Church Only")

    def test_04_same_denom_general_visible(self):
        gen_a = self._approved_general(
            denom=self.denom_a, creator=self.top_a, title="Shared A General"
        )
        self.assertTrue(
            visible_announcements(self.pastor_a).filter(pk=gen_a.pk).exists()
        )
        self.assertTrue(
            visible_announcements(self.member_a).filter(pk=gen_a.pk).exists()
        )
        self._login(self.member_a)
        response = self.client.get(reverse("announcements:announcement_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared A General")

    def test_05_same_denom_church_visible_in_authorized_scope(self):
        ann_a1 = self._approved_church(
            church=self.church_a1, creator=self.pastor_a, title="A1 Local"
        )
        # District pastor manages both A1 and A2 in same district.
        self.assertTrue(
            visible_announcements(self.district_pastor_a).filter(pk=ann_a1.pk).exists()
        )
        self.assertTrue(
            visible_announcements(self.pastor_a).filter(pk=ann_a1.pk).exists()
        )

    def test_06_wrong_church_cannot_access_church_scoped(self):
        ann_a1 = self._approved_church(
            church=self.church_a1, creator=self.pastor_a, title="A1 Only"
        )
        self.assertFalse(
            visible_announcements(self.sec_a2).filter(pk=ann_a1.pk).exists()
        )
        self._login(self.sec_a2)
        response = self.client.get(
            reverse("announcements:announcement_detail", args=[ann_a1.pk])
        )
        # Same denomination so PK loads, but not published to this church → deny.
        self.assertIn(response.status_code, (403, 404))

    def test_07_missing_denomination_fails_closed(self):
        orphan = Announcement.objects.create(
            title="Orphan Quarantine",
            content="No tenant",
            visibility="general",
            church=None,
            denomination=None,
            created_by=self.top_a,
            is_approved=True,
            approved_by=self.top_a,
            approved_at=timezone.now(),
            status=Announcement.STATUS_APPROVED,
        )
        # Bypass model clean for quarantine simulation.
        Announcement.objects.filter(pk=orphan.pk).update(denomination=None)
        orphan.refresh_from_db()
        self.assertIsNone(orphan.denomination_id)
        self.assertFalse(
            visible_announcements(self.pastor_a).filter(pk=orphan.pk).exists()
        )
        self.assertFalse(
            visible_announcements(self.top_a).filter(pk=orphan.pk).exists()
        )
        self._login(self.top_a)
        response = self.client.get(
            reverse("announcements:announcement_detail", args=[orphan.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_08_unauthorized_approval_denied(self):
        pending_b = self._pending_church(
            church=self.church_b1, creator=self.pastor_b, title="Approve Leak"
        )
        self.assertFalse(can_approve_announcement(self.pastor_a, pending_b))
        self._login(self.pastor_a)
        response = self.client.post(
            reverse("announcements:approve_announcement", args=[pending_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        pending_b.refresh_from_db()
        self.assertFalse(pending_b.is_approved)

    def test_09_unauthorized_mutation_denied(self):
        pending_b = self._pending_church(
            church=self.church_b1, creator=self.pastor_b, title="Edit Leak"
        )
        self._login(self.pastor_a)
        response = self.client.get(
            reverse("announcements:edit_announcement", args=[pending_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("announcements:archive_announcement", args=[pending_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        # Board member (view-only) cannot approve own-denom pending.
        pending_a = self._pending_church(
            church=self.church_a1, creator=self.pastor_a, title="Board Cannot Approve"
        )
        self.assertFalse(can_approve_announcement(self.board_a, pending_a))
        self._login(self.board_a)
        response = self.client.post(
            reverse("announcements:approve_announcement", args=[pending_a.pk])
        )
        self.assertEqual(response.status_code, 403)
        pending_a.refresh_from_db()
        self.assertFalse(pending_a.is_approved)

    def test_10_announcement_media_follows_denomination(self):
        from django.core.files.storage import default_storage

        gen_a = self._approved_general(
            denom=self.denom_a, creator=self.top_a, title="Media A"
        )
        gen_b = self._approved_general(
            denom=self.denom_b, creator=self.top_b, title="Media B"
        )
        path_a = "announcements/iso_media_a.jpg"
        path_b = "announcements/iso_media_b.jpg"
        default_storage.save(path_a, ContentFile(b"img-a"))
        default_storage.save(path_b, ContentFile(b"img-b"))
        AnnouncementImage.objects.bulk_create(
            [
                AnnouncementImage(announcement=gen_a, image=path_a),
                AnnouncementImage(announcement=gen_b, image=path_b),
            ]
        )
        self.assertTrue(user_may_access_media(self.pastor_a, path_a))
        self.assertFalse(user_may_access_media(self.pastor_a, path_b))
        self.assertFalse(user_may_access_media(self.pastor_b, path_a))

    def test_11_creator_denomination_change_does_not_move_ownership(self):
        gen_a = self._approved_general(
            denom=self.denom_a, creator=self.top_a, title="Owned By Denom A"
        )
        # Move creator into denomination B — ownership stays on announcement.denomination.
        self.top_a.denomination = self.denom_b
        self.top_a.save(update_fields=["denomination"])
        gen_a.refresh_from_db()
        self.assertEqual(gen_a.denomination_id, self.denom_a.pk)
        self.assertTrue(
            visible_announcements(self.pastor_a).filter(pk=gen_a.pk).exists()
        )
        self.assertFalse(
            visible_announcements(self.pastor_b).filter(pk=gen_a.pk).exists()
        )
        # Restore for other tests in this class instance.
        self.top_a.denomination = self.denom_a
        self.top_a.save(update_fields=["denomination"])

    def test_12_portal_member_sees_same_denom_policy(self):
        gen_a = self._approved_general(
            denom=self.denom_a, creator=self.top_a, title="Portal A Visible"
        )
        gen_b = self._approved_general(
            denom=self.denom_b, creator=self.top_b, title="Portal B Hidden"
        )
        self.assertTrue(
            visible_announcements(self.member_a).filter(pk=gen_a.pk).exists()
        )
        self.assertFalse(
            visible_announcements(self.member_a).filter(pk=gen_b.pk).exists()
        )
        self._login(self.member_a)
        # Portal detail uses visible_announcements; cross-tenant → 404.
        response = self.client.get(
            reverse("portal:announcement_detail", args=[gen_b.pk])
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            reverse("portal:announcement_detail", args=[gen_a.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal A Visible")

    def test_13_platform_operator_bounded(self):
        from django.core.files.storage import default_storage

        platform = User.objects.create_user(
            username="ann_iso_platform",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            is_platform_user=True,
        )
        gen_a = self._approved_general(
            denom=self.denom_a, creator=self.top_a, title="Platform Denied"
        )
        self.assertFalse(
            visible_announcements(platform).filter(pk=gen_a.pk).exists()
        )
        path = "announcements/iso_plat.jpg"
        default_storage.save(path, ContentFile(b"x"))
        AnnouncementImage.objects.bulk_create(
            [AnnouncementImage(announcement=gen_a, image=path)]
        )
        self.assertFalse(user_may_access_media(platform, path))

    def test_14_predictable_id_cannot_bypass_authorization(self):
        pending_b = self._pending_church(
            church=self.church_b1, creator=self.pastor_b, title="IDOR Target"
        )
        self._login(self.pastor_a)
        for name in (
            "announcement_detail",
            "edit_announcement",
        ):
            response = self.client.get(reverse(f"announcements:{name}", args=[pending_b.pk]))
            self.assertEqual(response.status_code, 404, msg=name)
        for name in (
            "approve_announcement",
            "reject_announcement",
            "archive_announcement",
        ):
            response = self.client.post(
                reverse(f"announcements:{name}", args=[pending_b.pk]),
                {"reason": "cross tenant attempt"},
            )
            self.assertEqual(response.status_code, 404, msg=name)

    def test_create_sets_denomination_and_approve_same_denom(self):
        ann = create_announcement(
            self.pastor_a,
            title="Create Sets Denom",
            content="Body",
            visibility="church",
            church=self.church_a1,
        )
        self.assertEqual(ann.denomination_id, self.denom_a.pk)
        approve_announcement(ann, self.pastor_a)
        ann.refresh_from_db()
        self.assertTrue(ann.is_approved)

    def test_general_create_requires_actor_denomination(self):
        ann = create_announcement(
            self.top_a,
            title="Denom Wide",
            content="Body",
            visibility="general",
            auto_approve=True,
        )
        self.assertEqual(ann.denomination_id, self.denom_a.pk)
        self.assertIsNone(ann.church_id)
