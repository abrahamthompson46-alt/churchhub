"""Contribution campaign tests."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from contributions.models import CampaignStatus, ContributionCampaign, MemberContribution
from contributions.services import (
    close_campaign,
    create_campaign,
    open_campaign,
    record_member_contribution,
)
from members.models import Gender, Member
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from transactions.models import Account, OfferingCategory, Transaction
from transactions.services import create_default_accounts, open_working_day

User = get_user_model()


class ContributionCampaignTests(TestCase):
    def setUp(self):
        ensure_permission_matrix()
        conf = Conference.objects.create(name="Conf", code="CC1")
        zone = Zone.objects.create(name="Zone", code="Z1", conference=conf)
        district = District.objects.create(name="Dist", code="D1", zone=zone)
        self.church = Church.objects.create(name="Church", code="CH1", district=district)
        create_default_accounts(self.church)
        self.category = OfferingCategory.objects.filter(church=self.church).first()
        if not self.category:
            account = Account.objects.filter(church=self.church, account_type="INCOME").first()
            self.category = OfferingCategory.objects.create(
                church=self.church,
                name="Harvest",
                code="HARVEST",
                account=account,
            )
        self.treasurer = User.objects.create_user(
            username="treasury_cc",
            password="pass12345",
            role=UserRole.TREASURY,
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pastor_cc",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.member = Member.objects.create(
            church=self.church,
            first_name="Campaign",
            last_name="Member",
            gender=Gender.MALE,
            email="campaign.member@example.org",
            date_of_birth=timezone.localdate().replace(year=1995),
        )
        self.portal_user = User.objects.create_user(
            username="portal_cc",
            password="pass12345",
            role=UserRole.MEMBER,
            church=self.church,
            member=self.member,
        )
        self.campaign = create_campaign(
            self.church,
            performed_by=self.treasurer,
            name="Annual Harvest",
            code="HARVEST2026",
            purpose="Support the annual harvest program.",
            deadline=timezone.localdate() + timedelta(days=3),
            offering_category=self.category,
            target_amount=Decimal("1000.00"),
            default_member_target=Decimal("100.00"),
        )
        open_campaign(self.campaign, performed_by=self.treasurer)

    def test_record_contribution_posts_receipt(self):
        gift = record_member_contribution(
            self.campaign,
            member=self.member,
            amount=Decimal("50.00"),
            performed_by=self.treasurer,
        )
        self.assertEqual(MemberContribution.objects.filter(campaign=self.campaign).count(), 1)
        self.assertEqual(gift.transaction.transaction_type, "RECEIPT")
        self.assertEqual(Transaction.objects.filter(church=self.church, member=self.member).count(), 1)

    def test_cannot_record_when_closed(self):
        close_campaign(self.campaign, performed_by=self.treasurer)
        with self.assertRaises(Exception):
            record_member_contribution(
                self.campaign,
                member=self.member,
                amount=Decimal("10.00"),
                performed_by=self.treasurer,
            )

    def test_portal_lists_open_campaign(self):
        client = Client()
        client.login(username="portal_cc", password="pass12345")
        response = client.get(reverse("portal:contributions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual Harvest")

    def test_staff_campaign_list(self):
        client = Client()
        client.login(username="treasury_cc", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = client.get(reverse("contributions:campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual Harvest")
        self.assertContains(response, "New Campaign")

    def test_navigation_includes_new_campaign_for_treasurer(self):
        from accounts.mfa import SESSION_MFA_VERIFIED
        from church_system.navigation import get_main_navigation

        nav = get_main_navigation(self.treasurer, active_church=self.church)
        finance = next(item for item in nav if item.get("id") == "finance")
        labels = []
        for section in finance.get("sections", []):
            labels.extend(i["label"] for i in section.get("items", []))
        self.assertIn("Contribution Campaigns", labels)
        self.assertIn("New Campaign", labels)


class ContributionPhase2Tests(ContributionCampaignTests):
    def test_bulk_entry_records_multiple(self):
        from contributions.services import record_bulk_contributions

        other = Member.objects.create(
            church=self.church,
            first_name="Other",
            last_name="Person",
            gender=Gender.FEMALE,
        )
        created = record_bulk_contributions(
            self.campaign,
            entries=[
                {"member": self.member, "amount": Decimal("20.00")},
                {"member": other, "amount": Decimal("30.00")},
            ],
            performed_by=self.treasurer,
        )
        self.assertEqual(len(created), 2)

    def test_member_target_progress(self):
        from contributions.services import member_progress, save_member_targets

        save_member_targets(
            self.campaign,
            targets={self.member.pk: Decimal("150.00")},
            performed_by=self.treasurer,
        )
        record_member_contribution(
            self.campaign,
            member=self.member,
            amount=Decimal("50.00"),
            performed_by=self.treasurer,
        )
        progress = member_progress(self.campaign, self.member)
        self.assertEqual(progress["target"], Decimal("150.00"))
        self.assertEqual(progress["remaining"], Decimal("100.00"))

    def test_deadline_notification_created(self):
        from contributions.reminder_services import deliver_campaign_reminder
        from dashboard.models import Notification

        sent = deliver_campaign_reminder(self.campaign, self.portal_user, "d3", send_email=False)
        self.assertTrue(sent)
        self.assertTrue(
            Notification.objects.filter(user=self.portal_user, category="FINANCE").exists()
        )

    def test_excel_import_preview(self):
        from church_system.spreadsheet_io import build_template_xlsx
        from contributions.import_services import preview_campaign_import

        content = build_template_xlsx(
            ["membership_number", "amount"],
            [[self.member.membership_number or "M1", "25.00"]],
        )
        if not self.member.membership_number:
            self.member.membership_number = "M1"
            self.member.save(update_fields=["membership_number"])
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            "import.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        result = preview_campaign_import(self.campaign, upload)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.succeeded, 1)
