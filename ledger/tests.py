"""Tests for ledger app — seed, remittance posting, confirm workflow."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from ledger.models import LedgerCategory
from ledger.services import build_entry_draft, post_ledger_entry, seed_ledger
from members.models import Member
from organization.models import Church, Conference, District, Zone
from remittance.services import ensure_default_policies_for_church
from transactions.models import Account, Transaction, TransactionLine
from transactions.services import WorkingDayClosedError, open_working_day

User = get_user_model()


class LedgerTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="LC", name="Ledger Conference")
        cls.zone = Zone.objects.create(conference=cls.conference, code="LZ", name="Ledger Zone")
        cls.district = District.objects.create(zone=cls.zone, code="LD", name="Ledger District")
        cls.church = Church.objects.create(district=cls.district, code="LCH", name="Ledger Church")
        seed_ledger(cls.church)
        ensure_default_policies_for_church(cls.church)
        cls.treasury = User.objects.create_user(
            username="ledger_t",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="ledger_p",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Tithe",
            gender="F",
        )

    def setUp(self):
        open_working_day(self.church, timezone.localdate(), self.pastor)


class SeedTests(LedgerTestMixin, TestCase):
    def test_seed_creates_categories_per_type(self):
        self.assertGreater(
            LedgerCategory.objects.filter(church=self.church, transaction_type="RECEIPT").count(),
            5,
        )
        self.assertGreater(
            LedgerCategory.objects.filter(church=self.church, transaction_type="EXPENSE").count(),
            5,
        )
        self.assertGreater(
            LedgerCategory.objects.filter(church=self.church, transaction_type="TRANSFER").count(),
            2,
        )

    def test_category_has_debit_and_credit(self):
        cat = LedgerCategory.objects.filter(church=self.church, code="REC_TITHE_CASH").first()
        self.assertIsNotNone(cat)
        self.assertNotEqual(cat.default_debit_account_id, cat.default_credit_account_id)

    def test_remittance_transfer_templates_clear_payables(self):
        tithe = LedgerCategory.objects.get(church=self.church, code="TRF_TITHE_REMIT")
        combined = LedgerCategory.objects.get(church=self.church, code="TRF_COMBINED_REMIT")
        conf = LedgerCategory.objects.get(church=self.church, code="TRF_TITHE_REMIT_CONF")
        union = LedgerCategory.objects.get(church=self.church, code="TRF_TITHE_REMIT_UNION")
        self.assertEqual(tithe.default_debit_account.name, "Tithe Remittance Payable")
        self.assertEqual(combined.default_debit_account.name, "Combined Remittance Payable")
        self.assertEqual(tithe.default_credit_account.name, "District Tithe Remittance")
        self.assertEqual(combined.default_credit_account.name, "District Combined Remittance")
        self.assertEqual(conf.default_credit_account.name, "Conference Tithe Remittance")
        self.assertEqual(union.default_credit_account.name, "Union Tithe Remittance")
        self.assertNotEqual(tithe.default_credit_account.name, "Main Bank")
        # Remittance transfers must never credit Main Bank
        for code in (
            "TRF_TITHE_REMIT",
            "TRF_TITHE_REMIT_CONF",
            "TRF_TITHE_REMIT_UNION",
            "TRF_COMBINED_REMIT",
            "TRF_COMBINED_REMIT_CONF",
            "TRF_COMBINED_REMIT_UNION",
        ):
            cat = LedgerCategory.objects.get(church=self.church, code=code)
            self.assertNotEqual(cat.default_credit_account.name, "Main Bank")
            self.assertNotEqual(cat.default_credit_account.account_type, "BANK")

    def test_remittance_accounts_have_stable_codes(self):
        from transactions.account_codes import ACCOUNT_CODE_BY_NAME, get_account_by_code

        for name, code in ACCOUNT_CODE_BY_NAME.items():
            if "Remittance" not in name or "Payable" in name:
                continue
            acct = Account.objects.filter(church=self.church, name=name).first()
            self.assertIsNotNone(acct, name)
            self.assertEqual(acct.code, code)
            self.assertEqual(get_account_by_code(self.church, code).pk, acct.pk)

class PostingTests(LedgerTestMixin, TestCase):
    def test_post_ledger_entry_balanced(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_COMBINED_CASH")
        draft = build_entry_draft(cat, Decimal("250.00"), "Sunday combined", None)
        txn = post_ledger_entry(self.church, self.treasury, draft)
        self.assertEqual(txn.approval_status, "PENDING")
        self.assertEqual(txn.ledger_category_id, cat.pk)
        # Combined 50/50 → DR cash + CR retain + CR remit payable
        self.assertEqual(txn.lines.count(), 3)
        total = sum(line.amount for line in txn.lines.all())
        self.assertEqual(total, Decimal("0"))

    def test_tithe_uses_remittance_payable(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_TITHE_CASH")
        draft = build_entry_draft(
            cat, Decimal("100.00"), "Member tithe", None, member=self.member
        )
        txn = post_ledger_entry(self.church, self.treasury, draft)
        credit_names = {
            line.account.name for line in txn.lines.filter(amount__lt=0)
        }
        self.assertIn("Tithe Remittance Payable", credit_names)
        self.assertNotIn("Tithe", credit_names)

    def test_expense_category_posts(self):
        cat = LedgerCategory.objects.get(church=self.church, code="EXP_UTIL_CASH")
        draft = build_entry_draft(cat, Decimal("80.00"), "Electricity bill", None)
        txn = post_ledger_entry(self.church, self.treasury, draft)
        self.assertEqual(txn.transaction_type, "EXPENSE")
        funds = list(txn.lines.values_list("fund", flat=True))
        self.assertTrue(all(f == "" or f for f in funds))

    def test_draft_requires_working_day(self):
        from transactions.models import WorkingDay

        WorkingDay.objects.filter(church=self.church).delete()
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        with self.assertRaises(WorkingDayClosedError):
            build_entry_draft(cat, Decimal("10.00"), "No day", None)

    def test_idempotent_confirm(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        draft = build_entry_draft(cat, Decimal("40.00"), "Idempotent", None)
        key = "ledger-test-key-001"
        first = post_ledger_entry(self.church, self.treasury, draft, idempotency_key=key)
        second = post_ledger_entry(self.church, self.treasury, draft, idempotency_key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Transaction.objects.filter(church=self.church, ledger_category=cat).count(),
            1,
        )


class ViewTests(LedgerTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_entry_requires_login(self):
        response = self.client.get(reverse("ledger:entry"))
        self.assertEqual(response.status_code, 302)

    def test_api_categories_filters_by_type(self):
        self.client.login(username="ledger_t", password="pass12345")
        response = self.client.get(reverse("ledger:api_categories"), {"type": "EXPENSE"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(all(c["transaction_type"] == "EXPENSE" for c in data["categories"]))

    def test_confirm_flow_saves_transaction(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        draft = build_entry_draft(cat, Decimal("100.00"), "Test income", None)
        session = self.client.session
        session["ledger_entry_draft"] = draft
        session.save()

        self.client.login(username="ledger_t", password="pass12345")
        response = self.client.post(
            reverse("ledger:entry_confirm"),
            {"action": "confirm", "idempotency_key": "view-confirm-1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.filter(church=self.church, ledger_category=cat).count(), 1)

    def test_entry_form_review_redirects(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        self.client.login(username="ledger_t", password="pass12345")
        response = self.client.post(
            reverse("ledger:entry"),
            {
                "transaction_type": "RECEIPT",
                "category": str(cat.pk),
                "amount": "50.00",
                "narration": "Offering",
                "date": timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("ledger/entry/confirm", response.url)


class PageTests(LedgerTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username="ledger_t", password="pass12345")

    def test_index_renders(self):
        response = self.client.get(reverse("ledger:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "General Ledger")

    def test_categories_renders(self):
        response = self.client.get(reverse("ledger:categories"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Posting Categories")
        self.assertContains(response, "REC_TITHE_CASH")

    def test_categories_filter_by_type(self):
        response = self.client.get(reverse("ledger:categories"), {"type": "EXPENSE"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EXP_UTIL_CASH")
        self.assertNotContains(response, "REC_TITHE_CASH")

    def test_entries_list_renders(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        draft = build_entry_draft(cat, Decimal("25.00"), "Test", None)
        post_ledger_entry(self.church, self.treasury, draft)
        response = self.client.get(reverse("ledger:entries"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ledger Entries")

    def test_entries_export_csv(self):
        response = self.client.get(reverse("ledger:entries"), {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_category_report_renders(self):
        response = self.client.get(reverse("ledger:category_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GL by Category")

    def test_entry_page_renders(self):
        response = self.client.get(reverse("ledger:entry"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ledger Entry")

    def test_confirm_page_renders_with_draft(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        draft = build_entry_draft(cat, Decimal("75.00"), "Confirm test", None)
        session = self.client.session
        session["ledger_entry_draft"] = draft
        session.save()
        response = self.client.get(reverse("ledger:entry_confirm"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm Ledger Entry")
        self.assertContains(response, "Debit")

    def test_category_detail_renders(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_TITHE_CASH")
        response = self.client.get(reverse("ledger:category_detail", args=[cat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cat.name)
        self.assertContains(response, "Posting Rules")

    def test_category_edit_updates(self):
        cat = LedgerCategory.objects.get(church=self.church, code="REC_INCOME_CASH")
        response = self.client.post(
            reverse("ledger:category_edit", args=[cat.pk]),
            {
                "name": "General Income Updated",
                "default_narration": cat.default_narration,
                "default_debit_account": str(cat.default_debit_account_id),
                "default_credit_account": str(cat.default_credit_account_id),
                "requires_member": "",
                "is_active": "on",
                "sort_order": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "General Income Updated")

    def test_accounts_and_category_create_pages(self):
        response = self.client.get(reverse("ledger:accounts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chart of Accounts")
        response = self.client.get(reverse("ledger:category_add"))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("ledger:account_add"))
        self.assertEqual(response.status_code, 200)

    def test_entry_prefills_from_category_link(self):
        cat = LedgerCategory.objects.get(church=self.church, code="EXP_UTIL_CASH")
        response = self.client.get(reverse("ledger:entry"), {"category": str(cat.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(cat.pk))
