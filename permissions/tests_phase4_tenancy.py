"""CH-SEC-L1 — unanchored institution superadmin fail-closed tenancy."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches, get_manageable_users
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination


class TenantFailClosedL1Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(code="l1-a", name="L1 Denom A")
        cls.denom_b = Denomination.objects.create(code="l1-b", name="L1 Denom B")
        conf_a = Conference.objects.create(
            name="L1 Conf A", code="L1CA", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            name="L1 Conf B", code="L1CB", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="L1ZA", name="Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="L1ZB", name="Zone B")
        dist_a = District.objects.create(zone=zone_a, code="L1DA", name="Dist A")
        dist_b = District.objects.create(zone=zone_b, code="L1DB", name="Dist B")
        cls.church_a = Church.objects.create(district=dist_a, code="L1CHA", name="Church A")
        cls.church_b = Church.objects.create(district=dist_b, code="L1CHB", name="Church B")

        cls.anchored_sa = User.objects.create_user(
            username="l1_anchored_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            denomination=cls.denom_a,
        )
        cls.church_anchored_sa = User.objects.create_user(
            username="l1_church_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=cls.church_a,
            denomination=cls.denom_a,
        )
        # Legacy unanchored SUPER_ADMIN row (bypass save validation via update).
        cls.unanchored_sa = User.objects.create_user(
            username="l1_unanchored_sa",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church_a,
        )
        User.objects.filter(pk=cls.unanchored_sa.pk).update(
            role=UserRole.SUPER_ADMIN,
            denomination_id=None,
            church_id=None,
            is_superuser=True,
            is_platform_user=False,
        )
        cls.unanchored_sa.refresh_from_db()

        cls.platform_unanchored = User.objects.create_user(
            username="l1_plat_unanchored",
            password="pass12345",
            is_platform_user=True,
            platform_role="READONLY",
            is_superuser=False,
        )
        cls.platform_owner = User.objects.create_user(
            username="l1_plat_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
            is_superuser=False,
        )

    def test_unanchored_superadmin_manageable_churches_empty(self):
        self.assertFalse(get_manageable_churches(self.unanchored_sa).exists())

    def test_unanchored_superadmin_manageable_users_self_only(self):
        qs = get_manageable_users(self.unanchored_sa)
        self.assertEqual(list(qs.values_list("pk", flat=True)), [self.unanchored_sa.pk])

    def test_unanchored_platform_user_not_institution_superadmin_scope(self):
        # Platform operators are excluded from is_superadmin; empty institution scope.
        self.assertFalse(get_manageable_churches(self.platform_unanchored).exists())
        self.assertFalse(get_manageable_churches(self.platform_owner).exists())

    def test_anchored_superadmin_same_denomination_only(self):
        ids = set(get_manageable_churches(self.anchored_sa).values_list("pk", flat=True))
        self.assertEqual(ids, {self.church_a.pk})
        ids2 = set(
            get_manageable_churches(self.church_anchored_sa).values_list("pk", flat=True)
        )
        self.assertEqual(ids2, {self.church_a.pk})

    def test_anchored_superadmin_cross_denomination_denied(self):
        self.assertNotIn(
            self.church_b.pk,
            get_manageable_churches(self.anchored_sa).values_list("pk", flat=True),
        )

    def test_save_rejects_unanchored_super_admin(self):
        user = User(
            username="l1_bad_sa",
            role=UserRole.SUPER_ADMIN,
            is_platform_user=False,
        )
        user.set_password("pass12345")
        with self.assertRaises(ValidationError):
            user.save()

    def test_save_allows_anchored_super_admin(self):
        user = User(
            username="l1_ok_sa",
            role=UserRole.SUPER_ADMIN,
            denomination=self.denom_a,
            is_platform_user=False,
        )
        user.set_password("pass12345")
        user.save()
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
