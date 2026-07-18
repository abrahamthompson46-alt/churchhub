"""Subtree organization scope tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from organization.models import Church, Conference, District, Zone
from permissions.org_scope import OrgScopeLevel, apply_org_scope, church_in_user_scope
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches
from sitecontrol.models import Denomination

User = get_user_model()


class OrgScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.denom = Denomination.objects.create(name="SDA", code="SDA", is_active=True)
        cls.conf = Conference.objects.create(name="Ghana", code="GH", denomination=cls.denom)
        cls.zone = Zone.objects.create(name="Kumasi", code="KU", conference=cls.conf)
        cls.district_a = District.objects.create(name="Bantama", code="BA", zone=cls.zone)
        cls.district_b = District.objects.create(name="Ashanti", code="AS", zone=cls.zone)
        cls.church_a = Church.objects.create(
            name="Church A", code="CA", district=cls.district_a, financials_provisioned=True
        )
        cls.church_b = Church.objects.create(
            name="Church B", code="CB", district=cls.district_a, financials_provisioned=True
        )
        cls.church_other = Church.objects.create(
            name="Other District Church",
            code="OD",
            district=cls.district_b,
            financials_provisioned=True,
        )

    def test_district_admin_sees_only_own_district_churches(self):
        john = User.objects.create_user(
            username="john_da",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church_a,
            denomination=self.denom,
        )
        apply_org_scope(
            john,
            role=UserRole.DISTRICT_PASTOR,
            scope_level=OrgScopeLevel.DISTRICT,
            church=self.church_a,
            district=self.district_a,
            denomination=self.denom,
        )
        john.save()

        manageable = set(get_manageable_churches(john).values_list("pk", flat=True))
        self.assertIn(self.church_a.pk, manageable)
        self.assertIn(self.church_b.pk, manageable)
        self.assertNotIn(self.church_other.pk, manageable)
        self.assertTrue(church_in_user_scope(john, self.church_a))
        self.assertFalse(church_in_user_scope(john, self.church_other))

    def test_church_treasurer_sees_only_home_church(self):
        mary = User.objects.create_user(
            username="mary_tr",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church_a,
            denomination=self.denom,
            scope_level=OrgScopeLevel.CHURCH,
        )
        manageable = list(get_manageable_churches(mary))
        self.assertEqual(manageable, [self.church_a])

    def test_conference_admin_sees_all_conference_churches(self):
        peter = User.objects.create_user(
            username="peter_ca",
            password="pass12345",
            role=UserRole.CONFERENCE_ADMIN,
            denomination=self.denom,
        )
        apply_org_scope(
            peter,
            role=UserRole.CONFERENCE_ADMIN,
            scope_level=OrgScopeLevel.CONFERENCE,
            conference=self.conf,
            denomination=self.denom,
            church=self.church_a,
        )
        peter.save()
        manageable = set(get_manageable_churches(peter).values_list("pk", flat=True))
        self.assertEqual(
            manageable,
            {self.church_a.pk, self.church_b.pk, self.church_other.pk},
        )
