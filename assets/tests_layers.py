"""Characterization tests for assets selectors / repositories layering."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from assets import repositories as repo
from assets import selectors
from assets.models import AssetCategory, FixedAsset
from assets.services import (
    ensure_asset_defaults_for_church,
    generate_asset_code,
    submit_asset_for_approval,
)
from organization.models import Church, Conference, District, Zone
from transactions.services import create_default_accounts, open_working_day

User = get_user_model()


class AssetsLayerTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Asset Layer Conf", code="ALC")
        zone = Zone.objects.create(name="Asset Layer Zone", code="ALZ", conference=conf)
        district = District.objects.create(
            name="Asset Layer Dist", code="ALD", zone=zone
        )
        self.church = Church.objects.create(
            name="Asset Layer Church", code="ALCH", district=district
        )
        other_conf = Conference.objects.create(name="Other Asset Conf", code="OAC")
        other_zone = Zone.objects.create(
            name="Other Asset Zone", code="OAZ", conference=other_conf
        )
        other_dist = District.objects.create(
            name="Other Asset Dist", code="OAD", zone=other_zone
        )
        self.other_church = Church.objects.create(
            name="Other Asset Church", code="OACH", district=other_dist
        )
        create_default_accounts(self.church)
        ensure_asset_defaults_for_church(self.church)
        ensure_asset_defaults_for_church(self.other_church)
        self.user = User.objects.create_user(
            username="asset_layer",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="asset_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.category = AssetCategory.objects.filter(church=self.church).first()
        self.asset = FixedAsset.objects.create(
            church=self.church,
            category=self.category,
            asset_code=generate_asset_code(self.church),
            name="Projector",
            acquisition_cost=Decimal("1000.00"),
            salvage_value=Decimal("50.00"),
            useful_life_months=36,
            depreciation_method="STRAIGHT_LINE",
            purchase_date=date(2024, 1, 15),
            status="DRAFT",
            created_by=self.user,
        )

    def test_selector_asset_church_scope(self):
        found = selectors.asset_for_church(self.church, self.asset.pk)
        self.assertEqual(found.pk, self.asset.pk)
        with self.assertRaises(Http404):
            selectors.asset_for_church(self.other_church, self.asset.pk)

    def test_selector_list_and_search(self):
        qs = selectors.assets_for_church(self.church, q="Projector")
        self.assertIn(self.asset, qs)
        other_qs = selectors.assets_for_church(self.other_church)
        self.assertNotIn(self.asset, other_qs)

    def test_repository_audit_and_submit(self):
        log = repo.create_asset_audit(
            asset=self.asset,
            action="CREATE",
            user=self.user,
            notes="seed",
        )
        self.assertEqual(log.action, "CREATE")
        submit_asset_for_approval(self.asset, self.user)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, "PENDING_APPROVAL")
