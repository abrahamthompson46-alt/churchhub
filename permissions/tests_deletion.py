"""Permission override delete audit regression."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from organization.models import Church, Conference, District, Zone
from permissions.models import Permission, PermissionAuditLog, PermissionOverride
from permissions.roles import UserRole
from permissions.services import create_override, ensure_permission_matrix
from sitecontrol.models import SiteSettings

User = get_user_model()


class PermissionOverrideDeleteAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        conf = Conference.objects.create(name="Perm Conf", code="PERC")
        zone = Zone.objects.create(conference=conf, name="Perm Z", code="PERZ")
        dist = District.objects.create(zone=zone, name="Perm D", code="PERD")
        cls.church = Church.objects.create(district=dist, name="Perm Church", code="PERCH")
        cls.admin = User.objects.create_superuser(
            username="perm_super_del",
            password="pass12345",
            email="perm-del@test.com",
            role=UserRole.SUPER_ADMIN,
            church=cls.church,
        )
        cls.target = User.objects.create_user(
            username="perm_target_del",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )

    def test_override_delete_writes_permission_audit(self):
        perm = Permission.objects.get(codename="export_members")
        override = create_override(self.target, perm, granted=False, reason="test")
        client = Client()
        client.login(username="perm_super_del", password="pass12345")
        response = client.post(
            reverse("permissions:override_delete", kwargs={"pk": override.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PermissionOverride.objects.filter(pk=override.pk).exists())
        self.assertTrue(
            PermissionAuditLog.objects.filter(action="OVERRIDE_DELETE").exists()
        )
