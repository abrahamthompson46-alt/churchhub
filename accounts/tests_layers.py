"""Characterization tests for accounts selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts import repositories as repo
from accounts import selectors
from accounts.models import UserActivityLog, UserInvitation
from accounts.permissions import get_manageable_users
from accounts.services import (
    accept_invitation,
    create_invitation,
    log_activity,
)
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class AccountsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        ensure_permission_matrix()
        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save(update_fields=["enforce_subscription_limits"])
        clear_settings_cache()

        cls.denom_a = Denomination.objects.create(
            name="Acct Layer Denom A", code="ALDA", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Acct Layer Denom B", code="ALDB", is_active=True
        )
        cls.conf_a = Conference.objects.create(
            code="ALA1", name="Acct Layer Conf A", denomination=cls.denom_a
        )
        cls.conf_b = Conference.objects.create(
            code="ALB1", name="Acct Layer Conf B", denomination=cls.denom_b
        )
        cls.zone_a = Zone.objects.create(
            conference=cls.conf_a, code="ALZA", name="Acct Zone A"
        )
        cls.zone_b = Zone.objects.create(
            conference=cls.conf_b, code="ALZB", name="Acct Zone B"
        )
        cls.district_a = District.objects.create(
            zone=cls.zone_a, code="ALDA1", name="Acct Dist A"
        )
        cls.district_b = District.objects.create(
            zone=cls.zone_b, code="ALDB1", name="Acct Dist B"
        )
        cls.church_a = Church.objects.create(
            district=cls.district_a, code="ALCHA", name="Acct Church A"
        )
        cls.church_b = Church.objects.create(
            district=cls.district_b, code="ALCHB", name="Acct Church B"
        )

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="acct_layer_admin",
            password="pass12345",
            email="acct_layer_admin@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.secretary = User.objects.create_user(
            username="acct_layer_sec",
            password="pass12345",
            email="acct_layer_sec@test.com",
            role=UserRole.SECRETARY,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.other_secretary = User.objects.create_user(
            username="acct_layer_sec_b",
            password="pass12345",
            email="acct_layer_sec_b@test.com",
            role=UserRole.SECRETARY,
            church=self.church_b,
            denomination=self.denom_b,
        )
        self.platform = User.objects.create_user(
            username="acct_layer_platform",
            password="pass12345",
            email="acct_layer_platform@test.com",
            is_platform_user=True,
            platform_role="SUPPORT",
            is_staff=True,
        )

    def test_selector_username_and_email_lookups(self):
        self.assertTrue(selectors.username_exists_iexact("acct_layer_sec"))
        self.assertTrue(selectors.username_exists_iexact("ACCT_LAYER_SEC"))
        self.assertFalse(selectors.username_exists_iexact("nobody_here"))
        self.assertTrue(selectors.active_email_exists_iexact("acct_layer_sec@test.com"))

    def test_selector_church_isolation_manageable_users(self):
        qs = get_manageable_users(self.secretary)
        self.assertIn(self.secretary, qs)
        self.assertNotIn(self.other_secretary, qs)

    def test_selector_platform_user_isolation(self):
        qs = get_manageable_users(self.admin)
        self.assertNotIn(self.platform, qs)

    def test_selector_denomination_church_lookup(self):
        church = selectors.church_by_pk(self.church_a.pk)
        self.assertEqual(church.pk, self.church_a.pk)
        self.assertEqual(
            selectors.denomination_by_pk(self.denom_a.pk).pk, self.denom_a.pk
        )

    def test_repository_activity_log(self):
        entry = log_activity(
            self.secretary,
            "PROFILE_UPDATE",
            performed_by=self.admin,
            details={"via": "tests_layers"},
        )
        self.assertTrue(
            UserActivityLog.objects.filter(pk=entry.pk, action="PROFILE_UPDATE").exists()
        )

    def test_repository_save_user(self):
        self.secretary.phone = "555-0100"
        repo.save_user(self.secretary, update_fields=["phone"])
        self.secretary.refresh_from_db()
        self.assertEqual(self.secretary.phone, "555-0100")

    def test_invitation_flow_via_service_and_repo(self):
        inv = create_invitation(
            email="invitee@test.com",
            username="invitee_layer",
            role=UserRole.SECRETARY,
            church=self.church_a,
            invited_by=self.admin,
        )
        self.assertTrue(UserInvitation.objects.filter(pk=inv.pk).exists())
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.admin, action="INVITE_SENT"
            ).exists()
        )
        user = accept_invitation(inv, password="Passw0rd!Test", first_name="In", last_name="Vitee")
        self.assertEqual(user.church_id, self.church_a.pk)
        self.assertTrue(
            UserActivityLog.objects.filter(user=user, action="INVITE_ACCEPTED").exists()
        )
        inv.refresh_from_db()
        self.assertTrue(inv.is_accepted)

    def test_pending_invitations_selector_scopes_to_manager_churches(self):
        create_invitation(
            email="local@test.com",
            username="local_invite",
            role=UserRole.MEMBER,
            church=self.church_a,
            invited_by=self.admin,
        )
        create_invitation(
            email="other@test.com",
            username="other_invite",
            role=UserRole.MEMBER,
            church=self.church_b,
            invited_by=self.admin,
        )
        pending = list(
            selectors.pending_invitations_for_manager(
                self.admin, [self.church_a.pk]
            )
        )
        usernames = {i.username for i in pending}
        self.assertIn("local_invite", usernames)
        self.assertNotIn("other_invite", usernames)

    def test_filter_manageable_users_search(self):
        qs = selectors.filter_manageable_users(
            get_manageable_users(self.admin), q="acct_layer_sec"
        )
        self.assertIn(self.secretary, qs)
        self.assertNotIn(self.admin, qs)
