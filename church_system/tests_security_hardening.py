"""Regression tests for approved security hardening."""

from datetime import date
from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from portal.services import (
    authenticate_portal_credentials,
    build_confirm_token,
    canonical_dob_password,
    resolve_confirm_token,
)
from portal.services import PortalAuthError
from transactions.services import (
    DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT,
    effective_receipt_auto_approve_limit,
    get_or_create_treasury_approval_policy,
    record_receipt,
    open_working_day,
)
from django.utils import timezone

User = get_user_model()


class PortalCredentialHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="SEC", name="Sec Conf")
        zone = Zone.objects.create(conference=conf, code="SZ", name="Sec Zone")
        district = District.objects.create(zone=zone, code="SD", name="Sec Dist")
        cls.church = Church.objects.create(district=district, code="SCH", name="Sec Church")
        cls.dob = date(1991, 7, 4)
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Sam",
            last_name="Member",
            email="sam.member@example.com",
            date_of_birth=cls.dob,
            gender="Male",
        )

    def test_dob_rejected_after_password_change(self):
        user = authenticate_portal_credentials(
            "sam.member@example.com",
            canonical_dob_password(self.dob),
        )
        user.set_password("RealPortalPass1!")
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])

        with self.assertRaises(PortalAuthError):
            authenticate_portal_credentials(
                "sam.member@example.com",
                canonical_dob_password(self.dob),
            )

    def test_confirm_token_is_single_use(self):
        user = authenticate_portal_credentials(
            "sam.member@example.com",
            canonical_dob_password(self.dob),
        )
        token = build_confirm_token(user)
        resolve_confirm_token(token)
        with self.assertRaises(PortalAuthError):
            resolve_confirm_token(token)


@override_settings(HEALTH_CHECK_TOKEN="test-health-secret")
class HealthEndpointAuthTests(TestCase):
    def test_health_requires_token_when_configured(self):
        client = Client()
        blocked = client.get(reverse("health_check"))
        self.assertEqual(blocked.status_code, 401)
        ok = client.get(reverse("health_check"), {"token": "test-health-secret"})
        self.assertIn(ok.status_code, (200, 503))


class TreasuryAutoApproveCapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="TC", name="Treasury Conf")
        zone = Zone.objects.create(conference=conf, code="TZ", name="Treasury Zone")
        district = District.objects.create(zone=zone, code="TD", name="Treasury Dist")
        cls.church = Church.objects.create(district=district, code="TCH", name="Treasury Church")
        cls.treasurer = User.objects.create_user(
            username="sec_treasury",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        open_working_day(cls.church, timezone.localdate(), cls.treasurer)

    def test_new_church_policy_has_capped_auto_approve(self):
        policy = get_or_create_treasury_approval_policy(self.church)
        self.assertEqual(
            policy.default_receipt_auto_approve_limit,
            DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT,
        )
        enabled, limit = effective_receipt_auto_approve_limit(self.treasurer, self.church)
        self.assertTrue(enabled)
        self.assertEqual(limit, DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT)

    def test_receipt_above_cap_stays_pending(self):
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=DEFAULT_RECEIPT_AUTO_APPROVE_LIMIT + Decimal("0.01"),
        )
        self.assertEqual(txn.approval_status, "PENDING")


class MemberSearchPiiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        conf = Conference.objects.create(code="MC", name="Member Conf")
        zone = Zone.objects.create(conference=conf, code="MZ", name="Member Zone")
        district = District.objects.create(zone=zone, code="MD", name="Member Dist")
        cls.church = Church.objects.create(district=district, code="MCH", name="Member Church")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Pat",
            last_name="Private",
            email="pat@example.com",
            phone="555-0100",
            date_of_birth=date(1985, 1, 1),
            gender="Female",
        )
        cls.treasurer = User.objects.create_user(
            username="treasury_search",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def test_treasury_detail_search_omits_sensitive_pii(self):
        client = Client()
        client.login(username="treasury_search", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = client.get(
            reverse("members:search"),
            {"q": "Pat", "detail": "1"},
        )
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertNotIn("date_of_birth", row)
        self.assertNotIn("address", row)
        self.assertNotIn("phone", row)
