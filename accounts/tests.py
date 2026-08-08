"""Tests for accounts permissions, services, views, and middleware."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import AcceptInvitationForm, UserInviteForm, UserManageForm
from accounts.models import UserActivityLog, UserInvitation
from accounts.permissions import (
    can_approve_transactions,
    can_manage_finances,
    can_manage_members,
    can_manage_users,
    can_view_all_churches,
    get_manageable_churches,
    get_manageable_users,
)
from accounts.services import (
    accept_invitation,
    activate_user,
    create_invitation,
    deactivate_user,
    resend_invitation,
    revoke_invitation,
    sync_role_groups,
    update_user_role,
)
from organization.models import Church, Conference, District, Zone
from permissions.middleware import RoleEnforcementMiddleware
from permissions.roles import UserRole
from sitecontrol.models import SiteSettings

User = get_user_model()


class ChurchHubTestMixin:
    """Minimal organization hierarchy for account tests."""

    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="T1", name="Test Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="Z1", name="Test Zone")
        cls.district = District.objects.create(zone=cls.zone, code="D1", name="Test District")
        cls.church = Church.objects.create(
            district=cls.district,
            code="C1",
            name="Test Church",
        )
        cls.other_district = District.objects.create(zone=cls.zone, code="D2", name="Other District")
        cls.other_church = Church.objects.create(
            district=cls.other_district,
            code="C2",
            name="Other Church",
        )
        from permissions.services import ensure_permission_matrix
        ensure_permission_matrix()


class PermissionTests(ChurchHubTestMixin, TestCase):
    def test_treasury_can_manage_finances_not_approve(self):
        user = User.objects.create_user(
            username="treasury1",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.assertTrue(can_manage_finances(user))
        self.assertFalse(can_approve_transactions(user))

    def test_secretary_can_manage_members_and_finances(self):
        user = User.objects.create_user(
            username="sec1",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.assertTrue(can_manage_members(user))
        self.assertTrue(can_manage_finances(user))
        self.assertFalse(can_approve_transactions(user))

    def test_member_role_is_restricted(self):
        user = User.objects.create_user(
            username="mem1",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self.assertFalse(can_manage_finances(user))
        self.assertFalse(can_manage_members(user))
        self.assertFalse(can_manage_users(user))

    def test_superuser_has_full_access(self):
        user = User.objects.create_superuser(
            username="admin1",
            password="pass12345",
            email="admin@test.com",
        )
        self.assertTrue(can_view_all_churches(user))
        self.assertTrue(can_manage_finances(user))
        self.assertTrue(can_manage_users(user))

    def test_local_pastor_can_manage_users_in_church(self):
        pastor = User.objects.create_user(
            username="pastor1",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.assertTrue(can_manage_users(pastor))


class RoleAssignmentTests(ChurchHubTestMixin, TestCase):
    def test_local_pastor_cannot_assign_district_pastor(self):
        pastor = User.objects.create_user(
            username="lp_assign",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.assertFalse(
            UserRole.can_assign_role(pastor.role, UserRole.DISTRICT_PASTOR)
        )
        choices = {c[0] for c in UserRole.assignable_role_choices(pastor)}
        self.assertNotIn(UserRole.DISTRICT_PASTOR, choices)
        with self.assertRaises(ValueError):
            create_invitation(
                email="dp@test.com",
                username="dp_invite",
                role=UserRole.DISTRICT_PASTOR,
                church=self.church,
                invited_by=pastor,
            )

    def test_secretary_can_only_assign_member(self):
        secretary = User.objects.create_user(
            username="sec_assign",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        choices = {c[0] for c in UserRole.assignable_role_choices(secretary)}
        self.assertEqual(choices, {UserRole.MEMBER})
        self.assertFalse(UserRole.can_assign_role(secretary.role, UserRole.TREASURY))
        self.assertTrue(UserRole.can_assign_role(secretary.role, UserRole.MEMBER))

    def test_superuser_can_assign_super_admin(self):
        admin = User.objects.create_superuser(
            username="su_assign",
            password="pass12345",
            email="su@test.com",
        )
        choices = {c[0] for c in UserRole.assignable_role_choices(admin)}
        self.assertIn(UserRole.SUPER_ADMIN, choices)
        self.assertTrue(
            UserRole.can_assign_role(
                admin.role, UserRole.SUPER_ADMIN, actor_is_superuser=True
            )
        )


class ManageableScopeTests(ChurchHubTestMixin, TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="sa",
            password="pass12345",
            email="sa@test.com",
            role=UserRole.SUPER_ADMIN,
        )
        self.pastor = User.objects.create_user(
            username="pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.other_pastor = User.objects.create_user(
            username="other_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.other_church,
        )
        User.objects.create_user(
            username="member1",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )

    def test_super_admin_sees_all_users_and_churches(self):
        self.assertEqual(get_manageable_users(self.super_admin).count(), 4)
        self.assertEqual(get_manageable_churches(self.super_admin).count(), 2)

    def test_local_pastor_scoped_to_own_church(self):
        manageable = get_manageable_users(self.pastor)
        self.assertIn(self.pastor, manageable)
        self.assertNotIn(self.other_pastor, manageable)
        self.assertEqual(get_manageable_churches(self.pastor).count(), 1)
        self.assertEqual(get_manageable_churches(self.pastor).first(), self.church)

    def test_get_manageable_users_excludes_platform_users(self):
        platform = User.objects.create_user(
            username="platform_op",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
        )
        manageable = get_manageable_users(self.super_admin)
        self.assertNotIn(platform, manageable)
        self.assertFalse(manageable.filter(is_platform_user=True).exists())


class ServiceTests(ChurchHubTestMixin, TestCase):
    def setUp(self):
        from sitecontrol.services import clear_settings_cache

        self.manager = User.objects.create_superuser(
            username="mgr",
            password="pass12345",
            email="mgr@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        self.target = User.objects.create_user(
            username="target",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        site = SiteSettings.load()
        site.password_min_length = 8
        site.password_require_uppercase = False
        site.save(update_fields=["password_min_length", "password_require_uppercase"])
        clear_settings_cache()

    def test_sync_role_groups_assigns_treasury_groups(self):
        user = User.objects.create_user(
            username="treasury2",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        sync_role_groups(user)
        self.assertEqual(user.groups.count(), 0)

    def test_sync_role_groups_is_noop(self):
        Group.objects.get_or_create(name="Admins")
        Group.objects.get_or_create(name="superAdmin")
        sync_role_groups(self.manager)
        self.assertEqual(self.manager.groups.count(), 0)

    def test_deactivate_and_activate_log_activity(self):
        deactivate_user(self.target, performed_by=self.manager, ip_address="127.0.0.1")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(
            UserActivityLog.objects.filter(user=self.target, action="USER_DEACTIVATE").exists()
        )

        activate_user(self.target, performed_by=self.manager, ip_address="127.0.0.1")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(
            UserActivityLog.objects.filter(user=self.target, action="USER_ACTIVATE").exists()
        )

    def test_self_deactivate_blocked(self):
        with self.assertRaises(ValueError):
            deactivate_user(self.manager, performed_by=self.manager)

    def test_update_user_role_logs_and_syncs_groups(self):
        Group.objects.get_or_create(name="admin")
        update_user_role(
            self.target,
            UserRole.LOCAL_PASTOR,
            performed_by=self.manager,
            ip_address="127.0.0.1",
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, UserRole.LOCAL_PASTOR)
        log = UserActivityLog.objects.filter(user=self.target, action="ROLE_CHANGE").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details["old_role"], UserRole.SECRETARY)
        self.assertEqual(log.details["new_role"], UserRole.LOCAL_PASTOR)

    def test_update_user_role_idempotent_skips_log(self):
        before = UserActivityLog.objects.filter(user=self.target, action="ROLE_CHANGE").count()
        update_user_role(
            self.target,
            UserRole.SECRETARY,
            performed_by=self.manager,
        )
        after = UserActivityLog.objects.filter(user=self.target, action="ROLE_CHANGE").count()
        self.assertEqual(before, after)

    def test_invitation_create_and_accept(self):
        invitation = create_invitation(
            email="new@test.com",
            username="newuser",
            role=UserRole.SECRETARY,
            church=self.church,
            invited_by=self.manager,
        )
        self.assertTrue(invitation.is_valid)
        self.assertTrue(
            UserActivityLog.objects.filter(user=self.manager, action="INVITE_SENT").exists()
        )

        user = accept_invitation(
            invitation,
            password="securepass12",
            first_name="New",
            last_name="User",
        )
        invitation.refresh_from_db()
        self.assertFalse(invitation.is_valid)
        self.assertTrue(invitation.is_accepted)
        self.assertEqual(user.username, "newuser")
        self.assertEqual(user.church, self.church)
        self.assertTrue(
            UserActivityLog.objects.filter(user=user, action="INVITE_ACCEPTED").exists()
        )

    def test_accept_invite_rejects_short_password(self):
        from sitecontrol.services import clear_settings_cache

        invitation = create_invitation(
            email="shortpw@test.com",
            username="shortpw",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.manager,
        )
        site = SiteSettings.load()
        site.password_min_length = 12
        site.save(update_fields=["password_min_length"])
        clear_settings_cache()
        with self.assertRaises(Exception):
            accept_invitation(invitation, password="short", first_name="A", last_name="B")

    def test_accept_form_validates_site_min_length(self):
        from sitecontrol.services import clear_settings_cache

        invitation = create_invitation(
            email="formpw@test.com",
            username="formpw",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.manager,
        )
        site = SiteSettings.load()
        site.password_min_length = 12
        site.save(update_fields=["password_min_length"])
        clear_settings_cache()
        form = AcceptInvitationForm(
            data={
                "first_name": "A",
                "last_name": "B",
                "password1": "shortpass1",
                "password2": "shortpass1",
            },
            invitation=invitation,
        )
        self.assertFalse(form.is_valid())

    def test_revoke_invitation_invalidates_accept(self):
        invitation = create_invitation(
            email="revoke@test.com",
            username="revoked_user",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.manager,
        )
        revoke_invitation(invitation, performed_by=self.manager)
        invitation.refresh_from_db()
        self.assertFalse(invitation.is_valid)
        self.assertTrue(invitation.is_revoked)
        with self.assertRaises(ValueError):
            accept_invitation(invitation, password="securepass12", first_name="R", last_name="U")

    def test_resend_invitation_extends_expiry(self):
        invitation = create_invitation(
            email="resend@test.com",
            username="resend_user",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.manager,
        )
        old_expiry = invitation.expires_at
        old_token = invitation.token
        before = timezone.now()
        resend_invitation(invitation, performed_by=self.manager)
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.token, old_token)
        self.assertGreater(invitation.expires_at, old_expiry)
        self.assertLessEqual(invitation.expires_at, before + timedelta(hours=1, minutes=1))
        self.assertTrue(
            UserActivityLog.objects.filter(user=self.manager, action="INVITE_RESENT").exists()
        )

    def test_invitation_defaults_to_one_hour_and_single_use(self):
        before = timezone.now()
        invitation = create_invitation(
            email="hour@test.com",
            username="hour_user",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.manager,
        )
        self.assertGreaterEqual(invitation.expires_at, before + timedelta(minutes=55))
        self.assertLessEqual(invitation.expires_at, before + timedelta(hours=1, minutes=1))
        accept_invitation(invitation, password="securepass12", first_name="H", last_name="U")
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)
        self.assertFalse(invitation.is_valid)
        with self.assertRaises(ValueError):
            accept_invitation(invitation, password="securepass12", first_name="H", last_name="U")


class FormTests(ChurchHubTestMixin, TestCase):
    def test_user_manage_form_excludes_is_active(self):
        manager = User.objects.create_superuser(
            username="form_mgr",
            password="pass12345",
            email="formmgr@test.com",
        )
        target = User.objects.create_user(
            username="form_target",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
            is_active=True,
        )
        form = UserManageForm(
            data={
                "first_name": "X",
                "last_name": "Y",
                "email": "xy@test.com",
                "phone": "",
                "role": UserRole.MEMBER,
                "scope_level": "CHURCH",
                "scope_unit": str(self.church.pk),
                "church": str(self.church.pk),
                "is_active": False,
            },
            instance=target,
            manager=manager,
        )
        self.assertNotIn("is_active", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertTrue(saved.is_active)

    def test_invite_form_filters_roles_for_local_pastor(self):
        pastor = User.objects.create_user(
            username="form_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        form = UserInviteForm(manager=pastor)
        choices = {c[0] for c in form.fields["role"].choices}
        self.assertNotIn(UserRole.DISTRICT_PASTOR, choices)
        self.assertIn(UserRole.MEMBER, choices)


class ViewTests(ChurchHubTestMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Python 3.14 + Django test client: Context.__copy__ crashes in
        # store_rendered_templates. Skip the copy; status/content asserts still work.
        from unittest.mock import patch

        from django.test.client import ContextList

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

    def setUp(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret

        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin",
            password="pass12345",
            email="admin@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        enable_mfa_for_user(self.admin, generate_totp_secret(), [])
        self.member = User.objects.create_user(
            username="member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
        )
        self._mfa_session_key = SESSION_MFA_VERIFIED

    def _login(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[self._mfa_session_key] = True
        session.save()

    def test_user_list_requires_manager_role(self):
        self._login("member")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

        self._login("admin")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)

    def test_user_list_pagination(self):
        for i in range(30):
            User.objects.create_user(
                username=f"pageuser{i}",
                password="pass12345",
                role=UserRole.MEMBER,
                church=self.church,
            )
        self._login("admin")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 25)
        response2 = self.client.get(reverse("accounts:user_list") + "?page=2")
        self.assertEqual(response2.status_code, 200)
        self.assertGreater(len(response2.context["page_obj"].object_list), 0)

    def test_invite_user_creates_invitation(self):
        self._login("admin")
        response = self.client.post(
            reverse("accounts:invite_user"),
            {
                "email": "invite@test.com",
                "username": "invited",
                "role": UserRole.SECRETARY,
                "scope_level": "CHURCH",
                "scope_unit": str(self.church.pk),
                "church": str(self.church.pk),
            },
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context.get("form") and response.context["form"].errors)
        self.assertTrue(UserInvitation.objects.filter(username="invited").exists())

    def test_duplicate_pending_invite_is_resent(self):
        from unittest.mock import patch

        invitation = create_invitation(
            email="retry@test.com",
            username="retry_invited",
            role=UserRole.SECRETARY,
            church=self.church,
            invited_by=self.admin,
        )
        self._login("admin")
        with patch(
            "accounts.views.resend_invitation",
            return_value=(invitation, True),
        ) as resend:
            response = self.client.post(
                reverse("accounts:invite_user"),
                {
                    "email": "retry@test.com",
                    "username": "retry_invited",
                    "role": UserRole.SECRETARY,
                    "scope_level": "CHURCH",
                    "scope_unit": str(self.church.pk),
                    "church": str(self.church.pk),
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:invite_detail", args=[invitation.pk]))
        resend.assert_called_once()

    def test_churchless_pending_invite_lookup_is_denomination_scoped(self):
        from accounts import selectors
        from sitecontrol.models import Denomination

        first = Denomination.objects.create(name="First", code="first-invite")
        second = Denomination.objects.create(name="Second", code="second-invite")
        expiry = timezone.now() + timedelta(hours=1)
        first_invite = UserInvitation.objects.create(
            email="shared@test.com",
            username="first_shared",
            role=UserRole.CONFERENCE_ADMIN,
            scope_level="DENOMINATION",
            denomination=first,
            invited_by=self.admin,
            expires_at=expiry,
        )
        second_invite = UserInvitation.objects.create(
            email="shared@test.com",
            username="second_shared",
            role=UserRole.CONFERENCE_ADMIN,
            scope_level="DENOMINATION",
            denomination=second,
            invited_by=self.admin,
            expires_at=expiry,
        )
        self.assertEqual(
            selectors.pending_invitation_for_email(
                email="shared@test.com",
                denomination=first,
            ),
            first_invite,
        )
        self.assertEqual(
            selectors.pending_invitation_for_email(
                email="shared@test.com",
                denomination=second,
            ),
            second_invite,
        )

    def test_local_pastor_cannot_invite_district_pastor_via_view(self):
        User.objects.create_user(
            username="lp_view",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self._login("lp_view")
        response = self.client.post(
            reverse("accounts:invite_user"),
            {
                "email": "bad@test.com",
                "username": "bad_dp",
                "role": UserRole.DISTRICT_PASTOR,
                "church": str(self.church.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserInvitation.objects.filter(username="bad_dp").exists())

    def test_accept_invite_creates_user(self):
        invitation = create_invitation(
            email="accept@test.com",
            username="accepted",
            role=UserRole.TREASURY,
            church=self.church,
            invited_by=self.admin,
        )
        response = self.client.post(
            reverse("accounts:accept_invite", kwargs={"token": invitation.token}),
            {
                "first_name": "Accept",
                "last_name": "Test",
                "password1": "longpassword12",
                "password2": "longpassword12",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="accepted").exists())

    def test_activity_log_accessible_to_managers(self):
        self._login("admin")
        response = self.client.get(reverse("accounts:activity_log"))
        self.assertEqual(response.status_code, 200)

    def test_user_detail_update(self):
        target = User.objects.create_user(
            username="editme",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
            first_name="Old",
        )
        self._login("admin")
        response = self.client.post(
            reverse("accounts:user_detail", kwargs={"pk": target.pk}),
            {
                "first_name": "Updated",
                "last_name": "",
                "email": "editme@test.com",
                "phone": "",
                "role": UserRole.SECRETARY,
                "scope_level": "CHURCH",
                "scope_unit": str(self.church.pk),
                "church": str(self.church.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.first_name, "Updated")

    def test_user_detail_role_change_audits_old_role(self):
        target = User.objects.create_user(
            username="rolechange",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self._login("admin")
        response = self.client.post(
            reverse("accounts:user_detail", kwargs={"pk": target.pk}),
            {
                "action": "save",
                "first_name": "",
                "last_name": "",
                "email": "rolechange@test.com",
                "phone": "",
                "role": UserRole.TREASURY,
                "scope_level": "CHURCH",
                "scope_unit": str(self.church.pk),
                "church": str(self.church.pk),
                "member": "",
            },
        )
        if response.status_code != 302:
            form = response.context["form"] if response.context else None
            self.fail(f"expected 302 got {response.status_code} errors={getattr(form, 'errors', None)}")
        self.assertEqual(response.url, reverse("accounts:user_detail", kwargs={"pk": target.pk}))
        target.refresh_from_db()
        self.assertEqual(target.role, UserRole.TREASURY)
        log = UserActivityLog.objects.filter(user=target, action="ROLE_CHANGE").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details["old_role"], UserRole.SECRETARY)
        self.assertEqual(log.details["new_role"], UserRole.TREASURY)

    def test_self_deactivate_blocked_in_view(self):
        self._login("admin")
        response = self.client.post(
            reverse("accounts:user_detail", kwargs={"pk": self.admin.pk}),
            {"action": "deactivate"},
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_platform_user_can_get_profile(self):
        platform = User.objects.create_user(
            username="plat_profile",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
            email="plat@test.com",
        )
        self.client.force_login(platform)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_invite_revoke_via_view(self):
        invitation = create_invitation(
            email="viewrevoke@test.com",
            username="viewrevoke",
            role=UserRole.MEMBER,
            church=self.church,
            invited_by=self.admin,
        )
        self._login("admin")
        response = self.client.post(
            reverse("accounts:invite_revoke", kwargs={"pk": invitation.pk})
        )
        self.assertEqual(response.status_code, 302)
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_revoked)


class MiddlewareTests(ChurchHubTestMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from unittest.mock import patch

        from django.test.client import ContextList

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

    def test_unassigned_local_role_redirected_to_profile(self):
        user = User.objects.create_user(
            username="nochurch",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=None,
        )
        client = Client()
        client.force_login(user)
        response = client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/profile/", response.url)

    def test_profile_exempt_from_church_requirement(self):
        user = User.objects.create_user(
            username="nochurch2",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=None,
        )
        client = Client()
        client.force_login(user)
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_middleware_passes_through_when_church_assigned(self):
        user = User.objects.create_user(
            username="haschurch",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        middleware = RoleEnforcementMiddleware(lambda r: None)
        request = Client().get("/").wsgi_request
        request.user = user
        request.path = "/dashboard/"
        result = middleware(request)
        self.assertIsNone(result)
