"""Cross-denomination isolation — users must not access another denomination's data."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from members.models import Gender, Member, MembershipStatus
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from sitecontrol.denomination_services import ensure_builtin_denominations
from sitecontrol.models import Denomination
from sitecontrol.test_support import SiteControlClientHarness

User = get_user_model()


class DenominationIsolationMixin(SiteControlClientHarness):
    @classmethod
    def setUpTestData(cls):
        # Isolation assertions must not be short-circuited by MFA enroll redirects.
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        clear_settings_cache()

        ensure_builtin_denominations()
        cls.sda = Denomination.objects.get(code="sda")
        cls.methodist = Denomination.objects.get(code="methodist")

        cls.conf_sda = Conference.objects.create(
            name="SDA Test Conference", code="SDATC", denomination=cls.sda
        )
        cls.conf_meth = Conference.objects.create(
            name="Methodist Test District", code="METHTC", denomination=cls.methodist
        )
        zone_sda = Zone.objects.create(conference=cls.conf_sda, name="Z-SDA", code="ZSDA")
        zone_meth = Zone.objects.create(conference=cls.conf_meth, name="C-METH", code="CMETH")
        d_sda = District.objects.create(zone=zone_sda, name="D-SDA", code="DSDA")
        d_meth = District.objects.create(zone=zone_meth, name="S-METH", code="SMETH")
        cls.church_sda = Church.objects.create(district=d_sda, name="SDA Church", code="SDACH")
        cls.church_meth = Church.objects.create(district=d_meth, name="Meth Church", code="METHCH")

        cls.treasury_sda = User.objects.create_user(
            username="treasury_sda_iso",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church_sda,
        )
        cls.member_meth = Member.objects.create(
            church=cls.church_meth,
            first_name="Cross",
            last_name="Denied",
            gender=Gender.MALE,
            membership_status=MembershipStatus.ACTIVE,
        )


class CrossDenominationIsolationTests(DenominationIsolationMixin, TestCase):
    def test_member_detail_other_denomination_blocked(self):
        client = Client()
        client.login(username="treasury_sda_iso", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_sda.pk)
        session["active_denomination_id"] = str(self.sda.pk)
        session.save()
        response = client.get(reverse("members:detail", kwargs={"member_id": self.member_meth.pk}))
        self.assertIn(response.status_code, (403, 404))

    def test_user_denomination_derived_from_church(self):
        from church_system.denomination_scope import get_user_denomination

        self.assertEqual(get_user_denomination(self.treasury_sda).pk, self.sda.pk)


class DenominationProfileTests(TestCase):
    def test_builtin_profiles_exist(self):
        ensure_builtin_denominations()
        codes = set(Denomination.objects.values_list("code", flat=True))
        self.assertTrue({"sda", "methodist", "cop", "generic"}.issubset(codes))

    def test_methodist_labels_differ_from_sda(self):
        ensure_builtin_denominations()
        from sitecontrol.denomination_services import get_level_label

        sda = Denomination.objects.get(code="sda")
        meth = Denomination.objects.get(code="methodist")
        self.assertNotEqual(
            get_level_label(sda, "church"),
            get_level_label(meth, "church"),
        )
