"""Characterization tests for remittance selectors / repositories layering."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from remittance import repositories as repo
from remittance import selectors
from remittance.models import RemittancePolicy, SettlementBatch
from remittance.services import (
    create_settlement_draft,
    ensure_default_policies_for_church,
    get_active_policy,
)
from remittance.welfare_services import create_welfare_case
from transactions.services import create_default_accounts, open_working_day

User = get_user_model()


class RemittanceLayerTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Layer Conf", code="RLC")
        zone = Zone.objects.create(name="Layer Zone", code="RLZ", conference=conf)
        district = District.objects.create(name="Layer Dist", code="RLD", zone=zone)
        self.church = Church.objects.create(
            name="Layer Church", code="RLCH", district=district
        )
        other_conf = Conference.objects.create(name="Other Conf", code="ROC")
        other_zone = Zone.objects.create(
            name="Other Zone", code="ROZ", conference=other_conf
        )
        other_dist = District.objects.create(
            name="Other Dist", code="ROD", zone=other_zone
        )
        self.other_church = Church.objects.create(
            name="Other Church", code="ROCH", district=other_dist
        )
        create_default_accounts(self.church)
        create_default_accounts(self.other_church)
        ensure_default_policies_for_church(self.church)
        self.user = User.objects.create_user(
            username="layer_rem",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="layer_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.member = Member.objects.create(
            church=self.church,
            first_name="Ada",
            last_name="Lovelace",
            gender=Gender.FEMALE,
        )
        self.factory = RequestFactory()

    def _request(self, user, church=None):
        request = self.factory.get("/")
        request.user = user
        request.session = {}
        request.church = church or user.church
        return request

    def test_selector_policies_and_active_policy(self):
        policies = list(selectors.policies_for_unit("CHURCH", self.church.pk))
        self.assertTrue(policies)
        policy = get_active_policy(
            "CHURCH",
            self.church.pk,
            "COMBINED",
            "GROSS_COLLECTION",
        )
        self.assertIsNotNone(policy)
        self.assertEqual(policy.retain_percent, Decimal("50.00"))

    def test_selector_settlements_scoped_to_church(self):
        # Seed remit payable via a posted receipt path is heavy; create draft after
        # ensuring payable amount exists by creating a settlement with payable lines.
        from transactions.services import record_receipt

        record_receipt(
            church=self.church,
            created_by=self.user,
            tithe_amount=Decimal("100.00"),
        )
        # Approve so payable lines count toward settlement gross
        from transactions.models import Transaction
        from transactions.services import approve_transaction

        txn = Transaction.objects.filter(church=self.church).latest("created_at")
        approve_transaction(txn, self.pastor)

        batch = create_settlement_draft(
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            offering_type="TITHE",
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            user=self.user,
            church=self.church,
        )
        qs = selectors.settlements_for_church(self.church)
        self.assertIn(batch, qs)
        other_batches = selectors.settlements_for_church(self.other_church)
        self.assertNotIn(batch, other_batches)

    def test_welfare_case_selector_scopes_church(self):
        case = create_welfare_case(
            church=self.church,
            member=self.member,
            amount_requested=Decimal("25.00"),
            reason="Medical",
            user=self.user,
        )
        found = selectors.welfare_case_for_church(self.church, case.pk)
        self.assertEqual(found.pk, case.pk)
        with self.assertRaises(Http404):
            selectors.welfare_case_for_church(self.other_church, case.pk)

    def test_member_for_request_cross_church_denied(self):
        other_member = Member.objects.create(
            church=self.other_church,
            first_name="Foreign",
            last_name="Member",
            gender=Gender.MALE,
        )
        request = self._request(self.user)
        with self.assertRaises(Http404):
            selectors.member_for_request(request, other_member.pk)

    def test_repository_policy_audit_and_settlement_create(self):
        policy = RemittancePolicy.objects.filter(
            unit_type="CHURCH", unit_id=self.church.pk
        ).first()
        log = repo.create_policy_audit(
            policy=policy,
            action="UPDATE",
            changed_by=self.user,
            snapshot={"retain_percent": "40.00"},
        )
        self.assertEqual(log.action, "UPDATE")
        batch = repo.create_settlement_batch(
            offering_type="COMBINED",
            from_unit_type="CHURCH",
            from_unit_id=self.church.pk,
            to_unit_type="DISTRICT",
            to_unit_id=self.church.district_id,
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            gross_received=Decimal("10.00"),
            retain_amount=Decimal("0.00"),
            remit_amount=Decimal("10.00"),
            status="DRAFT",
            created_by=self.user,
        )
        self.assertEqual(batch.status, "DRAFT")
        self.assertTrue(
            SettlementBatch.objects.filter(pk=batch.pk).exists()
        )
