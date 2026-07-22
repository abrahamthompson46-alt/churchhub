"""Characterization tests for giving selectors / repositories layering."""

from datetime import date
from decimal import Decimal
from importlib import import_module

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from giving import repositories as repo
from giving import selectors
from giving.services import (
    can_view_member_giving,
    church_giving_leaders,
    export_giving_statement_table,
    member_giving_lines,
    member_giving_summary,
)
from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.models import Account, Transaction, TransactionLine

User = get_user_model()


class GivingLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(
            name="Giv Layer Denom A", code="glda", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Giv Layer Denom B", code="gldb", is_active=True
        )
        conf_a = Conference.objects.create(
            code="GLCA", name="Giv Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="GLCB", name="Giv Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="GLZA", name="Giv Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="GLZB", name="Giv Zone B")
        dist_a = District.objects.create(zone=zone_a, code="GLDA", name="Giv Dist A")
        dist_b = District.objects.create(zone=zone_b, code="GLDB", name="Giv Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="GLCHA", name="Giv Church A"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="GLCHB", name="Giv Church B"
        )
        from transactions.services import create_default_accounts

        create_default_accounts(cls.church_a)
        create_default_accounts(cls.church_b)
        cls.member_a = Member.objects.create(
            church=cls.church_a,
            first_name="Ada",
            last_name="Giver",
            gender="Female",
        )
        cls.member_b = Member.objects.create(
            church=cls.church_b,
            first_name="Bob",
            last_name="Other",
            gender="Male",
        )
        cls.tithe_a = Account.objects.get(church=cls.church_a, name="Tithe")
        cls.cash_a = Account.objects.get(church=cls.church_a, name="Cash")
        cls.tithe_b = Account.objects.get(church=cls.church_b, name="Tithe")
        cls.cash_b = Account.objects.get(church=cls.church_b, name="Cash")
        cls.year = timezone.now().year

    def setUp(self):
        self.treasury_a = User.objects.create_user(
            username="giv_layer_t_a",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.member_user_b = User.objects.create_user(
            username="giv_layer_m_b",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church_b,
            denomination=self.denom_b,
        )

    def _post_approved_tithe(self, *, church, member, tithe_acct, cash_acct, amount, year=None):
        txn = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=church,
            member=member,
            date=date(year or self.year, 6, 15),
            description="Layer tithe",
            approval_status="APPROVED",
            created_by=self.treasury_a,
        )
        TransactionLine.objects.create(transaction=txn, account=cash_acct, amount=amount)
        TransactionLine.objects.create(
            transaction=txn, account=tithe_acct, amount=-amount
        )
        return txn

    def test_selector_reads_member_lines(self):
        self._post_approved_tithe(
            church=self.church_a,
            member=self.member_a,
            tithe_acct=self.tithe_a,
            cash_acct=self.cash_a,
            amount=Decimal("100.00"),
        )
        lines = selectors.member_giving_lines_qs(self.member_a, year=self.year)
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().account.account_type, "TITHE")

    def test_church_isolation_leaders_and_lines(self):
        self._post_approved_tithe(
            church=self.church_a,
            member=self.member_a,
            tithe_acct=self.tithe_a,
            cash_acct=self.cash_a,
            amount=Decimal("50.00"),
        )
        self._post_approved_tithe(
            church=self.church_b,
            member=self.member_b,
            tithe_acct=self.tithe_b,
            cash_acct=self.cash_b,
            amount=Decimal("75.00"),
        )
        leaders_a = church_giving_leaders(self.church_a, year=self.year)
        leaders_b = church_giving_leaders(self.church_b, year=self.year)
        self.assertEqual(len(leaders_a), 1)
        self.assertEqual(leaders_a[0]["member"].pk, self.member_a.pk)
        self.assertEqual(leaders_b[0]["member"].pk, self.member_b.pk)
        self.assertFalse(
            selectors.member_giving_lines_qs(self.member_a)
            .filter(transaction__church=self.church_b)
            .exists()
        )

    def test_statement_generation_and_aggregation(self):
        self._post_approved_tithe(
            church=self.church_a,
            member=self.member_a,
            tithe_acct=self.tithe_a,
            cash_acct=self.cash_a,
            amount=Decimal("120.00"),
        )
        pending = Transaction.objects.create(
            transaction_type="RECEIPT",
            church=self.church_a,
            member=self.member_a,
            date=date(self.year, 7, 1),
            description="Pending",
            approval_status="PENDING",
            created_by=self.treasury_a,
        )
        TransactionLine.objects.create(
            transaction=pending, account=self.tithe_a, amount=Decimal("-999.00")
        )

        summary = member_giving_summary(self.member_a, year=self.year)
        self.assertEqual(summary["TITHE"], Decimal("120.00"))
        self.assertEqual(summary["total"], Decimal("120.00"))
        self.assertIn("welfare_contributed", summary)
        lines = member_giving_lines(self.member_a, year=self.year)
        self.assertEqual(lines.count(), 1)

    def test_export_behavior(self):
        self._post_approved_tithe(
            church=self.church_a,
            member=self.member_a,
            tithe_acct=self.tithe_a,
            cash_acct=self.cash_a,
            amount=Decimal("10.00"),
        )
        lines = member_giving_lines(self.member_a, year=self.year)
        payload = export_giving_statement_table(lines)
        self.assertEqual(payload["headers"], ["Date", "Reference", "Account", "Amount"])
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0][3], Decimal("10.00"))

    def test_scoped_member_or_404(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.treasury_a
        request.session = {}
        found = selectors.get_scoped_member_or_404(request, self.member_a.pk)
        self.assertEqual(found.pk, self.member_a.pk)
        with self.assertRaises(Http404):
            selectors.get_scoped_member_or_404(request, self.member_b.pk)

    def test_permission_and_repository_read_only(self):
        self.assertTrue(can_view_member_giving(self.treasury_a, self.member_a))
        self.assertFalse(can_view_member_giving(self.member_user_b, self.member_a))
        write_names = [
            name
            for name in dir(repo)
            if not name.startswith("_") and callable(getattr(repo, name, None))
        ]
        self.assertEqual(write_names, [])
        mod = import_module("giving.repositories")
        self.assertIn("read-only", (mod.__doc__ or "").lower())
