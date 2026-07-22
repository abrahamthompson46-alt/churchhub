"""P0-12 regression: remittance unit pickers must be tenant- and RBAC-scoped."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from organization.models import Church, Conference, District, Zone
from permissions.org_scope import OrgScopeLevel, apply_org_scope
from permissions.roles import UserRole
from remittance.models import RemittancePolicyAuditLog
from remittance.services import (
    RemittancePolicyError,
    get_unit_choices,
    save_remittance_policy,
    unit_in_user_scope,
)
from sitecontrol.models import Denomination
from sitecontrol.rbac import ROLE_OWNER, ROLE_SUPPORT

User = get_user_model()


class RemittanceUnitScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.denom_a = Denomination.objects.create(name="Denom A", code="DA", is_active=True)
        cls.denom_b = Denomination.objects.create(name="Denom B", code="DB", is_active=True)

        cls.conf_a = Conference.objects.create(
            name="Conf A", code="CA", denomination=cls.denom_a
        )
        cls.conf_b = Conference.objects.create(
            name="Conf B", code="CB", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(name="Zone A", code="ZA", conference=cls.conf_a)
        zone_b = Zone.objects.create(name="Zone B", code="ZB", conference=cls.conf_b)

        cls.district_a1 = District.objects.create(name="District A1", code="DA1", zone=zone_a)
        cls.district_a2 = District.objects.create(name="District A2", code="DA2", zone=zone_a)
        cls.district_b = District.objects.create(name="District B", code="DB1", zone=zone_b)

        cls.church_a1 = Church.objects.create(
            name="Church A1",
            code="CHA1",
            district=cls.district_a1,
            financials_provisioned=True,
        )
        cls.church_a2 = Church.objects.create(
            name="Church A2",
            code="CHA2",
            district=cls.district_a1,
            financials_provisioned=True,
        )
        cls.church_a3 = Church.objects.create(
            name="Church A3",
            code="CHA3",
            district=cls.district_a2,
            financials_provisioned=True,
        )
        cls.church_b = Church.objects.create(
            name="Church B",
            code="CHB1",
            district=cls.district_b,
            financials_provisioned=True,
        )

    def _ids(self, choices):
        return {choice_id for choice_id, _label in choices}

    def test_church_user_cannot_view_another_church_units(self):
        user = User.objects.create_user(
            username="church_tr",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church_a1,
            denomination=self.denom_a,
            scope_level=OrgScopeLevel.CHURCH,
        )
        church_ids = self._ids(get_unit_choices("CHURCH", user=user, church=self.church_a1))
        self.assertEqual(church_ids, {str(self.church_a1.pk)})
        self.assertNotIn(str(self.church_a2.pk), church_ids)
        self.assertNotIn(str(self.church_b.pk), church_ids)
        self.assertFalse(
            unit_in_user_scope(user, "CHURCH", self.church_a2.pk, church=self.church_a1)
        )

    def test_district_user_sees_only_permitted_churches(self):
        user = User.objects.create_user(
            username="district_pastor",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church_a1,
            denomination=self.denom_a,
        )
        apply_org_scope(
            user,
            role=UserRole.DISTRICT_PASTOR,
            scope_level=OrgScopeLevel.DISTRICT,
            church=self.church_a1,
            district=self.district_a1,
            denomination=self.denom_a,
        )
        user.save()

        church_ids = self._ids(get_unit_choices("CHURCH", user=user))
        self.assertEqual(church_ids, {str(self.church_a1.pk), str(self.church_a2.pk)})
        self.assertNotIn(str(self.church_a3.pk), church_ids)

        district_ids = self._ids(get_unit_choices("DISTRICT", user=user))
        self.assertEqual(district_ids, {str(self.district_a1.pk)})
        self.assertNotIn(str(self.district_a2.pk), district_ids)

    def test_conference_user_sees_only_conference_hierarchy(self):
        user = User.objects.create_user(
            username="conf_admin",
            password="pass12345",
            role=UserRole.CONFERENCE_ADMIN,
            denomination=self.denom_a,
        )
        apply_org_scope(
            user,
            role=UserRole.CONFERENCE_ADMIN,
            scope_level=OrgScopeLevel.CONFERENCE,
            conference=self.conf_a,
            denomination=self.denom_a,
            church=self.church_a1,
        )
        user.save()

        church_ids = self._ids(get_unit_choices("CHURCH", user=user))
        self.assertEqual(
            church_ids,
            {str(self.church_a1.pk), str(self.church_a2.pk), str(self.church_a3.pk)},
        )
        self.assertNotIn(str(self.church_b.pk), church_ids)

        conf_ids = self._ids(get_unit_choices("CONFERENCE", user=user))
        self.assertEqual(conf_ids, {str(self.conf_a.pk)})
        self.assertNotIn(str(self.conf_b.pk), conf_ids)

        district_ids = self._ids(get_unit_choices("DISTRICT", user=user))
        self.assertEqual(
            district_ids,
            {str(self.district_a1.pk), str(self.district_a2.pk)},
        )
        self.assertNotIn(str(self.district_b.pk), district_ids)

    def test_cross_denomination_units_never_appear(self):
        user = User.objects.create_user(
            username="denom_a_user",
            password="pass12345",
            role=UserRole.CONFERENCE_ADMIN,
            denomination=self.denom_a,
        )
        apply_org_scope(
            user,
            role=UserRole.CONFERENCE_ADMIN,
            scope_level=OrgScopeLevel.CONFERENCE,
            conference=self.conf_a,
            denomination=self.denom_a,
            church=self.church_a1,
        )
        user.save()

        for unit_type, foreign_id in (
            ("CHURCH", self.church_b.pk),
            ("DISTRICT", self.district_b.pk),
            ("CONFERENCE", self.conf_b.pk),
        ):
            ids = self._ids(get_unit_choices(unit_type, user=user, denomination=self.denom_a))
            self.assertNotIn(str(foreign_id), ids, msg=unit_type)

        with self.assertRaises(RemittancePolicyError):
            save_remittance_policy(
                {
                    "offering_type": "TITHE",
                    "application_scope": "GROSS_COLLECTION",
                    "unit_type": "CHURCH",
                    "unit_id": str(self.church_b.pk),
                    "retain_percent": "50",
                    "remit_percent": "50",
                    "effective_from": "2026-01-01",
                    "is_active": True,
                    "notes": "",
                },
                user,
                church=self.church_a1,
            )
        self.assertTrue(
            RemittancePolicyAuditLog.objects.filter(action="SCOPE_VIOLATION").exists()
        )

    def test_platform_owner_retains_expected_access(self):
        owner = User.objects.create_user(
            username="platform_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role=ROLE_OWNER,
        )
        all_church_ids = self._ids(get_unit_choices("CHURCH", user=owner))
        self.assertIn(str(self.church_a1.pk), all_church_ids)
        self.assertIn(str(self.church_b.pk), all_church_ids)

        scoped = self._ids(
            get_unit_choices("CHURCH", user=owner, denomination=self.denom_a)
        )
        self.assertIn(str(self.church_a1.pk), scoped)
        self.assertNotIn(str(self.church_b.pk), scoped)

    def test_platform_scoped_operator_limited_to_managed_denomination(self):
        operator = User.objects.create_user(
            username="platform_op",
            password="pass12345",
            is_platform_user=True,
            platform_role=ROLE_SUPPORT,
        )
        operator.managed_denominations.add(self.denom_a)

        ids = self._ids(get_unit_choices("CHURCH", user=operator))
        self.assertIn(str(self.church_a1.pk), ids)
        self.assertNotIn(str(self.church_b.pk), ids)

        denied = self._ids(
            get_unit_choices("CHURCH", user=operator, denomination=self.denom_b)
        )
        self.assertEqual(denied, set())

    def test_unauthenticated_or_missing_user_returns_empty(self):
        self.assertEqual(get_unit_choices("CHURCH", church=self.church_a1), [])
        self.assertEqual(get_unit_choices("CHURCH", user=None), [])
