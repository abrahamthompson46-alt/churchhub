"""Characterization tests for ledger selectors / repositories layering."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from ledger import repositories as repo
from ledger import selectors
from ledger.models import LedgerCategory
from ledger.services import (
    build_entry_draft,
    create_ledger_category,
    post_ledger_entry,
    seed_ledger,
)
from organization.models import Church, Conference, District, Zone
from permissions.checks import can_manage_gl_categories, can_view_ledger
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from remittance.services import ensure_default_policies_for_church
from sitecontrol.models import Denomination
from transactions.models import Account, Transaction
from transactions.services import open_working_day

User = get_user_model()


class LedgerLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denom_a = Denomination.objects.create(
            name="Led Layer Denom A", code="llda", is_active=True
        )
        cls.denom_b = Denomination.objects.create(
            name="Led Layer Denom B", code="lldb", is_active=True
        )
        conf_a = Conference.objects.create(
            code="LLCA", name="Led Conf A", denomination=cls.denom_a
        )
        conf_b = Conference.objects.create(
            code="LLCB", name="Led Conf B", denomination=cls.denom_b
        )
        zone_a = Zone.objects.create(conference=conf_a, code="LLZA", name="Led Zone A")
        zone_b = Zone.objects.create(conference=conf_b, code="LLZB", name="Led Zone B")
        dist_a = District.objects.create(zone=zone_a, code="LLDA", name="Led Dist A")
        dist_b = District.objects.create(zone=zone_b, code="LLDB", name="Led Dist B")
        cls.church_a = Church.objects.create(
            district=dist_a, code="LLCHA", name="Led Church A"
        )
        cls.church_b = Church.objects.create(
            district=dist_b, code="LLCHB", name="Led Church B"
        )
        seed_ledger(cls.church_a)
        seed_ledger(cls.church_b)
        ensure_default_policies_for_church(cls.church_a)
        ensure_default_policies_for_church(cls.church_b)

    def setUp(self):
        self.treasury_a = User.objects.create_user(
            username="led_layer_t_a",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church_a,
            denomination=self.denom_a,
        )
        self.member_user = User.objects.create_user(
            username="led_layer_m_a",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church_a,
            denomination=self.denom_a,
        )
        open_working_day(self.church_a, timezone.localdate(), self.treasury_a)

    def test_selector_reads_categories(self):
        qs = selectors.categories_for_type_qs(self.church_a, "RECEIPT")
        self.assertTrue(qs.filter(code="REC_TITHE_CASH").exists())
        self.assertFalse(qs.filter(transaction_type="EXPENSE").exists())
        summary = selectors.ledger_summary_counts(self.church_a)
        self.assertGreater(summary["category_count"], 0)
        self.assertGreater(summary["account_count"], 0)

    def test_church_isolation_categories_and_entries(self):
        cat_a = selectors.categories_for_type_qs(self.church_a, "RECEIPT").get(
            code="REC_INCOME_CASH"
        )
        cat_b = selectors.categories_for_type_qs(self.church_b, "RECEIPT").get(
            code="REC_INCOME_CASH"
        )
        self.assertNotEqual(cat_a.pk, cat_b.pk)
        self.assertEqual(cat_a.church_id, self.church_a.pk)

        draft = build_entry_draft(cat_a, Decimal("10.00"), "Isolation", None)
        post_ledger_entry(self.church_a, self.treasury_a, draft)

        entries_a = selectors.ledger_entries_qs(self.church_a)
        entries_b = selectors.ledger_entries_qs(self.church_b)
        self.assertEqual(entries_a.count(), 1)
        self.assertEqual(entries_b.count(), 0)
        self.assertFalse(entries_b.filter(pk=entries_a.first().pk).exists())

    def test_denomination_isolation_via_church_scope(self):
        """Categories are church-scoped; denom wall is church ownership."""
        with self.assertRaises(Http404):
            selectors.get_category_or_404(
                self.church_b,
                selectors.categories_for_church_qs(self.church_a).first().pk,
            )
        with self.assertRaises(Http404):
            selectors.get_account_or_404(
                self.church_b,
                selectors.accounts_for_church_qs(self.church_a).first().pk,
            )

    def test_permission_checks(self):
        self.assertTrue(can_view_ledger(self.treasury_a))
        self.assertTrue(can_manage_gl_categories(self.treasury_a))
        self.assertFalse(can_manage_gl_categories(self.member_user))

    def test_repository_writes(self):
        cash = Account.objects.get(church=self.church_a, name="Cash")
        income = Account.objects.get(church=self.church_a, name="General Income")
        before = selectors.category_code_exists(self.church_a, "REC_LAYER_TEST")
        self.assertFalse(before)

        category = create_ledger_category(
            self.church_a,
            self.treasury_a,
            code="REC_LAYER_TEST",
            name="Layer Test Receipt",
            transaction_type="RECEIPT",
            default_debit_account=cash,
            default_credit_account=income,
        )
        self.assertTrue(selectors.category_code_exists(self.church_a, "REC_LAYER_TEST"))
        self.assertEqual(category.church_id, self.church_a.pk)

        category.name = "Layer Test Updated"
        repo.save_category(category)
        category.refresh_from_db()
        self.assertEqual(category.name, "Layer Test Updated")

    def test_transaction_integration(self):
        cat = LedgerCategory.objects.get(
            church=self.church_a, code="REC_INCOME_CASH"
        )
        draft = build_entry_draft(cat, Decimal("42.00"), "Txn integration", None)
        trx = post_ledger_entry(self.church_a, self.treasury_a, draft)
        self.assertIsInstance(trx, Transaction)
        self.assertEqual(trx.church_id, self.church_a.pk)
        self.assertEqual(trx.ledger_category_id, cat.pk)
        self.assertEqual(trx.approval_status, "PENDING")
        self.assertTrue(
            selectors.ledger_entries_qs(self.church_a, category=cat)
            .filter(pk=trx.pk)
            .exists()
        )
