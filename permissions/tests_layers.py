"""Characterization tests for permissions selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from organization.models import Church, Conference, District, Zone
from permissions import repositories as repo
from permissions import selectors
from permissions.models import Permission, PermissionAuditLog, PermissionOverride, RolePermission
from permissions.org_scope import church_in_user_scope
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches
from permissions.services import (
    create_override,
    ensure_permission_matrix,
    get_effective_permissions,
    log_permission_audit,
    user_has_permission,
)
from permissions.superadmin import is_superadmin
from sitecontrol.models import Denomination

User = get_user_model()


class PermissionsLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()

        cls.denom_a = Denomination.objects.create(
            name="Perm Layer Denom A", code="PLDA", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Perm Layer Denom B", code="PLDB", is_active=True
        )
        cls.conf_a = Conference.objects.create(
            code="PLA1", name="Perm Layer Conf A", denomination=cls.denom_a
        )
        cls.conf_b = Conference.objects.create(
            code="PLB1", name="Perm Layer Conf B", denomination=cls.denom_b
        )
        cls.zone_a = Zone.objects.create(
            conference=cls.conf_a, code="PLZA", name="Perm Layer Zone A"
        )
        cls.zone_b = Zone.objects.create(
            conference=cls.conf_b, code="PLZB", name="Perm Layer Zone B"
        )
        cls.district_a = District.objects.create(
            zone=cls.zone_a, code="PLDA1", name="Perm Layer Dist A"
        )
        cls.district_b = District.objects.create(
            zone=cls.zone_b, code="PLDB1", name="Perm Layer Dist B"
        )
        cls.church_a = Church.objects.create(
            district=cls.district_a, code="PLCHA", name="Perm Layer Church A"
        )
        cls.church_b = Church.objects.create(
            district=cls.district_b, code="PLCHB", name="Perm Layer Church B"
        )

    def setUp(self):
        self.secretary = User.objects.create_user(
            username="perm_layer_sec",
            password="pass12345",
            email="perm_layer_sec@test.com",
            role=UserRole.SECRETARY,
            church=self.church_a,
        )
        self.other_secretary = User.objects.create_user(
            username="perm_layer_sec_b",
            password="pass12345",
            email="perm_layer_sec_b@test.com",
            role=UserRole.SECRETARY,
            church=self.church_b,
        )
        self.admin = User.objects.create_superuser(
            username="perm_layer_admin",
            password="pass12345",
            email="perm_layer_admin@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church_a,
        )

    def test_selector_active_permissions_ordered(self):
        qs = selectors.active_permissions_ordered()
        self.assertTrue(qs.filter(codename="view_members").exists())
        self.assertTrue(all(p.is_active for p in qs[:20]))

    def test_effective_permission_resolution_for_role(self):
        effective = get_effective_permissions(self.secretary)
        self.assertIn("view_members", effective)
        self.assertTrue(user_has_permission(self.secretary, "view_members"))

    def test_override_deny_precedes_matrix_grant(self):
        perm = Permission.objects.get(codename="view_members")
        self.assertTrue(user_has_permission(self.secretary, "view_members"))
        create_override(
            user=self.secretary,
            permission=perm,
            granted=False,
            reason="layer deny",
            created_by=self.admin,
        )
        self.assertFalse(user_has_permission(self.secretary, "view_members"))

    def test_override_grant_precedes_matrix_deny(self):
        perm = Permission.objects.get(codename="manage_permissions")
        self.assertFalse(user_has_permission(self.secretary, "manage_permissions"))
        create_override(
            user=self.secretary,
            permission=perm,
            granted=True,
            reason="layer grant",
            created_by=self.admin,
        )
        self.assertTrue(user_has_permission(self.secretary, "manage_permissions"))

    def test_church_isolation_manageable_churches(self):
        qs = get_manageable_churches(self.secretary)
        self.assertIn(self.church_a, qs)
        self.assertNotIn(self.church_b, qs)

    def test_church_in_user_scope_cross_church_denied(self):
        self.assertTrue(church_in_user_scope(self.secretary, self.church_a))
        self.assertFalse(church_in_user_scope(self.secretary, self.church_b))

    def test_denomination_isolation_via_selectors(self):
        qs_a = selectors.churches_for_denomination(
            selectors.active_churches_base_qs(), self.denom_a
        )
        self.assertIn(self.church_a, qs_a)
        self.assertNotIn(self.church_b, qs_a)

    def test_repository_audit_create(self):
        entry = log_permission_audit(
            "MATRIX_UPDATE",
            performed_by=self.admin,
            target_user=self.secretary,
            details={"via": "tests_layers"},
        )
        self.assertTrue(
            PermissionAuditLog.objects.filter(pk=entry.pk, action="MATRIX_UPDATE").exists()
        )

    def test_repository_save_and_delete_override(self):
        perm = Permission.objects.get(codename="export_members")
        override = PermissionOverride(
            user=self.secretary,
            permission=perm,
            granted=True,
            reason="repo path",
            created_by=self.admin,
        )
        repo.save_override(override)
        self.assertTrue(PermissionOverride.objects.filter(pk=override.pk).exists())
        repo.delete_override(override)
        self.assertFalse(PermissionOverride.objects.filter(pk=override.pk).exists())

    def test_repository_role_permission_update(self):
        perm = Permission.objects.get(codename="view_reports")
        rp, _ = repo.get_or_create_role_permission(
            role=UserRole.MEMBER,
            permission=perm,
            defaults={"granted": False},
        )
        rp.granted = True
        repo.save_role_permission(rp, update_fields=["granted", "updated_at"])
        rp.refresh_from_db()
        self.assertTrue(rp.granted)

    def test_superadmin_bypasses_matrix(self):
        self.assertTrue(is_superadmin(self.admin))
        self.assertTrue(user_has_permission(self.admin, "manage_permissions"))

    def test_selector_role_permission_for(self):
        rp = selectors.role_permission_for(UserRole.SECRETARY, "view_members")
        self.assertEqual(rp.permission.codename, "view_members")
