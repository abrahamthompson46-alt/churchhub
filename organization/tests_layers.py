"""Characterization tests for organization selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase

from accounts.models import UserRole
from organization import repositories as repo
from organization import selectors
from organization.access import get_scoped_church, scoped_churches, scoped_conferences
from organization.models import (
    Church,
    Conference,
    District,
    GeneralConference,
    OrganizationAuditLog,
    Union,
    Zone,
)
from organization.services import create_church, transfer_church
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class OrganizationLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        ensure_permission_matrix()
        settings_obj = SiteSettings.load()
        settings_obj.enforce_subscription_limits = False
        settings_obj.save(update_fields=["enforce_subscription_limits"])
        clear_settings_cache()

        cls.denomination = Denomination.objects.create(
            name="Layer Denom",
            code="LD",
            is_active=True,
        )
        cls.other_denomination = Denomination.objects.create(
            name="Other Layer Denom",
            code="OLD",
            is_active=True,
        )
        cls.gc = GeneralConference.objects.create(code="LGC1", name="Layer GC")
        cls.union = Union.objects.create(
            general_conference=cls.gc, code="LU1", name="Layer Union"
        )
        cls.conference = Conference.objects.create(
            code="LC1",
            name="Layer Conference",
            denomination=cls.denomination,
            union=cls.union,
        )
        cls.other_conference = Conference.objects.create(
            code="LOC1",
            name="Other Layer Conference",
            denomination=cls.other_denomination,
        )
        cls.zone = Zone.objects.create(
            conference=cls.conference, code="LZ1", name="Layer Zone"
        )
        cls.other_zone = Zone.objects.create(
            conference=cls.other_conference, code="LOZ1", name="Other Layer Zone"
        )
        cls.district = District.objects.create(
            zone=cls.zone, code="LD1", name="Layer District"
        )
        cls.other_district = District.objects.create(
            zone=cls.other_zone, code="LOD1", name="Other Layer District"
        )
        cls.district2 = District.objects.create(
            zone=cls.zone, code="LD2", name="Layer District 2"
        )
        cls.church = Church.objects.create(
            district=cls.district,
            code="LCH1",
            name="Layer Church",
            financials_provisioned=True,
        )
        cls.other_church = Church.objects.create(
            district=cls.other_district,
            code="LOCH1",
            name="Other Layer Church",
            financials_provisioned=True,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_superuser(
            username="org_layer_admin",
            password="pass12345",
            email="org_layer@test.com",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
        )
        self.clerk = User.objects.create_user(
            username="org_layer_clerk",
            password="pass12345",
            email="org_clerk@test.com",
            role=UserRole.SECRETARY,
            church=self.church,
        )

    def _request(self, user, denomination=None):
        request = self.factory.get("/")
        request.user = user
        denom = denomination or self.denomination
        request.session = {"active_denomination_id": str(denom.pk)}
        return request

    def test_scoped_conferences_excludes_other_denomination(self):
        request = self._request(self.admin)
        qs = selectors.scoped_conferences(request)
        self.assertIn(self.conference, qs)
        self.assertNotIn(self.other_conference, qs)

    def test_scoped_churches_includes_local_church(self):
        request = self._request(self.admin)
        qs = scoped_churches(request)
        self.assertIn(self.church, qs)

    def test_scoped_churches_excludes_other_denomination(self):
        request = self._request(self.admin)
        qs = selectors.scoped_churches(request)
        self.assertNotIn(self.other_church, qs)

    def test_get_scoped_church_cross_denomination_404(self):
        request = self._request(self.admin)
        with self.assertRaises(Http404):
            get_scoped_church(request, self.other_church.pk)

    def test_clerk_cannot_access_other_church(self):
        request = self._request(self.clerk)
        with self.assertRaises(Http404):
            get_scoped_church(request, self.other_church.pk)

    def test_hierarchy_selectors_respect_denomination(self):
        request = self._request(self.admin)
        conf_base = selectors.hierarchy_conf_base(request, "")
        self.assertIn(self.conference, conf_base)
        self.assertNotIn(self.other_conference, conf_base)
        zones = selectors.zones_for_denomination(self.denomination)
        self.assertIn(self.zone, zones)
        self.assertNotIn(self.other_zone, zones)
        districts = selectors.districts_for_denomination(self.denomination)
        self.assertIn(self.district, districts)
        self.assertNotIn(self.other_district, districts)

    def test_directory_churches_search(self):
        request = self._request(self.admin)
        qs = selectors.directory_churches(request, q="Layer Church")
        self.assertIn(self.church, qs)
        qs_miss = selectors.directory_churches(request, q="ZZZNOMATCH")
        self.assertNotIn(self.church, qs_miss)

    def test_repository_audit_create(self):
        entry = repo.create_org_audit(
            action="UPDATE",
            entity_type="Church",
            entity_id=self.church.pk,
            entity_label=str(self.church),
            performed_by=self.admin,
            details={"via": "tests_layers"},
        )
        self.assertTrue(
            OrganizationAuditLog.objects.filter(pk=entry.pk, action="UPDATE").exists()
        )

    def test_repository_save_conference_zone_district(self):
        conf = Conference(
            code="REPO_C",
            name="Repo Conference",
            denomination=self.denomination,
        )
        repo.save_conference(conf)
        self.assertTrue(Conference.objects.filter(pk=conf.pk).exists())

        zone = Zone(conference=conf, code="REPO_Z", name="Repo Zone")
        repo.save_zone(zone)
        self.assertTrue(Zone.objects.filter(pk=zone.pk).exists())

        district = District(zone=zone, code="REPO_D", name="Repo District")
        repo.save_district(district)
        self.assertTrue(District.objects.filter(pk=district.pk).exists())

    def test_repository_save_gc_and_union(self):
        gc = GeneralConference(code="REPO_GC", name="Repo GC")
        repo.save_general_conference(gc)
        union = Union(general_conference=gc, code="REPO_U", name="Repo Union")
        repo.save_union(union)
        self.assertTrue(Union.objects.filter(pk=union.pk, general_conference=gc).exists())

    def test_create_church_via_service_uses_repo_path(self):
        church, created = create_church(
            district=self.district,
            name="Repo Path Church",
            code="RPC1",
            setup_financials=False,
            performed_by=self.admin,
        )
        self.assertTrue(created)
        self.assertTrue(
            OrganizationAuditLog.objects.filter(
                action="CREATE", entity_type="Church", entity_id=church.pk
            ).exists()
        )

    def test_transfer_within_denomination(self):
        church, _ = create_church(
            district=self.district,
            name="Movable Layer",
            code="ML1",
            setup_financials=False,
        )
        transfer_church(church, self.district2, performed_by=self.admin, reason="test")
        church.refresh_from_db()
        self.assertEqual(church.district_id, self.district2.pk)

    def test_conference_by_code_selector(self):
        self.assertEqual(selectors.conference_by_code("LC1").pk, self.conference.pk)
        self.assertIsNone(selectors.conference_by_code("NOPE"))

    def test_access_scoped_conferences_delegates(self):
        request = self._request(self.admin)
        self.assertEqual(
            list(scoped_conferences(request).values_list("pk", flat=True)),
            list(selectors.scoped_conferences(request).values_list("pk", flat=True)),
        )

    def test_form_dropdown_selectors_isolate_denomination(self):
        zones = selectors.zones_for_denomination(self.denomination)
        self.assertIn(self.zone, zones)
        self.assertNotIn(self.other_zone, zones)
        targets = selectors.transfer_target_districts(
            self._request(self.admin), self.church
        )
        self.assertIn(self.district2, targets)
        self.assertNotIn(self.other_district, targets)
        self.assertNotIn(self.district, targets)
