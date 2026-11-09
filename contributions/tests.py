"""Contribution campaign tests."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from contributions.forms import ContributionCampaignForm, RemitCampaignForm
from contributions.models import CampaignKind, CampaignStatus, ContributionCampaign, MemberContribution
from contributions.services import (
    ContributionServiceError,
    close_campaign,
    create_campaign,
    open_campaign,
    record_member_contribution,
    remit_district_funeral_campaign,
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

    def test_generates_unique_codes(self):
        second_campaign = create_campaign(
            self.church,
            performed_by=self.treasurer,
            name="Building Drive",
            purpose="Roof",
            deadline=timezone.localdate() + timedelta(days=10),
            offering_category=self.category,
        )
        third_campaign = create_campaign(
            self.church,
            performed_by=self.treasurer,
            name="Youth Drive",
            purpose="Camp",
            deadline=timezone.localdate() + timedelta(days=10),
            offering_category=self.category,
        )
        self.assertTrue(second_campaign.code.startswith("CMP-"))
        self.assertTrue(third_campaign.code.startswith("CMP-"))
        self.assertNotEqual(second_campaign.code, third_campaign.code)

    def test_record_contribution_posts_receipt(self):
        gift = record_member_contribution(
            self.campaign,
            member=self.member,
            amount=Decimal("50.00"),
            performed_by=self.treasurer,
            idempotency_key="contrib-test-receipt-1",
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
                idempotency_key="contrib-test-closed-1",
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
        create = client.get(reverse("contributions:campaign_create"))
        self.assertEqual(create.status_code, 200)
        self.assertContains(create, "finance-entry-form")
        self.assertNotContains(create, 'name="code"')
        detail = client.get(reverse("contributions:campaign_detail", args=[self.campaign.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "data-member-picker")
        self.assertContains(detail, "Search member")

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

    def test_campaign_member_totals_export_is_audited(self):
        from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
        from reports.models import ReportAccessAuditLog

        enable_mfa_for_user(self.treasurer, generate_totp_secret(), [])
        self.treasurer.refresh_from_db()
        self.client.login(username="treasury_cc", password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        response = self.client.get(
            reverse("contributions:campaign_detail", args=[self.campaign.pk]),
            {"export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ReportAccessAuditLog.objects.filter(
                report_key="contribution_campaign_totals"
            ).count(),
            1,
        )


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
            idempotency_key="contrib-test-progress-1",
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


class DistrictFuneralCampaignTests(ContributionCampaignTests):
    def setUp(self):
        super().setUp()
        from transactions.services import ensure_district_funeral_offering_category

        self.funeral_category = ensure_district_funeral_offering_category(self.church)
        self.funeral = create_campaign(
            self.church,
            performed_by=self.treasurer,
            name="Sister Mensah funeral",
            code="FUN2026-01",
            purpose="District funeral collection.",
            deadline=timezone.localdate() + timedelta(days=14),
            offering_category=self.funeral_category,
            kind=CampaignKind.DISTRICT_FUNERAL,
        )
        open_campaign(self.funeral, performed_by=self.treasurer)

    def test_funeral_codes_use_fun_prefix(self):
        auto = create_campaign(
            self.church,
            performed_by=self.treasurer,
            name="Brother Owusu funeral",
            purpose="District funeral collection.",
            deadline=timezone.localdate() + timedelta(days=14),
            offering_category=self.funeral_category,
            kind=CampaignKind.DISTRICT_FUNERAL,
        )
        self.assertTrue(auto.code.startswith("FUN-"))

    def test_cannot_use_welfare_category(self):
        welfare = OfferingCategory.objects.get(church=self.church, code="WELFARE")
        with self.assertRaises(ValidationError):
            create_campaign(
                self.church,
                performed_by=self.treasurer,
                name="Bad funeral",
                code="FUN-BAD",
                purpose="Should fail.",
                deadline=timezone.localdate() + timedelta(days=7),
                offering_category=welfare,
                kind=CampaignKind.DISTRICT_FUNERAL,
            )

    def test_form_rewrites_welfare_to_funeral_holding(self):
        welfare = OfferingCategory.objects.get(church=self.church, code="WELFARE")
        form = ContributionCampaignForm(
            data={
                "kind": CampaignKind.DISTRICT_FUNERAL,
                "name": "Form funeral",
                "purpose": "District funeral",
                "deadline": (timezone.localdate() + timedelta(days=10)).isoformat(),
                "offering_category": str(welfare.pk),
                "portal_visible": "on",
                "show_church_progress": "on",
                "send_email_reminders": "on",
            },
            church=self.church,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["offering_category"].code, "DISTRICT_FUNERAL")
        self.assertNotIn("code", form.cleaned_data)

    def test_gift_and_remit_posts_pending_transfer(self):
        from contributions.services import build_campaign_summary

        gift = record_member_contribution(
            self.funeral,
            member=self.member,
            amount=Decimal("80.00"),
            performed_by=self.treasurer,
            idempotency_key="funeral-gift-1",
        )
        self.assertEqual(gift.transaction.transaction_type, "RECEIPT")
        row = remit_district_funeral_campaign(
            self.funeral,
            performed_by=self.treasurer,
            amount=Decimal("80.00"),
            payment_account_type="BANK",
            idempotency_key="funeral-remit-1",
        )
        self.assertEqual(row.transaction.transaction_type, "TRANSFER")
        self.assertEqual(row.transaction.approval_status, "PENDING")
        summary = build_campaign_summary(self.funeral)
        self.assertEqual(summary["total_raised"], Decimal("80.00"))
        self.assertEqual(summary["outstanding_to_district"], Decimal("0.00"))
        self.assertTrue(summary["has_pending_remittance"])

    def test_general_campaign_cannot_remit(self):
        with self.assertRaises(ContributionServiceError):
            remit_district_funeral_campaign(
                self.campaign,
                performed_by=self.treasurer,
                amount=Decimal("10.00"),
                idempotency_key="funeral-remit-general",
            )

    def test_staff_list_has_funeral_cta(self):
        client = Client()
        client.login(username="treasury_cc", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = client.get(reverse("contributions:campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New district funeral")
        self.assertContains(response, "Sister Mensah funeral")

    def test_other_church_cannot_open_funeral_campaign(self):
        other = Church.objects.create(name="Other Church", code="CH2", district=self.church.district)
        User.objects.create_user(
            username="treasury_other",
            password="pass12345",
            role=UserRole.TREASURY,
            church=other,
        )
        client = Client()
        client.login(username="treasury_other", password="pass12345")
        session = client.session
        session["current_church_id"] = str(other.id)
        session.save()
        response = client.get(reverse("contributions:campaign_detail", args=[self.funeral.pk]))
        self.assertEqual(response.status_code, 404)

    def test_remit_view_posts_journal(self):
        record_member_contribution(
            self.funeral,
            member=self.member,
            amount=Decimal("40.00"),
            performed_by=self.treasurer,
            idempotency_key="funeral-gift-view-1",
        )
        client = Client()
        client.login(username="treasury_cc", password="pass12345")
        session = client.session
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = client.post(
            reverse("contributions:campaign_remit", args=[self.funeral.pk]),
            {
                "amount": "40.00",
                "payment_account_type": "BANK",
                "notes": "Send to district",
                "idempotency_key": "funeral-remit-view-1",
            },
        )
        self.assertEqual(response.status_code, 302)
        from contributions.models import CampaignRemittance

        self.assertEqual(CampaignRemittance.objects.filter(campaign=self.funeral).count(), 1)

    def test_remit_defaults_to_cash(self):
        form = RemitCampaignForm()
        self.assertEqual(form.fields["payment_account_type"].initial, "CASH")
        record_member_contribution(
            self.funeral,
            member=self.member,
            amount=Decimal("25.00"),
            performed_by=self.treasurer,
            idempotency_key="funeral-gift-cash-default",
        )
        row = remit_district_funeral_campaign(
            self.funeral,
            performed_by=self.treasurer,
            amount=Decimal("25.00"),
            idempotency_key="funeral-remit-cash-default",
        )
        credit = row.transaction.lines.get(amount__lt=0)
        self.assertEqual(credit.account.account_type, "CASH")

    def test_district_treasury_lists_campaigns_by_church(self):
        from permissions.org_scope import apply_org_scope
        from transactions.services import ensure_district_funeral_offering_category

        other = Church.objects.create(
            name="Sister Church",
            code="CH2",
            district=self.church.district,
        )
        other_cat = ensure_district_funeral_offering_category(other)
        create_campaign(
            other,
            performed_by=self.treasurer,
            name="Other church funeral",
            purpose="District funeral collection.",
            deadline=timezone.localdate() + timedelta(days=14),
            offering_category=other_cat,
            kind=CampaignKind.DISTRICT_FUNERAL,
        )
        officer = User.objects.create_user(
            username="district_treas_cc",
            password="pass12345",
            role=UserRole.DISTRICT_TREASURY,
            church=self.church,
        )
        apply_org_scope(
            officer,
            role=UserRole.DISTRICT_TREASURY,
            church=self.church,
            district=self.church.district,
        )
        officer.save()
        client = Client()
        client.login(username="district_treas_cc", password="pass12345")
        response = client.get(reverse("contributions:campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sister Mensah funeral")
        self.assertContains(response, "Other church funeral")
        self.assertContains(response, "Sister Church")
        export = client.get(reverse("contributions:campaign_list"), {"export": "csv"})
        self.assertEqual(export.status_code, 200)
        self.assertContains(export, "Other church funeral")
