"""Tests for irreversible denomination purge."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from members.models import Member
from organization.models import Church, Conference, District, Zone
from sitecontrol.denomination_purge_services import (
    DenominationPurgeError,
    purge_denomination_completely,
    validate_denomination_purge,
)
from sitecontrol.models import Denomination, PlatformAuditLog, TenantApplication
from sitecontrol.test_support import SiteControlClientHarness

User = get_user_model()


def _build_purge_fixture(*, code="purge-me"):
    default_denom = Denomination.objects.filter(is_default=True).first()
    if not default_denom:
        default_denom = Denomination.objects.create(
            code="default-denom",
            name="Default Denom",
            is_default=True,
            is_active=True,
        )
    purge_denom = Denomination.objects.create(
        code=code,
        name=f"Denom {code}",
        is_active=True,
    )
    conf = Conference.objects.create(
        name=f"Conf {code}",
        code=f"{code}-conf",
        denomination=purge_denom,
    )
    zone = Zone.objects.create(conference=conf, name=f"Zone {code}", code=f"{code}-z")
    district = District.objects.create(zone=zone, name=f"District {code}", code=f"{code}-d")
    church = Church.objects.create(
        district=district,
        name=f"Church {code}",
        code=f"{code}-ch",
    )
    institution_user = User.objects.create_user(
        username=f"admin_{code}",
        password="pass12345",
        church=church,
        denomination=purge_denom,
    )
    member = Member.objects.create(
        church=church,
        first_name="Test",
        last_name=f"Member {code}",
        gender="M",
    )
    TenantApplication.objects.create(
        denomination=purge_denom,
        church_name="Pending",
        church_code=f"{code}-pend",
        contact_name="Contact",
        contact_email=f"contact@{code}.test",
        applicant_username=f"pending_{code}",
    )
    return purge_denom, church, institution_user, member


class DenominationPurgeServiceTests(TestCase):
    def test_validate_blocks_default_denomination(self):
        default_denom = Denomination.objects.create(
            code="default-only",
            name="Default Only",
            is_default=True,
            is_active=True,
        )
        with self.assertRaises(DenominationPurgeError):
            validate_denomination_purge(default_denom)

    def test_service_purge_removes_related_data(self):
        purge_denom, church, institution_user, member = _build_purge_fixture(code="svc-purge")
        result = purge_denomination_completely(
            purge_denom,
            performed_by=None,
            reason="Test purge",
        )
        self.assertEqual(result["denomination_code"], "svc-purge")
        self.assertFalse(Denomination.objects.filter(code="svc-purge").exists())
        self.assertFalse(Church.objects.filter(pk=church.pk).exists())
        self.assertFalse(User.objects.filter(pk=institution_user.pk).exists())
        self.assertFalse(Member.objects.filter(pk=member.pk).exists())
        self.assertFalse(
            TenantApplication.objects.filter(applicant_username="pending_svc-purge").exists()
        )


class DenominationPurgeUITests(SiteControlClientHarness, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.purge_denom, cls.church, cls.institution_user, cls.member = _build_purge_fixture(
            code="ui-purge"
        )
        cls.owner = User.objects.create_user(
            username="purge_owner",
            password="OwnerPass123!",
            is_platform_user=True,
            platform_role="OWNER",
        )
        cls.scoped_op = User.objects.create_user(
            username="purge_scoped",
            password="pass12345",
            is_platform_user=True,
            platform_role="BILLING",
        )
        cls.scoped_op.managed_denominations.add(cls.purge_denom)

    def setUp(self):
        self.disable_privileged_mfa()

    def test_purge_ui_requires_owner(self):
        client = Client()
        client.login(username="purge_scoped", password="pass12345")
        response = client.get(
            reverse("sitecontrol:denomination_purge", kwargs={"pk": self.purge_denom.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_purge_ui_three_step_flow(self):
        client = Client()
        client.login(username="purge_owner", password="OwnerPass123!")
        url = reverse("sitecontrol:denomination_purge", kwargs={"pk": self.purge_denom.pk})

        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "step 1 of 3")

        response = client.post(
            url,
            {
                "step": "1",
                "ack_irreversible": "yes",
                "ack_financial": "yes",
                "ack_authority": "yes",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "step 2 of 3")

        response = client.post(
            url,
            {
                "step": "2",
                "confirm_code": "ui-purge",
                "reason": "Contract terminated",
                "ack_final": "yes",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "step 3 of 3")

        before_logs = PlatformAuditLog.objects.filter(action="DENOMINATION_PURGE").count()
        response = client.post(
            url,
            {
                "step": "3",
                "confirm_phrase": "DELETE PERMANENTLY",
                "password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Denomination.objects.filter(pk=self.purge_denom.pk).exists())

        response = client.post(
            url,
            {
                "step": "3",
                "confirm_phrase": "DELETE PERMANENTLY",
                "password": "OwnerPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Denomination.objects.filter(pk=self.purge_denom.pk).exists())
        self.assertEqual(
            PlatformAuditLog.objects.filter(action="DENOMINATION_PURGE").count(),
            before_logs + 1,
        )
