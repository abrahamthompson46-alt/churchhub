"""Cross-tenant isolation tests — church A must not access church B data."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from assets.models import FixedAsset
from members.models import Gender, Member, MembershipStatus
from organization.models import Church, Conference, District, Zone
from payroll.models import Employee
from permissions.roles import UserRole
from sitecontrol.test_support import SiteControlClientHarness
from transactions.models import Transaction
from transactions.services import open_working_day, record_receipt

User = get_user_model()


class TenantIsolationMixin(SiteControlClientHarness):
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

        conf = Conference.objects.create(name="Conf", code="CF")
        zone = Zone.objects.create(conference=conf, name="Zone", code="Z1")
        d1 = District.objects.create(zone=zone, name="D1", code="D1")
        d2 = District.objects.create(zone=zone, name="D2", code="D2")
        cls.church_a = Church.objects.create(district=d1, name="Church A", code="CHA")
        cls.church_b = Church.objects.create(district=d2, name="Church B", code="CHB")

        cls.treasury_a = User.objects.create_user(
            username="treasury_a",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church_a,
        )
        cls.treasury_b = User.objects.create_user(
            username="treasury_b",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church_b,
        )

        cls.member_b = Member.objects.create(
            church=cls.church_b,
            first_name="Other",
            last_name="Member",
            gender=Gender.MALE,
            membership_status=MembershipStatus.ACTIVE,
        )
        open_working_day(cls.church_b, timezone.localdate(), cls.treasury_b)
        cls.txn_b = record_receipt(
            church=cls.church_b,
            created_by=cls.treasury_b,
            income_amount=Decimal("50.00"),
        )

        from assets.services import ensure_asset_defaults_for_church

        ensure_asset_defaults_for_church(cls.church_b)
        category = cls.church_b.asset_categories.first()
        if category:
            cls.asset_b = FixedAsset.objects.create(
                church=cls.church_b,
                category=category,
                asset_code="CHB-FA-0001",
                name="Projector B",
                purchase_date=date(2024, 1, 1),
                acquisition_cost=Decimal("1000.00"),
                useful_life_months=36,
            )
        else:
            cls.asset_b = None

        cls.employee_b = Employee.objects.create(
            host_church=cls.church_b,
            paying_unit_id=cls.church_b.pk,
            first_name="Pay",
            last_name="Roll",
            employee_number="EMP-B-001",
            date_joined=date(2024, 1, 1),
        )


class MemberIsolationTests(TenantIsolationMixin, TestCase):
    def test_member_detail_other_church_returns_404(self):
        client = Client()
        client.login(username="treasury_a", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_a.pk)
        session.save()
        response = client.get(reverse("members:detail", kwargs={"member_id": self.member_b.pk}))
        self.assertIn(response.status_code, (403, 404))


class TransactionIsolationTests(TenantIsolationMixin, TestCase):
    def test_transaction_detail_other_church_returns_404(self):
        client = Client()
        client.login(username="treasury_a", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_a.pk)
        session.save()
        response = client.get(reverse("transactions:transaction_detail", kwargs={"pk": self.txn_b.pk}))
        self.assertIn(response.status_code, (403, 404))

    def test_member_list_excludes_other_church(self):
        Member.objects.create(
            church=self.church_a,
            first_name="Local",
            last_name="Member",
            gender=Gender.FEMALE,
            membership_status=MembershipStatus.ACTIVE,
        )
        client = Client()
        client.login(username="treasury_a", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_a.pk)
        session.save()
        response = client.get(reverse("members:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local")
        self.assertNotContains(response, "Other Member")


class AssetIsolationTests(TenantIsolationMixin, TestCase):
    def test_asset_detail_other_church_returns_404(self):
        if not self.asset_b:
            self.skipTest("No asset categories seeded")
        client = Client()
        client.login(username="treasury_a", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_a.pk)
        session.save()
        response = client.get(reverse("assets:asset_detail", kwargs={"pk": self.asset_b.pk}))
        self.assertIn(response.status_code, (403, 404))


class PayrollIsolationTests(TenantIsolationMixin, TestCase):
    def test_employee_list_scoped_to_church(self):
        client = Client()
        client.login(username="treasury_b", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_b.pk)
        session.save()
        response = client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pay Roll")

        client.login(username="treasury_a", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church_a.pk)
        session.save()
        response = client.get(reverse("payroll:employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Pay Roll")
