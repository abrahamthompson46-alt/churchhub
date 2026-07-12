"""Tests for church scoping utilities."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from church_system.church_scope import filter_by_church
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from transactions.models import Transaction
from transactions.services import open_working_day, record_expense

User = get_user_model()


class ChurchScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Conf", code="CF")
        zone = Zone.objects.create(conference=conf, name="Zone", code="Z1")
        d1 = District.objects.create(zone=zone, name="D1", code="D1")
        d2 = District.objects.create(zone=zone, name="D2", code="D2")
        cls.church_a = Church.objects.create(district=d1, name="Church A", code="CHA")
        cls.church_b = Church.objects.create(district=d2, name="Church B", code="CHB")

        cls.district_pastor = User.objects.create_user(
            username="district_pastor",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church_a,
        )
        cls.treasury_a = User.objects.create_user(
            username="treasury_a",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church_a,
        )
        cls.treasury_b = User.objects.create_user(
            username="treasury_b",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church_b,
        )

    def setUp(self):
        from django.utils import timezone

        open_working_day(self.church_a, timezone.localdate(), self.treasury_a)
        open_working_day(self.church_b, timezone.localdate(), self.treasury_b)
        self.txn_a = record_expense(
            church=self.church_a,
            created_by=self.treasury_a,
            amount=Decimal("10.00"),
        )
        self.txn_b = record_expense(
            church=self.church_b,
            created_by=self.treasury_b,
            amount=Decimal("20.00"),
        )

    def test_filter_by_church_scopes_hierarchy_user_without_active_church(self):
        factory = RequestFactory()
        request = factory.get("/transactions/")
        request.user = self.district_pastor
        request.session = {}

        qs = filter_by_church(Transaction.objects.all(), request)
        church_ids = set(qs.values_list("church_id", flat=True))
        self.assertIn(self.church_a.pk, church_ids)
        self.assertNotIn(self.church_b.pk, church_ids)

    def test_filter_by_church_returns_none_for_user_without_church(self):
        factory = RequestFactory()
        member = User.objects.create_user(
            username="member1",
            password="pass12345",
            role=UserRole.MEMBER,
            church=None,
        )
        request = factory.get("/transactions/")
        request.user = member
        request.session = {}

        qs = filter_by_church(Transaction.objects.all(), request)
        self.assertEqual(qs.count(), 0)

    def test_filter_by_church_scopes_member_to_own_church(self):
        factory = RequestFactory()
        request = factory.get("/transactions/")
        request.user = self.treasury_a
        request.session = {}

        qs = filter_by_church(Transaction.objects.all(), request)
        self.assertEqual(list(qs.values_list("pk", flat=True)), [self.txn_a.pk])
        self.assertNotIn(self.txn_b.pk, qs.values_list("pk", flat=True))
