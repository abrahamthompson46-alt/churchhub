"""Tests for platform Excel import."""

from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from church_system.spreadsheet_io import build_template_xlsx
from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from sitecontrol.import_services import commit_member_import, preview_member_import
from sitecontrol.test_support import SiteControlClientHarness
from transactions.models import Transaction
from transactions.services import create_default_accounts, open_working_day


def _xlsx_upload(headers, rows, name="import.xlsx"):
    content = build_template_xlsx(headers, rows)
    return SimpleUploadedFile(
        name,
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class MemberImportServiceTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Conf", code="CF1")
        zone = Zone.objects.create(name="Zone", code="Z1", conference=conf)
        district = District.objects.create(name="Dist", code="D1", zone=zone)
        self.church = Church.objects.create(name="Church", code="CH1", district=district)
        self.user = User.objects.create_user(username="owner", password="pass12345")

    def test_preview_valid_member_row(self):
        upload = _xlsx_upload(
            ["first_name", "last_name", "gender"],
            [["Ada", "Lovelace", "Female"]],
        )
        result = preview_member_import(upload)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.failed, 0)
        self.assertTrue(result.rows[0].ok)

    def test_commit_creates_member(self):
        upload = _xlsx_upload(
            ["first_name", "last_name", "gender", "phone"],
            [["Ada", "Lovelace", "Female", "0241111222"]],
        )
        result = commit_member_import(self.church, self.user, upload)
        self.assertEqual(result.succeeded, 1)
        self.assertTrue(
            Member.objects.filter(church=self.church, last_name="Lovelace").exists()
        )

    def test_commit_rolls_back_on_any_error(self):
        upload = _xlsx_upload(
            ["first_name", "last_name", "gender"],
            [
                ["Good", "Member", "Male"],
                ["", "Bad", "Male"],
            ],
        )
        result = commit_member_import(self.church, self.user, upload)
        self.assertEqual(result.failed, 1)
        self.assertFalse(Member.objects.filter(church=self.church, last_name="Member").exists())


class PlatformImportViewTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        conf = Conference.objects.create(name="Conf", code="CF2")
        zone = Zone.objects.create(name="Zone", code="Z2", conference=conf)
        district = District.objects.create(name="Dist", code="D2", zone=zone)
        self.church = Church.objects.create(name="Church", code="CH2", district=district)
        create_default_accounts(self.church)
        self.pastor = User.objects.create_user(
            username="pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.member = Member.objects.create(
            church=self.church,
            first_name="Import",
            last_name="Target",
            gender=Gender.MALE,
            email="import@example.org",
            date_of_birth=timezone.localdate().replace(year=1990),
        )
        self.owner = User.objects.create_user(
            username="platform",
            password="pass12345",
            is_platform_user=True,
            is_superuser=True,
            platform_role="OWNER",
        )
        self.readonly = User.objects.create_user(
            username="readonly",
            password="pass12345",
            is_platform_user=True,
            platform_role="READONLY",
        )

    def test_owner_can_open_import_hub(self):
        self.client.login(username="platform", password="pass12345")
        response = self.client.get(reverse("sitecontrol:import_hub"))
        self.assertEqual(response.status_code, 200)

    def test_readonly_blocked_from_import(self):
        self.client.login(username="readonly", password="pass12345")
        response = self.client.get(reverse("sitecontrol:import_members"))
        self.assertEqual(response.status_code, 403)

    def test_member_import_preview_via_view(self):
        self.client.login(username="platform", password="pass12345")
        upload = _xlsx_upload(
            ["first_name", "last_name", "gender"],
            [["New", "Person", "Male"]],
        )
        response = self.client.post(
            reverse("sitecontrol:import_members"),
            {
                "church": str(self.church.pk),
                "file": upload,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ready to import")

    def test_transaction_import_commits_receipt(self):
        self.client.login(username="platform", password="pass12345")
        upload = _xlsx_upload(
            ["date", "member_email", "tithe", "combined", "payment_method"],
            [
                [
                    timezone.localdate().isoformat(),
                    "import@example.org",
                    "10",
                    "5",
                    "CASH",
                ],
            ],
        )
        response = self.client.post(
            reverse("sitecontrol:import_transactions"),
            {
                "church": str(self.church.pk),
                "commit": "on",
                "file": upload,
            },
            format="multipart",
        )
        self.assertRedirects(response, reverse("sitecontrol:import_transactions"))
        trx = Transaction.objects.filter(church=self.church, transaction_type="RECEIPT").first()
        self.assertIsNotNone(trx)
        self.assertEqual(trx.member_id, self.member.pk)
