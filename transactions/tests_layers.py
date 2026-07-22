"""Characterization tests for transactions selectors / repositories layering."""

from decimal import Decimal

from django.http import Http404
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from transactions import repositories as repo
from transactions import selectors
from transactions.services import (
    approve_transaction,
    create_default_accounts,
    open_working_day,
    record_receipt,
    validate_transaction_balance,
)

User = get_user_model()


class TransactionsLayerTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Layer Conf", code="LC")
        zone = Zone.objects.create(name="Layer Zone", code="LZ", conference=conf)
        district = District.objects.create(name="Layer Dist", code="LD", zone=zone)
        self.church = Church.objects.create(
            name="Layer Church", code="LCH", district=district
        )
        create_default_accounts(self.church)
        self.user = User.objects.create_user(
            username="layer_tr",
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
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.get("/")
        request.user = user
        request.session = {}
        # Active church resolution used by filter_by_church helpers
        request.church = self.church
        return request

    def test_selector_pending_and_repository_create_line_path(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.user,
            tithe_amount=Decimal("10.00"),
        )
        request = self._request(self.user)
        pending = list(selectors.pending_transactions_qs(request))
        self.assertIn(txn, pending)

        approve_transaction(txn, self.pastor)
        txn.refresh_from_db()
        self.assertEqual(txn.approval_status, "APPROVED")
        self.assertTrue(txn.locked)
        validate_transaction_balance(txn)

        total = repo.transaction_line_sum(txn)
        self.assertEqual(total, Decimal("0.00"))

    def test_selector_transaction_for_request_scopes_church(self):
        other_conf = Conference.objects.create(name="Other", code="OT")
        other_zone = Zone.objects.create(name="OZ", code="OZ", conference=other_conf)
        other_dist = District.objects.create(name="OD", code="OD", zone=other_zone)
        other_church = Church.objects.create(
            name="Other Church", code="OCH", district=other_dist
        )
        create_default_accounts(other_church)
        other_user = User.objects.create_user(
            username="other_tr",
            password="pass12345",
            role="TREASURY",
            church=other_church,
        )
        open_working_day(other_church, timezone.localdate(), other_user)
        foreign = record_receipt(
            church=other_church,
            created_by=other_user,
            income_amount=Decimal("5.00"),
        )
        request = self._request(self.user)
        with self.assertRaises(Http404):
            selectors.transaction_for_request(request, foreign.pk)
