"""Tests for permissions matrix, checks, overrides, and views."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from permissions.checks import (
    can_approve_minutes,
    can_approve_transactions,
    can_create_announcements,
    can_manage_finances,
    can_manage_members,
    can_manage_permissions,
    can_manage_users,
    can_view_all_churches,
    can_view_members,
    can_view_reports,
    is_superadmin,
    user_has_permission,
    user_has_role,
)
from permissions.middleware import PermissionCacheMiddleware, RoleEnforcementMiddleware
from permissions.models import Permission, PermissionOverride, RolePermission
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches, get_manageable_users
from permissions.scoping_checks import can_act_on_church, pending_for_church_scope
from permissions.services import (
    bind_request_permission_cache,
    create_override,
    ensure_permission_matrix,
    sync_role_groups,
    update_matrix_cell,
)
from meetings.models import Meeting, MeetingStatus, MinutesStatus

User = get_user_model()


class ChurchHubTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="P1", name="Perm Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="PZ", name="Perm Zone")
        cls.district = District.objects.create(zone=cls.zone, code="PD", name="Perm District")
        cls.church = Church.objects.create(district=cls.district, code="PC", name="Perm Church")
        ensure_permission_matrix()


class PermissionCheckTests(ChurchHubTestMixin, TestCase):
    def test_treasury_can_manage_finances(self):
        user = User.objects.create_user(
            username="perm_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertTrue(can_manage_finances(user))
        self.assertTrue(user_has_permission(user, "manage_finances"))

    def test_secretary_can_manage_members_and_finances(self):
        user = User.objects.create_user(
            username="perm_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.assertTrue(can_manage_members(user))
        self.assertTrue(can_manage_finances(user))
        self.assertFalse(can_approve_transactions(user))

    def test_member_is_restricted(self):
        user = User.objects.create_user(
            username="perm_mem",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.assertFalse(can_manage_finances(user))
        self.assertFalse(can_manage_members(user))
        self.assertFalse(can_manage_users(user))
        self.assertTrue(can_view_members(user))
        self.assertTrue(can_create_announcements(user))

    def test_manage_members_implies_view_members(self):
        user = User.objects.create_user(
            username="implies_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        perm_view = Permission.objects.get(codename="view_members")
        RolePermission.objects.filter(role=user.role, permission=perm_view).update(granted=False)
        self.assertTrue(can_manage_members(user))
        self.assertTrue(can_view_members(user))

    def test_treasury_lacks_approve_transactions_by_default(self):
        user = User.objects.create_user(
            username="perm_treasury_appr",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertTrue(can_manage_finances(user))
        self.assertFalse(can_approve_transactions(user))

    def test_board_member_has_read_permissions(self):
        user = User.objects.create_user(
            username="board1",
            password="pass12345",
            role=UserRole.BOARD_MEMBER,
            church=self.church,
        )
        self.assertTrue(can_view_members(user))
        self.assertTrue(can_view_reports(user))
        self.assertFalse(can_manage_members(user))
        self.assertFalse(can_manage_finances(user))

    def test_local_pastor_has_approve_minutes(self):
        user = User.objects.create_user(
            username="pastor_mins",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.assertTrue(can_approve_minutes(user))

    def test_superuser_has_full_access(self):
        user = User.objects.create_superuser(
            username="perm_admin",
            password="pass12345",
            email="perm@test.com",
        )
        self.assertTrue(is_superadmin(user))
        self.assertTrue(can_view_all_churches(user))
        self.assertTrue(can_manage_permissions(user))

    def test_super_admin_role_bypasses_deny_override(self):
        user = User.objects.create_user(
            username="super_admin_deny",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        perm = Permission.objects.get(codename="manage_finances")
        create_override(user, perm, granted=False, reason="Should not block super admin")
        self.assertTrue(is_superadmin(user))
        self.assertTrue(can_manage_finances(user))
        self.assertTrue(user_has_permission(user, "manage_finances"))

    def test_super_admin_bypasses_role_checks(self):
        user = User.objects.create_user(
            username="super_admin_role",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        self.assertTrue(user_has_role(user, {UserRole.TREASURY}))

    def test_platform_superuser_is_not_institution_superadmin(self):
        user = User.objects.create_superuser(
            username="platform_admin",
            password="pass12345",
            email="platform@test.com",
            is_platform_user=True,
        )
        self.assertFalse(is_superadmin(user))


class MatrixTests(ChurchHubTestMixin, TestCase):
    def test_matrix_seeded(self):
        self.assertGreater(Permission.objects.count(), 0)
        self.assertGreater(RolePermission.objects.count(), 0)

    def test_deny_override_blocks_permission(self):
        user = User.objects.create_user(
            username="override_user",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        perm = Permission.objects.get(codename="manage_finances")
        create_override(user, perm, granted=False, reason="Test deny")
        self.assertFalse(can_manage_finances(user))

    def test_grant_override_allows_permission(self):
        user = User.objects.create_user(
            username="grant_user",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        perm = Permission.objects.get(codename="manage_members")
        create_override(user, perm, granted=True, reason="Temp access")
        self.assertTrue(can_manage_members(user))

    def test_expired_override_ignored(self):
        from datetime import timedelta

        user = User.objects.create_user(
            username="expired_override",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        perm = Permission.objects.get(codename="manage_members")
        create_override(
            user,
            perm,
            granted=True,
            reason="Expired",
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(can_manage_members(user))

    def test_sync_role_groups_noop(self):
        user = User.objects.create_user(
            username="noop_groups",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        sync_role_groups(user)
        self.assertEqual(user.groups.count(), 0)


class ImpliesAndCacheTests(ChurchHubTestMixin, TestCase):
    def test_request_permission_cache(self):
        user = User.objects.create_user(
            username="cache_user",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        request = Client().get("/").wsgi_request
        request.user = user
        bind_request_permission_cache(request)
        self.assertTrue(can_manage_members(user))
        perm = Permission.objects.get(codename="manage_members")
        RolePermission.objects.filter(role=user.role, permission=perm).update(granted=False)
        self.assertTrue(can_manage_members(user))
        PermissionCacheMiddleware(lambda r: None)(request)
        self.assertFalse(can_manage_members(user))

    def test_matrix_cell_update_persists(self):
        perm = Permission.objects.get(codename="view_reports")
        update_matrix_cell(UserRole.MEMBER, perm.pk, True)
        rp = RolePermission.objects.get(role=UserRole.MEMBER, permission=perm)
        self.assertTrue(rp.granted)


class ScopingApprovalTests(ChurchHubTestMixin, TestCase):
    def setUp(self):
        self.pastor = User.objects.create_user(
            username="scope_pastor_appr",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.other_church = Church.objects.create(
            district=self.district, code="PC3", name="Scope Other Church"
        )
        self.meeting = Meeting.objects.create(
            church=self.church,
            title="Board Meeting",
            scheduled_at=timezone.now(),
            status=MeetingStatus.HELD,
            minutes_status=MinutesStatus.PENDING_APPROVAL,
            minutes_submitted_by=self.pastor,
        )

    def test_pastor_can_approve_own_church_minutes(self):
        self.assertTrue(can_act_on_church(self.pastor, self.church, "approve_minutes"))

    def test_pastor_cannot_approve_other_church(self):
        self.assertFalse(can_act_on_church(self.pastor, self.other_church, "approve_minutes"))

    def test_pending_queue_excludes_self_submission(self):
        qs = Meeting.objects.filter(minutes_status=MinutesStatus.PENDING_APPROVAL)
        scoped = pending_for_church_scope(
            self.pastor,
            qs,
            "approve_minutes",
            submitter_field="minutes_submitted_by",
        )
        self.assertFalse(scoped.filter(pk=self.meeting.pk).exists())


class ScopingTests(ChurchHubTestMixin, TestCase):
    def test_pastor_sees_church_users_only(self):
        pastor = User.objects.create_user(
            username="scope_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        other_church = Church.objects.create(
            district=self.district, code="PC2", name="Other Perm Church"
        )
        User.objects.create_user(
            username="other_user",
            password="pass12345",
            role=UserRole.MEMBER,
            church=other_church,
        )
        manageable = get_manageable_users(pastor)
        self.assertIn(pastor, manageable)
        self.assertFalse(manageable.filter(username="other_user").exists())


class PermissionViewTests(ChurchHubTestMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="perm_super",
            password="pass12345",
            email="super@test.com",
            role=UserRole.SUPER_ADMIN,
        )
        self.member = User.objects.create_user(
            username="perm_member_view",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )

    def test_matrix_requires_admin(self):
        self.client.login(username="perm_member_view", password="pass12345")
        response = self.client.get(reverse("permissions:matrix"))
        self.assertEqual(response.status_code, 403)

    def test_index_renders_for_superuser(self):
        self.client.login(username="perm_super", password="pass12345")
        response = self.client.get(reverse("permissions:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Permissions")


class MiddlewareTests(ChurchHubTestMixin, TestCase):
    def test_churchless_local_user_redirected(self):
        user = User.objects.create_user(
            username="no_church",
            password="pass12345",
            role=UserRole.SECRETARY,
        )
        self.client.login(username="no_church", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("profile", response.url)
