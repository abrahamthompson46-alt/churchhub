"""Owner email when a demo is requested or a tenant reports payment."""

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from organization.models import Conference, District, Zone
from sitecontrol.activation_services import submit_activation_request
from sitecontrol.commercial_notifications import owner_notification_emails
from sitecontrol.marketing_services import get_marketing_settings
from sitecontrol.models import SiteSettings
from sitecontrol.registration_services import submit_tenant_application
from sitecontrol.services import clear_settings_cache, ensure_default_plans
from sitecontrol.test_support import SiteControlClientHarness

DEMO_PASSWORD = "Tr1alLocked!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CHURCHHUB_ASYNC_EMAIL=False,
)
class CommercialOwnerEmailTests(SiteControlClientHarness, TestCase):
    def setUp(self):
        self.disable_privileged_mfa()
        ensure_default_plans()
        from sitecontrol.denomination_services import ensure_builtin_denominations
        from sitecontrol.models import Denomination

        ensure_builtin_denominations()
        self.denomination = Denomination.objects.get(code="demo")
        conf = Conference.objects.create(
            name="NotifyConf", code="NC1", denomination=self.denomination
        )
        zone = Zone.objects.create(name="NotifyZone", code="NZ1", conference=conf)
        self.district = District.objects.create(name="NotifyDist", code="ND1", zone=zone)
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = True
        settings_obj.auto_provision_public_trials = True
        settings_obj.public_demo_trial_days = 30
        settings_obj.mfa_required_for_privileged = False
        settings_obj.support_email = "support@churchhub.local"
        settings_obj.save()
        clear_settings_cache()
        marketing = get_marketing_settings()
        marketing.sales_notification_email = "owner@churchhub.test"
        marketing.save(update_fields=["sales_notification_email", "updated_at"])
        mail.outbox.clear()

    def _payload(self, **overrides):
        data = {
            "application_type": "EXISTING_DISTRICT",
            "denomination": self.denomination,
            "church_name": "Notify Chapel",
            "church_code": "NT01",
            "district": self.district,
            "contact_name": "Pastor Ada",
            "contact_email": "ada.notify@demo.test",
            "contact_phone": "+233 24 111 2222",
            "applicant_username": "pastoranotify",
            "password": DEMO_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_owner_inbox_prefers_sales_email(self):
        self.assertEqual(owner_notification_emails(), ["owner@churchhub.test"])

    def test_demo_request_emails_owner(self):
        with self.captureOnCommitCallbacks(execute=True):
            app = submit_tenant_application(self._payload())
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["owner@churchhub.test"])
        self.assertIn("Notify Chapel", message.subject)
        self.assertIn("ada.notify@demo.test", message.body)
        self.assertIn(reverse("sitecontrol:application_detail", args=[app.pk]), message.body)

    def test_payment_report_emails_owner(self):
        with self.captureOnCommitCallbacks(execute=True):
            app = submit_tenant_application(self._payload())
        mail.outbox.clear()
        church = app.created_church
        subscription = church.subscription
        with self.captureOnCommitCallbacks(execute=True):
            request = submit_activation_request(
                church=church,
                subscription=subscription,
                user=None,
                cleaned_data={
                    "church_name": church.name,
                    "church_code": church.code,
                    "church_address": "",
                    "contact_name": "Pastor Ada",
                    "contact_email": "ada.notify@demo.test",
                    "contact_phone": "",
                    "payment_reference": "MOMO-9001",
                    "billing_interval": "MONTHLY",
                    "notes": "",
                    "requested_plan": subscription.plan,
                },
            )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["owner@churchhub.test"])
        self.assertIn("MOMO-9001", message.body)
        self.assertIn("Payment reported", message.subject)
        self.assertIn(
            reverse("sitecontrol:activation_request_detail", args=[request.pk]),
            message.body,
        )
