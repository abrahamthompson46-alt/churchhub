"""Settlement desk scoping for hierarchy treasurers."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from organization.models import Church, Conference, District, Zone
from permissions.org_scope import OrgScopeLevel, apply_org_scope
from permissions.roles import UserRole
from remittance import selectors
from remittance.models import SettlementBatch
from remittance.services import RemittancePolicyError, create_settlement_draft
from remittance.settlement_desk import (
    draftable_hierarchy_from_units,
    list_settlement_desks,
    user_can_access_settlement_batch,
)
from sitecontrol.models import Denomination

User = get_user_model()


class SettlementDeskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.denom = Denomination.objects.create(name="Desk Denom", code="SD", is_active=True)
        cls.conf = Conference.objects.create(name="Desk Conf", code="DC", denomination=cls.denom)
        zone = Zone.objects.create(name="Desk Zone", code="DZ", conference=cls.conf)
        cls.district = District.objects.create(name="Desk District", code="DD", zone=zone)
        cls.church = Church.objects.create(
            name="Desk Church",
            code="DCH",
            district=cls.district,
            financials_provisioned=True,
        )
        cls.other_district = District.objects.create(name="Other D", code="OD", zone=zone)
        cls.other_church = Church.objects.create(
            name="Other Church",
            code="OCH",
            district=cls.other_district,
            financials_provisioned=True,
        )

    def test_district_desk_lists_manageable_batches(self):
        user = User.objects.create_user(
            username="district_desk",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
            denomination=self.denom,
        )
        apply_org_scope(
            user,
            role=UserRole.DISTRICT_PASTOR,
            scope_level=OrgScopeLevel.DISTRICT,
            church=self.church,
            district=self.district,
            denomination=self.denom,
        )
        desks = list_settlement_desks(user, church=self.church)
        self.assertEqual(len(desks), 1)
        self.assertEqual(desks[0].unit_type, "DISTRICT")

        SettlementBatch.objects.create(
            offering_type="TITHE",
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            to_unit_type="DISTRICT",
            to_unit_id=self.district.pk,
            period_start="2026-01-01",
            period_end="2026-01-31",
            gross_received=Decimal("100.00"),
            status="POSTED",
        )
        SettlementBatch.objects.create(
            offering_type="TITHE",
            from_unit_type="CHURCH",
            from_unit_id=self.other_church.pk,
            to_unit_type="DISTRICT",
            to_unit_id=self.other_district.pk,
            period_start="2026-01-01",
            period_end="2026-01-31",
            gross_received=Decimal("50.00"),
            status="POSTED",
        )

        batches = selectors.settlement_desk_batches(
            desk_type="DISTRICT",
            desk_id=self.district.pk,
            church_ids=[self.church.pk],
            tab="churches",
        )
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertTrue(user_can_access_settlement_batch(user, batch, church=self.church))

        out_of_scope = SettlementBatch.objects.get(from_unit_id=self.other_church.pk)
        self.assertFalse(
            user_can_access_settlement_batch(user, out_of_scope, church=self.church)
        )

    def test_settlement_desk_view_for_district_user(self):
        user = User.objects.create_user(
            username="district_view",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=self.church,
            denomination=self.denom,
        )
        apply_org_scope(
            user,
            role=UserRole.DISTRICT_PASTOR,
            scope_level=OrgScopeLevel.DISTRICT,
            church=self.church,
            district=self.district,
            denomination=self.denom,
        )
        self.client.login(username="district_view", password="pass12345")
        url = reverse("remittance:settlements")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Settlement Desk")

    def test_conference_desk_drafts_from_district_when_no_union(self):
        from django.utils import timezone

        user = User.objects.create_user(
            username="conf_desk",
            password="pass12345",
            role=UserRole.CONFERENCE_ADMIN,
            church=self.church,
            denomination=self.denom,
        )
        apply_org_scope(
            user,
            role=UserRole.CONFERENCE_ADMIN,
            scope_level=OrgScopeLevel.CONFERENCE,
            church=self.church,
            conference=self.conf,
            denomination=self.denom,
        )
        user.save()
        desks = list_settlement_desks(user, church=self.church)
        self.assertEqual(desks[0].unit_type, "CONFERENCE")
        units = draftable_hierarchy_from_units(user, desks[0], church=self.church)
        self.assertTrue(any(row[0] == "DISTRICT" for row in units))
        self.assertFalse(any(row[0] == "CONFERENCE" for row in units))

        today = timezone.localdate()
        with self.assertRaises(RemittancePolicyError) as ctx:
            create_settlement_draft(
                "CONFERENCE",
                self.conf.pk,
                "TITHE",
                today.replace(day=1),
                today,
                user,
            )
        self.assertIn("not linked to a union", str(ctx.exception))

        self.client.login(username="conf_desk", password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        resp = self.client.get(reverse("remittance:settlements"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Create hierarchy draft")
        self.assertContains(resp, self.district.name)
