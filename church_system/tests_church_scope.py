"""Regression: active church resolution and member visibility scope."""

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from church_system.church_scope import get_active_church
from members.models import Gender, Member, MembershipStatus
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.models import Denomination

User = get_user_model()


class ActiveChurchScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        denom = Denomination.objects.create(name="Scope Denom", code="SCPD", is_active=True)
        conf = Conference.objects.create(name="Conf", code="SC", denomination=denom)
        zone = Zone.objects.create(name="Z", code="ZSC", conference=conf)
        d1 = District.objects.create(name="D1", code="D1SC", zone=zone)
        d2 = District.objects.create(name="D2", code="D2SC", zone=zone)
        cls.church_a = Church.objects.create(name="Church A", code="CHA", district=d1)
        cls.church_b = Church.objects.create(name="Church B", code="CHB", district=d2)
        cls.super = User.objects.create_user(
            username="super_scope",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=cls.church_a,
            denomination=denom,
            is_superuser=True,
        )
        Member.objects.create(
            church=cls.church_a,
            first_name="Ada",
            last_name="Member",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
            email="ada@example.com",
        )

    def test_stale_session_church_falls_back_to_home_church(self):
        factory = RequestFactory()
        request = factory.get("/members/")
        request.user = self.super
        request.session = {"current_church_id": str(uuid.uuid4())}
        church = get_active_church(request)
        self.assertEqual(church, self.church_a)
        self.assertNotIn("current_church_id", request.session)

    def test_super_admin_sees_inactive_church_in_manageable_scope(self):
        from permissions.scoping import get_manageable_churches

        self.church_a.is_active = False
        self.church_a.save(update_fields=["is_active"])
        ids = set(get_manageable_churches(self.super).values_list("pk", flat=True))
        self.assertIn(self.church_a.pk, ids)
