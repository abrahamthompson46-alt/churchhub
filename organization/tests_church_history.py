"""Tests for Church History chronicle (Church Life panel)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from organization.models import (
    Church,
    ChurchHistoryEntry,
    Conference,
    District,
    Zone,
)
from organization.services import create_church_history_entry, search_church_history_entries
from permissions.org_scope import OrgScopeLevel, apply_org_scope
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class ChurchHistoryTests(TestCase):
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
            name="History Denom",
            code="HD",
            is_active=True,
        )
        cls.other_denomination = Denomination.objects.create(
            name="Other History Denom",
            code="OHD",
            is_active=True,
        )
        cls.conference = Conference.objects.create(
            code="HC1",
            name="History Conference",
            denomination=cls.denomination,
        )
        cls.other_conference = Conference.objects.create(
            code="OHC1",
            name="Other History Conference",
            denomination=cls.other_denomination,
        )
        cls.zone = Zone.objects.create(
            conference=cls.conference, code="HZ1", name="History Zone"
        )
        cls.other_zone = Zone.objects.create(
            conference=cls.other_conference, code="OHZ1", name="Other Zone"
        )
        cls.district = District.objects.create(
            zone=cls.zone, code="HD1", name="History District"
        )
        cls.other_district = District.objects.create(
            zone=cls.other_zone, code="OHD1", name="Other District"
        )
        cls.church = Church.objects.create(
            district=cls.district, code="HCH1", name="Alpha Church", is_active=True
        )
        cls.church_b = Church.objects.create(
            district=cls.district, code="HCH2", name="Beta Church", is_active=True
        )
        cls.other_church = Church.objects.create(
            district=cls.other_district, code="OHCH1", name="Foreign Church", is_active=True
        )

        cls.secretary = User.objects.create_user(
            username="hist_secretary",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
            denomination=cls.denomination,
        )
        cls.conference_admin = User.objects.create_user(
            username="hist_conf_admin",
            password="pass12345",
            role=UserRole.CONFERENCE_ADMIN,
            denomination=cls.denomination,
        )
        apply_org_scope(
            cls.conference_admin,
            role=UserRole.CONFERENCE_ADMIN,
            scope_level=OrgScopeLevel.CONFERENCE,
            conference=cls.conference,
            denomination=cls.denomination,
            church=cls.church,
        )
        cls.conference_admin.save()

        cls.other_user = User.objects.create_user(
            username="hist_other",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.other_church,
            denomination=cls.other_denomination,
        )

        cls.entry_a = create_church_history_entry(
            church=cls.church,
            title="Cornerstone laid",
            body="The foundation stone was dedicated with thanksgiving.",
            event_date=date(1998, 5, 10),
            category=ChurchHistoryEntry.Category.FOUNDING,
            location="Main Avenue",
            tags="dedication, founding",
            performed_by=cls.secretary,
        )
        cls.entry_b = create_church_history_entry(
            church=cls.church_b,
            title="Youth hall opened",
            body="A new youth facility opened for ministry.",
            event_date=date(2015, 3, 1),
            category=ChurchHistoryEntry.Category.BUILDING,
            tags="youth, building",
            performed_by=cls.conference_admin,
        )
        create_church_history_entry(
            church=cls.other_church,
            title="Secret foreign milestone",
            body="Must never leak across denomination wall.",
            event_date=date(2000, 1, 1),
            category=ChurchHistoryEntry.Category.MILESTONE,
            performed_by=cls.other_user,
        )

    def setUp(self):
        from accounts.mfa import SESSION_MFA_VERIFIED

        self.client = Client()
        self._mfa_session_key = SESSION_MFA_VERIFIED

    def _login(self, username):
        self.client.login(username=username, password="pass12345")
        session = self.client.session
        session[self._mfa_session_key] = True
        session.save()

    def test_search_matches_title_body_tags_and_church(self):
        qs = search_church_history_entries(self.secretary, q="foundation")
        self.assertEqual(list(qs), [self.entry_a])

        qs = search_church_history_entries(self.conference_admin, q="youth")
        self.assertEqual(list(qs), [self.entry_b])

        qs = search_church_history_entries(self.conference_admin, q="Beta")
        self.assertEqual(list(qs), [self.entry_b])

    def test_conference_scope_lists_all_manageable_churches(self):
        qs = search_church_history_entries(
            self.conference_admin,
            conference_id=self.conference.pk,
        )
        self.assertEqual(set(qs), {self.entry_a, self.entry_b})

    def test_church_scope_excludes_sibling_churches(self):
        qs = search_church_history_entries(
            self.conference_admin,
            church_id=self.church.pk,
        )
        self.assertEqual(list(qs), [self.entry_a])

    def test_tenant_isolation_blocks_other_denomination(self):
        qs = search_church_history_entries(self.secretary, q="Secret foreign")
        self.assertEqual(list(qs), [])

        self._login("hist_secretary")
        foreign = ChurchHistoryEntry.objects.get(title="Secret foreign milestone")
        response = self.client.get(
            reverse("organization:church_history_detail", kwargs={"pk": foreign.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_list_and_create_views(self):
        self._login("hist_secretary")
        list_resp = self.client.get(reverse("organization:church_history_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Cornerstone laid")

        create_resp = self.client.post(
            reverse("organization:church_history_create"),
            {
                "church": str(self.church.pk),
                "title": "Silver jubilee",
                "body": "Twenty-five years of ministry celebrated.",
                "event_date": "2023-07-01",
                "category": ChurchHistoryEntry.Category.MILESTONE,
                "location": "",
                "tags": "jubilee",
            },
        )
        self.assertEqual(create_resp.status_code, 302)
        self.assertTrue(
            ChurchHistoryEntry.objects.filter(title="Silver jubilee", church=self.church).exists()
        )

    def test_church_and_conference_detail_link_to_history(self):
        self._login("hist_conf_admin")
        church_resp = self.client.get(
            reverse("organization:church_detail", kwargs={"pk": self.church.pk})
        )
        self.assertEqual(church_resp.status_code, 200)
        self.assertContains(church_resp, "Church History")
        self.assertContains(
            church_resp,
            reverse("organization:church_history_list") + f"?church={self.church.pk}",
        )

        conf_resp = self.client.get(
            reverse("organization:conference_detail", kwargs={"pk": self.conference.pk})
        )
        self.assertEqual(conf_resp.status_code, 200)
        self.assertContains(conf_resp, "Church History")
        self.assertContains(
            conf_resp,
            reverse("organization:church_history_list") + f"?conference={self.conference.pk}",
        )

    def test_deep_link_filters(self):
        self._login("hist_conf_admin")
        church_list = self.client.get(
            reverse("organization:church_history_list"),
            {"church": str(self.church.pk)},
        )
        self.assertContains(church_list, "Cornerstone laid")
        self.assertNotContains(church_list, "Youth hall opened")

        conf_list = self.client.get(
            reverse("organization:church_history_list"),
            {"conference": str(self.conference.pk)},
        )
        self.assertContains(conf_list, "Cornerstone laid")
        self.assertContains(conf_list, "Youth hall opened")
