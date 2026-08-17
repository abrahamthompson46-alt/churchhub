"""INV-FIN-01 / INV-FIN-03 / INV-FIN-04: remittance and reconciliation HTTP gates."""

from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from remittance.services import outstanding_district_remittance_parts
from transactions.models import Account, BankReconciliation, FinancialAuditLog, Transaction
from transactions.services import (
    approve_transaction,
    create_bank_reconciliation,
    open_working_day,
    record_expense,
    record_receipt,
)

User = get_user_model()


class FinanceAuthorizationBoundaryTests(TestCase):
    """Direct HTTP tests: view_transactions must not authorize finance writes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from unittest.mock import patch

        from django.test.client import ContextList

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        conf = Conference.objects.create(name="Fin Auth Conf", code="FAC")
        zone = Zone.objects.create(name="Fin Auth Zone", code="FAZ", conference=conf)
        district = District.objects.create(name="Fin Auth Dist", code="FAD", zone=zone)
        cls.church = Church.objects.create(
            name="Fin Auth Church", code="FAH", district=district
        )
        cls.board = User.objects.create_user(
            username="fin_board",
            password="pass12345",
            role=UserRole.BOARD_MEMBER,
            church=cls.church,
        )
        cls.secretary = User.objects.create_user(
            username="fin_secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="fin_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=cls.church,
        )
        cls.treasurer = User.objects.create_user(
            username="fin_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def setUp(self):
        self.client = Client()
        open_working_day(self.church, timezone.localdate(), self.pastor)

    def _login(self, username):
        self.assertTrue(self.client.login(username=username, password="pass12345"))
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()

    def _bank_recon(self):
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("80.00"),
            payment_account_type="BANK",
            description="recon seed",
        )
        approve_transaction(txn, self.pastor)
        bank = Account.objects.get(church=self.church, account_type="BANK")
        return create_bank_reconciliation(
            church=self.church,
            bank_account=bank,
            statement_date=timezone.localdate(),
            statement_balance=Decimal("80.00"),
            user=self.treasurer,
        )

    def test_board_member_can_view_transactions(self):
        self._login("fin_board")
        response = self.client.get(reverse("transactions:transaction_list"))
        self.assertEqual(response.status_code, 200)

    def test_board_member_cannot_get_or_post_remittance(self):
        self._login("fin_board")
        get_response = self.client.get(reverse("transactions:record_remittance"))
        self.assertEqual(get_response.status_code, 403)
        before = Transaction.objects.filter(
            church=self.church, transaction_type="TRANSFER"
        ).count()
        post_response = self.client.post(
            reverse("transactions:record_remittance"),
            {
                "month": timezone.localdate().isoformat(),
                "idempotency_key": f"board-remit-{uuid.uuid4()}",
            },
        )
        self.assertEqual(post_response.status_code, 403)
        self.assertEqual(
            Transaction.objects.filter(
                church=self.church, transaction_type="TRANSFER"
            ).count(),
            before,
        )

    def test_board_member_cannot_create_or_match_reconciliation(self):
        recon = self._bank_recon()
        self._login("fin_board")
        list_response = self.client.get(reverse("transactions:reconciliation_list"))
        self.assertEqual(list_response.status_code, 200)
        detail = self.client.get(
            reverse("transactions:reconciliation_detail", kwargs={"pk": recon.pk})
        )
        self.assertEqual(detail.status_code, 200)

        bank = Account.objects.get(church=self.church, account_type="BANK")
        before = BankReconciliation.objects.filter(church=self.church).count()
        create_response = self.client.post(
            reverse("transactions:reconciliation_create"),
            {
                "bank_account": str(bank.pk),
                "statement_date": timezone.localdate().isoformat(),
                "statement_balance": "1.00",
                "notes": "board attempt",
            },
        )
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(
            BankReconciliation.objects.filter(church=self.church).count(),
            before,
        )

        line_id = recon.items.first().transaction_line_id
        match_response = self.client.post(
            reverse("transactions:reconciliation_detail", kwargs={"pk": recon.pk}),
            {"action": "match", "matched_lines": [str(line_id)]},
        )
        self.assertEqual(match_response.status_code, 403)
        recon.items.update()
        self.assertFalse(recon.items.filter(is_matched=True).exists())

    def test_secretary_can_create_receipt_and_open_remittance(self):
        seed = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("100.00"),
            description="seed tithe for remittance authz",
        )
        approve_transaction(seed, self.pastor)
        outstanding = outstanding_district_remittance_parts(self.church)
        self.assertGreater(outstanding["total"], Decimal("0.00"))

        self._login("fin_secretary")
        remit_get = self.client.get(reverse("transactions:record_remittance"))
        self.assertEqual(remit_get.status_code, 200)

        before_transfers = Transaction.objects.filter(
            church=self.church, transaction_type="TRANSFER"
        ).count()
        remit_post = self.client.post(
            reverse("transactions:record_remittance"),
            {
                "month": timezone.localdate().isoformat(),
                "idempotency_key": f"sec-remit-{uuid.uuid4()}",
            },
        )
        self.assertEqual(remit_post.status_code, 302)
        self.assertEqual(remit_post.url, reverse("dashboard:cutoff"))
        self.assertEqual(
            Transaction.objects.filter(
                church=self.church, transaction_type="TRANSFER"
            ).count(),
            before_transfers + 1,
        )
        remit_txn = Transaction.objects.get(
            church=self.church,
            transaction_type="TRANSFER",
            created_by=self.secretary,
        )
        self.assertEqual(remit_txn.approval_status, "PENDING")
        self.assertFalse(remit_txn.is_voided)
        self.assertTrue(
            FinancialAuditLog.objects.filter(
                church=self.church,
                transaction=remit_txn,
                action="REMIT",
            ).exists()
        )

        before = Transaction.objects.filter(
            church=self.church, transaction_type="RECEIPT"
        ).count()
        receipt = self.client.post(
            reverse("transactions:record_receipt") + "?classic=1",
            {
                "classic": "1",
                "idempotency_key": str(uuid.uuid4()),
                "tithe_amount": "0",
                "combined_amount": "0",
                "income_amount": "12.50",
                "payment_account_type": "CASH",
                "description": "Secretary receipt",
            },
        )
        self.assertNotEqual(receipt.status_code, 403)
        self.assertEqual(
            Transaction.objects.filter(
                church=self.church, transaction_type="RECEIPT"
            ).count(),
            before + 1,
        )

    def test_secretary_cannot_approve_or_void(self):
        txn = record_expense(
            church=self.church,
            created_by=self.treasurer,
            amount=Decimal("40.00"),
            description="pending expense",
        )
        self.assertEqual(txn.approval_status, "PENDING")
        self._login("fin_secretary")
        approve = self.client.post(
            reverse("transactions:approve_transaction", kwargs={"pk": txn.pk})
        )
        self.assertEqual(approve.status_code, 403)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "PENDING")

        approve_transaction(txn, self.pastor)
        void = self.client.post(
            reverse("transactions:void_transaction", kwargs={"pk": txn.pk}),
            {"reason": "secretary void attempt"},
        )
        self.assertEqual(void.status_code, 403)
        txn.refresh_from_db()
        self.assertFalse(txn.is_voided)

    def test_secretary_cannot_match_reconciliation(self):
        recon = self._bank_recon()
        self._login("fin_secretary")
        line_id = recon.items.first().transaction_line_id
        match_response = self.client.post(
            reverse("transactions:reconciliation_detail", kwargs={"pk": recon.pk}),
            {"action": "match", "matched_lines": [str(line_id)]},
        )
        self.assertEqual(match_response.status_code, 403)
        self.assertFalse(recon.items.filter(is_matched=True).exists())

        bank = Account.objects.get(church=self.church, account_type="BANK")
        before = BankReconciliation.objects.filter(church=self.church).count()
        create_response = self.client.post(
            reverse("transactions:reconciliation_create"),
            {
                "bank_account": str(bank.pk),
                "statement_date": timezone.localdate().isoformat(),
                "statement_balance": "2.00",
            },
        )
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(
            BankReconciliation.objects.filter(church=self.church).count(),
            before,
        )
