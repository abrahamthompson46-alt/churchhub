"""Security and workflow tests for the Platform Owner Marketing Hub."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from sitecontrol.marketing_forms import MarketingAssetForm, MarketingSettingsForm
from sitecontrol.marketing_services import create_public_lead, get_marketing_settings
from sitecontrol.models import (
    Denomination,
    MarketingCampaign,
    MarketingLead,
    PlatformAuditLog,
)
from sitecontrol.test_support import SiteControlClientHarness


@override_settings(CHURCHHUB_PUBLIC_URL="https://mychurch.example.com")
class MarketingHubTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        cache.clear()
        self.owner = User.objects.create_user(
            username="marketing-owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
        )
        self.support = User.objects.create_user(
            username="marketing-support",
            password="pass12345",
            is_platform_user=True,
            platform_role="SUPPORT",
        )
        self.denomination = Denomination.objects.create(
            name="Marketing Denomination",
            code="marketing-denom",
            is_active=True,
            allow_public_registration=True,
        )
        self.settings_obj = get_marketing_settings()
        self.settings_obj.public_inquiry_enabled = True
        self.settings_obj.notify_on_new_lead = False
        self.settings_obj.privacy_policy_url = "https://example.com/privacy"
        self.settings_obj.save()

    def _lead_payload(self, **overrides):
        payload = {
            "contact_name": "Prospect Person",
            "contact_email": "prospect@example.com",
            "contact_phone": "+233200000000",
            "organization_name": "Prospect Church",
            "denomination": str(self.denomination.pk),
            "message": "We need a guided demonstration.",
            "consent": "on",
            "campaign_slug": "",
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
            "website": "",
        }
        payload.update(overrides)
        return payload

    def test_owner_sees_marketing_navigation_and_hub(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("sitecontrol:marketing_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketing Hub")
        self.assertContains(response, reverse("marketing_inquiry"))

    def test_non_owner_platform_role_is_denied(self):
        self.client.force_login(self.support)
        response = self.client.get(reverse("sitecontrol:marketing_hub"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_from_owner_hub(self):
        response = self.client.get(reverse("sitecontrol:marketing_hub"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_public_inquiry_get_and_csrf_protection(self):
        response = self.client.get(reverse("marketing_inquiry"))
        self.assertEqual(response.status_code, 200)
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse("marketing_inquiry"), self._lead_payload())
        self.assertEqual(response.status_code, 403)

    def test_public_inquiry_creates_consent_and_redacted_audit(self):
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(message="<script>alert('x')</script>"),
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertRedirects(response, reverse("marketing_inquiry_success"))
        lead = MarketingLead.objects.get()
        self.assertTrue(lead.consent_given)
        self.assertEqual(lead.denomination, self.denomination)
        self.assertEqual(lead.ip_address, "203.0.113.10")
        audit = PlatformAuditLog.objects.get(action="MARKETING_LEAD_SUBMIT")
        self.assertNotIn("prospect@example.com", str(audit.details))
        self.assertNotIn("script", str(audit.details))

        self.client.force_login(self.owner)
        detail = self.client.get(
            reverse("sitecontrol:marketing_lead_detail", args=[lead.pk])
        )
        self.assertNotContains(detail, "<script>alert('x')</script>", html=False)
        self.assertContains(detail, "&lt;script&gt;", html=False)

    def test_active_campaign_controls_attribution(self):
        campaign = MarketingCampaign.objects.create(
            name="Facebook Launch",
            slug="facebook-launch",
            status="ACTIVE",
            source="facebook",
            medium="paid-social",
            campaign_tag="launch-2026",
            created_by=self.owner,
        )
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(
                campaign_slug=campaign.slug,
                utm_source="tampered",
                utm_medium="tampered",
                utm_campaign="tampered",
            ),
        )
        self.assertEqual(response.status_code, 302)
        lead = MarketingLead.objects.get()
        self.assertEqual(lead.campaign, campaign)
        self.assertEqual(lead.utm_source, "facebook")
        self.assertEqual(lead.utm_medium, "paid-social")
        self.assertEqual(lead.utm_campaign, "launch-2026")

    def test_service_rejects_inactive_denomination(self):
        self.denomination.is_active = False
        self.denomination.save(update_fields=["is_active"])
        cleaned = {
            "contact_name": "Scoped Lead",
            "contact_email": "scoped@example.com",
            "contact_phone": "",
            "organization_name": "",
            "denomination": self.denomination,
            "message": "",
            "consent": True,
            "campaign_slug": "",
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
        }
        with self.assertRaisesRegex(ValueError, "active denomination"):
            create_public_lead(cleaned, ip_address="203.0.113.31")
        self.assertFalse(MarketingLead.objects.exists())

    def test_honeypot_blocks_spam(self):
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(website="https://spam.invalid"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MarketingLead.objects.exists())
        self.assertContains(response, "Unable to submit this inquiry")

    def test_inquiry_rate_limit(self):
        for number in range(5):
            response = self.client.post(
                reverse("marketing_inquiry"),
                self._lead_payload(contact_email=f"prospect{number}@example.com"),
                REMOTE_ADDR="203.0.113.20",
            )
            self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(contact_email="blocked@example.com"),
            REMOTE_ADDR="203.0.113.20",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(MarketingLead.objects.count(), 5)

    def test_invalid_forms_do_not_exhaust_rate_limit(self):
        for _ in range(7):
            response = self.client.post(
                reverse("marketing_inquiry"),
                self._lead_payload(consent=""),
                REMOTE_ADDR="203.0.113.21",
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(),
            REMOTE_ADDR="203.0.113.21",
        )
        self.assertEqual(response.status_code, 302)

    def test_per_email_rate_limit_across_ips(self):
        for number in range(3):
            response = self.client.post(
                reverse("marketing_inquiry"),
                self._lead_payload(contact_email="repeat@example.com"),
                REMOTE_ADDR=f"203.0.113.{40 + number}",
            )
            self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("marketing_inquiry"),
            self._lead_payload(contact_email="repeat@example.com"),
            REMOTE_ADDR="203.0.113.50",
        )
        self.assertEqual(response.status_code, 429)

    def test_notification_failure_does_not_discard_lead(self):
        self.settings_obj.notify_on_new_lead = True
        self.settings_obj.sales_notification_email = "sales@example.com"
        self.settings_obj.save()
        cleaned = {
            "contact_name": "Persistent Lead",
            "contact_email": "persistent@example.com",
            "contact_phone": "",
            "organization_name": "",
            "denomination": self.denomination,
            "message": "",
            "consent": True,
            "campaign_slug": "",
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
        }
        with patch(
            "sitecontrol.marketing_services.send_lead_notification",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                lead, _ = create_public_lead(
                    cleaned,
                    ip_address="203.0.113.30",
                )
        self.assertTrue(MarketingLead.objects.filter(pk=lead.pk).exists())
        lead.refresh_from_db()
        self.assertEqual(lead.notification_status, "FAILED")
        self.assertEqual(lead.notification_error_code, "RuntimeError")

    def test_public_enable_requires_privacy_policy(self):
        form = MarketingSettingsForm(
            {
                "public_inquiry_enabled": True,
                "sales_notification_email": "",
                "marketing_site_url": "https://example.com",
                "privacy_policy_url": "",
                "consent_text": "Consent text",
                "notify_on_new_lead": False,
                "lead_retention_days": 365,
            },
            instance=self.settings_obj,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("privacy_policy_url", form.errors)

    def test_owner_can_export_leads_with_csv_injection_protection(self):
        MarketingLead.objects.create(
            contact_name="=SUM(1,1)",
            contact_email="export@example.com",
            consent_given=True,
            consent_text="Consent",
            consented_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        response = self.client.post(reverse("sitecontrol:marketing_lead_export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("'=SUM(1,1)", response.content.decode())
        self.assertTrue(
            PlatformAuditLog.objects.filter(action="MARKETING_LEAD_EXPORT").exists()
        )

    def test_non_owner_cannot_export_leads(self):
        self.client.force_login(self.support)
        response = self.client.post(reverse("sitecontrol:marketing_lead_export"))
        self.assertEqual(response.status_code, 403)

    def test_closed_lead_can_be_anonymized_with_audit(self):
        lead = MarketingLead.objects.create(
            status="CLOSED",
            contact_name="Privacy Person",
            contact_email="privacy@example.com",
            contact_phone="+233200000000",
            organization_name="Privacy Church",
            message="Private message",
            internal_notes="Private notes",
            consent_given=True,
            consent_text="Consent",
            consented_at=timezone.now(),
            ip_address="203.0.113.60",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("sitecontrol:marketing_lead_anonymize", args=[lead.pk])
        )
        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertIsNotNone(lead.anonymized_at)
        self.assertEqual(lead.contact_name, "Anonymized lead")
        self.assertEqual(lead.contact_phone, "")
        self.assertEqual(lead.message, "")
        self.assertIsNone(lead.ip_address)
        audit = PlatformAuditLog.objects.filter(
            action="MARKETING_LEAD_ANONYMIZE"
        ).latest("created_at")
        self.assertNotIn("privacy@example.com", str(audit.details))

    def test_retention_anonymizes_only_old_closed_leads(self):
        from sitecontrol.marketing_services import anonymize_expired_leads

        old_closed = MarketingLead.objects.create(
            status="CLOSED",
            contact_name="Old Closed",
            contact_email="old@example.com",
            consent_given=True,
            consent_text="Consent",
            consented_at=timezone.now() - timedelta(days=500),
        )
        active = MarketingLead.objects.create(
            status="QUALIFIED",
            contact_name="Active Lead",
            contact_email="active@example.com",
            consent_given=True,
            consent_text="Consent",
            consented_at=timezone.now() - timedelta(days=500),
        )
        MarketingLead.objects.filter(pk__in=[old_closed.pk, active.pk]).update(
            created_at=timezone.now() - timedelta(days=500)
        )
        count = anonymize_expired_leads(actor=self.owner)
        self.assertEqual(count, 1)
        old_closed.refresh_from_db()
        active.refresh_from_db()
        self.assertIsNotNone(old_closed.anonymized_at)
        self.assertIsNone(active.anonymized_at)

    def test_lead_update_is_audited_without_contact_pii(self):
        lead = MarketingLead.objects.create(
            contact_name="Workflow Lead",
            contact_email="workflow@example.com",
            consent_given=True,
            consent_text="Consent",
            consented_at=self.settings_obj.updated_at,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("sitecontrol:marketing_lead_detail", args=[lead.pk]),
            {
                "status": "QUALIFIED",
                "assigned_to": str(self.owner.pk),
                "internal_notes": "Call next week.",
            },
        )
        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "QUALIFIED")
        audit = PlatformAuditLog.objects.filter(action="MARKETING_LEAD_UPDATE").latest(
            "created_at"
        )
        self.assertEqual(audit.details["new_status"], "QUALIFIED")
        self.assertNotIn("workflow@example.com", str(audit.details))
        self.assertNotIn("Call next week", str(audit.details))

    def test_marketing_urls_must_use_https(self):
        settings_form = MarketingSettingsForm(
            {
                "public_inquiry_enabled": True,
                "sales_notification_email": "sales@example.com",
                "marketing_site_url": "http://example.com",
                "privacy_policy_url": "https://example.com/privacy",
                "consent_text": "Consent text",
                "notify_on_new_lead": True,
            },
            instance=self.settings_obj,
        )
        self.assertFalse(settings_form.is_valid())
        self.assertIn("marketing_site_url", settings_form.errors)

        asset_form = MarketingAssetForm(
            {
                "title": "Brochure",
                "description": "",
                "asset_type": "BROCHURE",
                "audience": "Pastors",
                "public_url": "http://example.com/brochure.pdf",
                "status": "APPROVED",
                "sort_order": 1,
            }
        )
        self.assertFalse(asset_form.is_valid())
        self.assertIn("public_url", asset_form.errors)
