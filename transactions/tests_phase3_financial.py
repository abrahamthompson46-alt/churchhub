"""Phase 3 financial integrity + maker-checker focused tests.

Covers: CH-SEC-004/005/006/011/012/013, INV-FIN-02, CH-SEC-L3, SoD.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from assets.models import FixedAsset
from assets.services import ensure_asset_defaults_for_church, post_depreciation_entry, seed_platform_category_templates
from contributions.services import create_campaign, open_campaign, record_member_contribution
from contributions.models import MemberContribution
from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from organization import repositories as org_repo
from permissions.services import ensure_permission_matrix
from remittance.models import SettlementBatch
from remittance.services import (
    RemittancePolicyError,
    create_settlement_draft,
)
from remittance.welfare_services import (
    approve_welfare_case,
    create_welfare_case,
    send_welfare_case_to_review,
)
from sitecontrol.models import Denomination
from sitecontrol import repositories as site_repo
from transactions.idempotency import (
    IdempotencyReplay,
    claim_financial_idempotency,
    complete_financial_idempotency,
)
from transactions.models import Account, OfferingCategory, Transaction
from transactions.services import (
    approve_transaction,
    create_default_accounts,
    open_working_day,
    record_expense,
    record_receipt,
    void_transaction,
)

User = get_user_model()


def _hierarchy(*, denom=None, code_prefix="P3"):
    conf = Conference.objects.create(
        name=f"{code_prefix} Conf",
        code=f"{code_prefix}C",
        denomination=denom,
    )
    zone = Zone.objects.create(name=f"{code_prefix} Zone", code=f"{code_prefix}Z", conference=conf)
    district = District.objects.create(
        name=f"{code_prefix} Dist", code=f"{code_prefix}D", zone=zone
    )
    church = Church.objects.create(
        name=f"{code_prefix} Church", code=f"{code_prefix}H", district=district
    )
    return conf, zone, district, church


class Phase3TenantIntegrityTests(TestCase):
    """CH-SEC-004 / INV-TEN-05."""

    def setUp(self):
        self.denom_a = Denomination.objects.create(
            name="Phase3 Denom A", code="p3a"
        )
        self.denom_b = Denomination.objects.create(
            name="Phase3 Denom B", code="p3b"
        )
        _, _, self.district_a, self.church = _hierarchy(denom=self.denom_a, code_prefix="P3A")
        _, _, self.district_b, _ = _hierarchy(denom=self.denom_b, code_prefix="P3B")

    def test_inconsistent_denomination_save_denied(self):
        self.church.district = self.district_b
        with self.assertRaises(ValidationError):
            self.church.full_clean()

    def test_repository_save_cannot_bypass_validation(self):
        self.church.district = self.district_b
        with self.assertRaises(ValidationError):
            org_repo.save_church(self.church)
        with self.assertRaises(ValidationError):
            site_repo.save_church(self.church)
        self.church.refresh_from_db()
        self.assertEqual(self.church.district_id, self.district_a.pk)

    def test_same_denomination_transfer_allowed(self):
        conf2 = Conference.objects.create(
            name="P3A Conf2", code="P3A2", denomination=self.denom_a
        )
        zone2 = Zone.objects.create(name="P3A Zone2", code="P3AZ2", conference=conf2)
        district2 = District.objects.create(name="P3A Dist2", code="P3AD2", zone=zone2)
        self.church.district = district2
        org_repo.save_church(self.church)
        self.church.refresh_from_db()
        self.assertEqual(self.church.district_id, district2.pk)


class Phase3IdempotencyTests(TestCase):
    """CH-SEC-013 / INV-IDEM-03."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3I")
        create_default_accounts(self.church)
        self.user = User.objects.create_user(
            username="p3_idem",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.user)

    def test_completed_key_replays(self):
        key = "p3-idem-complete-1"
        record = claim_financial_idempotency(self.church, self.user, "EXPENSE", key)
        trx = record_expense(
            church=self.church,
            created_by=self.user,
            amount=Decimal("10.00"),
            description="Idem expense",
        )
        complete_financial_idempotency(record, trx)
        with self.assertRaises(IdempotencyReplay) as ctx:
            claim_financial_idempotency(self.church, self.user, "EXPENSE", key)
        self.assertEqual(ctx.exception.existing_transaction.pk, trx.pk)

    def test_incomplete_key_serializes_under_lock(self):
        key = "p3-idem-incomplete-1"
        first = claim_financial_idempotency(self.church, self.user, "RECEIPT", key)
        second = claim_financial_idempotency(self.church, self.user, "RECEIPT", key)
        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(second.transaction_id)


class Phase3ContributionIdempotencyTests(TestCase):
    """CH-SEC-006."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3C")
        create_default_accounts(self.church)
        self.category = OfferingCategory.objects.filter(church=self.church).first()
        if not self.category:
            income = Account.objects.filter(church=self.church, account_type="INCOME").first()
            self.category = OfferingCategory.objects.create(
                church=self.church,
                name="Harvest",
                code="HARVEST",
                account=income,
            )
        self.treasurer = User.objects.create_user(
            username="p3_contrib",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="p3_contrib_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.member = Member.objects.create(
            church=self.church,
            first_name="Gift",
            last_name="Giver",
            gender=Gender.MALE,
        )
        self.campaign = create_campaign(
            church=self.church,
            performed_by=self.treasurer,
            name="Harvest",
            code="HARV",
            purpose="Test",
            deadline=timezone.localdate() + timedelta(days=30),
            offering_category=self.category,
        )
        open_campaign(self.campaign, performed_by=self.treasurer)

    def test_first_request_creates_one_effect(self):
        key = "p3-contrib-once"
        gift = record_member_contribution(
            self.campaign,
            member=self.member,
            amount=Decimal("25.00"),
            performed_by=self.treasurer,
            idempotency_key=key,
        )
        self.assertEqual(MemberContribution.objects.filter(campaign=self.campaign).count(), 1)
        replay = record_member_contribution(
            self.campaign,
            member=self.member,
            amount=Decimal("25.00"),
            performed_by=self.treasurer,
            idempotency_key=key,
        )
        self.assertEqual(gift.pk, replay.pk)
        self.assertEqual(MemberContribution.objects.filter(campaign=self.campaign).count(), 1)
        self.assertEqual(
            Transaction.objects.filter(church=self.church, member=self.member).count(),
            1,
        )


class Phase3LedgerAuthorizationTests(TestCase):
    """INV-FIN-02."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from unittest.mock import patch as _patch

        from django.test.client import ContextList

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = _patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3L")
        create_default_accounts(self.church)
        self.board = User.objects.create_user(
            username="p3_board_ledger",
            password="pass12345",
            role=UserRole.BOARD_MEMBER,
            church=self.church,
        )
        self.treasurer = User.objects.create_user(
            username="p3_treasury_ledger",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.treasurer)
        self.client = Client()

    def _session_login(self, user):
        self.client.login(username=user.username, password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.id)
        session.save()

    def test_view_ledger_cannot_confirm(self):
        self._session_login(self.board)
        session = self.client.session
        session["ledger_draft"] = {
            "category_id": str(uuid.uuid4()),
            "transaction_type": "RECEIPT",
            "amount": "10.00",
            "date": timezone.localdate().isoformat(),
            "description": "x",
            "debit_account_id": str(uuid.uuid4()),
            "credit_account_id": str(uuid.uuid4()),
            "idempotency_key": str(uuid.uuid4()),
        }
        session.save()
        response = self.client.post(reverse("ledger:entry_confirm"))
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            # Permission decorator redirects to login/denied rather than posting.
            self.assertNotEqual(response.url, reverse("ledger:entry_confirm"))

    def test_authorized_writer_reaches_confirm_gate(self):
        self._session_login(self.treasurer)
        response = self.client.get(reverse("ledger:entry"))
        self.assertEqual(response.status_code, 200)


class Phase3MakerCheckerWelfareTests(TestCase):
    """CH-SEC-011 / INV-SOD-02."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3W")
        create_default_accounts(self.church)
        self.creator = User.objects.create_user(
            username="p3_welfare_creator",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.reviewer = User.objects.create_user(
            username="p3_welfare_reviewer",
            password="pass12345",
            role=UserRole.BOARD_MEMBER,
            church=self.church,
        )
        self.approver = User.objects.create_user(
            username="p3_welfare_approver",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.member = Member.objects.create(
            church=self.church,
            first_name="Need",
            last_name="Help",
            gender=Gender.FEMALE,
        )
        open_working_day(self.church, timezone.localdate(), self.approver)

    def test_creator_cannot_approve(self):
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("40.00"),
            reason="Food",
            user=self.creator,
            assistance_type="OTHER",
        )
        with self.assertRaises(RemittancePolicyError):
            approve_welfare_case(case, self.creator)

    def test_reviewer_cannot_final_approve(self):
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("40.00"),
            reason="Medical",
            user=self.creator,
            assistance_type="MEDICAL",
        )
        send_welfare_case_to_review(case, self.reviewer)
        with self.assertRaises(RemittancePolicyError):
            approve_welfare_case(case, self.reviewer)
        approve_welfare_case(case, self.approver, amount_approved=Decimal("40.00"))
        case.refresh_from_db()
        self.assertEqual(case.status, "APPROVED")

    def test_creator_cannot_review(self):
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("40.00"),
            reason="Medical",
            user=self.creator,
            assistance_type="MEDICAL",
        )
        with self.assertRaises(RemittancePolicyError):
            send_welfare_case_to_review(case, self.creator)


class Phase3AssetJournalTests(TestCase):
    """CH-SEC-005."""

    def setUp(self):
        ensure_permission_matrix()
        seed_platform_category_templates()
        _, _, _, self.church = _hierarchy(code_prefix="P3AS")
        ensure_asset_defaults_for_church(self.church)
        create_default_accounts(self.church)
        self.maker = User.objects.create_user(
            username="p3_asset_maker",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.checker = User.objects.create_user(
            username="p3_asset_checker",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        category = self.church.asset_categories.first()
        self.asset = FixedAsset.objects.create(
            church=self.church,
            category=category,
            asset_code="P3AS-FA-0001",
            name="Projector",
            purchase_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200.00"),
            salvage_value=Decimal("0.00"),
            useful_life_months=12,
            depreciation_method="STRAIGHT_LINE",
            status="ACTIVE",
        )

    def test_closed_working_day_denied(self):
        from transactions.services import WorkingDayClosedError

        with self.assertRaises(WorkingDayClosedError):
            post_depreciation_entry(self.asset, 2024, 1, self.maker, checker=self.checker)

    def test_background_creates_pending_without_register(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)
        result = post_depreciation_entry(self.asset, 2024, 1, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["pending_journal"].approval_status, "PENDING")
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))

    def test_checker_updates_register(self):
        open_working_day(self.church, date(2024, 1, 28), self.checker)
        entry = post_depreciation_entry(
            self.asset, 2024, 1, self.maker, checker=self.checker
        )
        self.assertFalse(isinstance(entry, dict))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("100.00"))

    def test_maker_only_leaves_register_unchanged(self):
        open_working_day(self.church, date(2024, 2, 28), self.checker)
        pending = post_depreciation_entry(self.asset, 2024, 2, self.maker)
        self.assertIsInstance(pending, dict)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.00"))
        with self.assertRaises(Exception):
            post_depreciation_entry(self.asset, 2024, 2, self.maker, checker=self.checker)


class Phase3VoidConcurrencyTests(TransactionTestCase):
    """CH-SEC-012."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3V")
        create_default_accounts(self.church)
        self.maker = User.objects.create_user(
            username="p3_void_maker",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.checker = User.objects.create_user(
            username="p3_void_checker",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.checker)
        self.trx = record_receipt(
            church=self.church,
            created_by=self.maker,
            tithe_amount=Decimal("50.00"),
        )
        if self.trx.approval_status != "APPROVED":
            approve_transaction(self.trx, self.checker)
        self.trx.refresh_from_db()

    def test_sequential_second_void_denied(self):
        void_transaction(self.trx, self.checker, reason="first")
        with self.assertRaises(ValueError):
            void_transaction(self.trx, self.checker, reason="second")
        self.assertEqual(
            Transaction.objects.filter(reversal_of=self.trx).count(),
            1,
        )


class Phase3SettlementUniquenessTests(TestCase):
    """CH-SEC-L3."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3S")
        create_default_accounts(self.church)
        self.treasurer = User.objects.create_user(
            username="p3_settle_t",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="p3_settle_p",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        receipt = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("200.00"),
        )
        if receipt.approval_status != "APPROVED":
            approve_transaction(receipt, self.pastor)
        today = timezone.localdate()
        self.period_start = today.replace(day=1)
        self.period_end = today

    def test_duplicate_settlement_draft_denied(self):
        create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=self.period_start,
            period_end=self.period_end,
            user=self.pastor,
            church=self.church,
        )
        with self.assertRaises(RemittancePolicyError):
            create_settlement_draft(
                from_unit_type="CHURCH",
                from_unit_id=self.church.pk,
                offering_type="TITHE",
                period_start=self.period_start,
                period_end=self.period_end,
                user=self.pastor,
                church=self.church,
            )
        self.assertEqual(
            SettlementBatch.objects.filter(
                from_unit_id=self.church.pk,
                offering_type="TITHE",
                status__in=("DRAFT", "POSTED"),
            ).count(),
            1,
        )


class Phase3MakerCheckerExpenseTests(TestCase):
    """Cross-cutting SoD: maker cannot approve own expense."""

    def setUp(self):
        ensure_permission_matrix()
        _, _, _, self.church = _hierarchy(code_prefix="P3E")
        create_default_accounts(self.church)
        self.maker = User.objects.create_user(
            username="p3_exp_maker",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.checker = User.objects.create_user(
            username="p3_exp_checker",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.checker)

    def test_maker_cannot_approve_own(self):
        trx = record_expense(
            church=self.church,
            created_by=self.maker,
            amount=Decimal("15.00"),
            description="Office supplies",
        )
        with self.assertRaises(ValueError):
            approve_transaction(trx, self.maker)
        approve_transaction(trx, self.checker)
        trx.refresh_from_db()
        self.assertEqual(trx.approval_status, "APPROVED")
