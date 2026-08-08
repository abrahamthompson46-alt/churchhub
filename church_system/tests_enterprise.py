"""Tests for enterprise infrastructure (health, idempotency, email, validators)."""

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from accounts.validators import PlatformMinimumLengthValidator
from church_system.email_service import smtp_configured
from organization.models import Church, Conference, District, Zone
from sitecontrol.models import SiteSettings
from transactions.idempotency import IdempotencyReplay, claim_financial_idempotency, complete_financial_idempotency
from transactions.models import FinancialIdempotencyKey
from transactions.services import open_working_day, record_expense

User = get_user_model()


class HealthCheckTests(TestCase):
    def test_health_endpoint_ok(self):
        response = Client().get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["checks"]["database"], "ok")
        self.assertEqual(data["checks"]["cache"], "ok")
        self.assertEqual(data["checks"]["migrations"], "ok")
        self.assertEqual(data["checks"]["debug"], "ok")


class IdempotencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="C", code="C1")
        zone = Zone.objects.create(name="Z", code="Z1", conference=conf)
        district = District.objects.create(name="D", code="D1", zone=zone)
        cls.church = Church.objects.create(name="Ch", code="CH1", district=district)
        cls.user = User.objects.create_user(username="treasury_i", password="pass12345", church=cls.church)
        cls.approver = User.objects.create_user(
            username="pastor_i", password="pass12345", role="LOCAL_PASTOR", church=cls.church
        )
        open_working_day(cls.church, timezone.localdate(), cls.approver)

    def test_duplicate_key_raises_replay(self):
        key = str(uuid.uuid4())
        record = claim_financial_idempotency(self.church, self.user, "EXPENSE", key)
        txn = record_expense(self.church, self.user, Decimal("10.00"))
        complete_financial_idempotency(record, txn)
        with self.assertRaises(IdempotencyReplay):
            claim_financial_idempotency(self.church, self.user, "EXPENSE", key)
        self.assertEqual(FinancialIdempotencyKey.objects.filter(idempotency_key=key).count(), 1)


class EmailConfigTests(TestCase):
    def setUp(self):
        from sitecontrol.services import clear_settings_cache

        clear_settings_cache()
        site = SiteSettings.load()
        site.smtp_host = ""
        site.smtp_username = ""
        site.smtp_password = ""
        site.smtp_password_encrypted = ""
        site.default_from_email = ""
        site.save()
        clear_settings_cache()

    def test_smtp_not_configured_by_default(self):
        self.assertFalse(smtp_configured())

    def test_smtp_configured_from_site_settings(self):
        from church_system.email_service import resolve_smtp_config
        from sitecontrol.services import clear_settings_cache

        site = SiteSettings.load()
        site.smtp_host = "smtp.example.com"
        site.smtp_port = 587
        site.smtp_use_tls = True
        site.default_from_email = "noreply@example.com"
        site.smtp_username = "mailer"
        site.save()
        clear_settings_cache()

        self.assertTrue(smtp_configured())
        cfg = resolve_smtp_config()
        self.assertEqual(cfg.host, "smtp.example.com")
        self.assertEqual(cfg.from_email, "noreply@example.com")
        self.assertTrue(cfg.use_tls)
        self.assertFalse(cfg.use_ssl)

    def test_invitation_email_sends_when_smtp_resolved(self):
        from django.core import mail
        from unittest.mock import patch

        from accounts.services import create_invitation, send_invitation_email
        from organization.models import Church, Conference, District, Zone
        from permissions.roles import UserRole
        from sitecontrol.services import clear_settings_cache

        conf = Conference.objects.create(name="EC", code="EC1")
        zone = Zone.objects.create(name="EZ", code="EZ1", conference=conf)
        district = District.objects.create(name="ED", code="ED1", zone=zone)
        church = Church.objects.create(name="ECh", code="ECH1", district=district)
        inviter = User.objects.create_user(
            username="inviter_email",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=church,
        )
        site = SiteSettings.load()
        site.smtp_host = "smtp.example.com"
        site.default_from_email = "noreply@example.com"
        site.save()
        clear_settings_cache()

        invitation = create_invitation(
            email="newmember@example.com",
            username="newmember",
            role=UserRole.MEMBER,
            church=church,
            invited_by=inviter,
        )
        with patch("church_system.email_service.get_platform_connection") as mock_conn:
            from django.core.mail import get_connection

            mock_conn.return_value = get_connection(
                "django.core.mail.backends.locmem.EmailBackend"
            )
            sent = send_invitation_email(invitation, fail_silently=False)
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("invited", mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ["newmember@example.com"])

    def test_churchless_tree_admin_invitation_email_sends(self):
        from django.core import mail
        from unittest.mock import patch

        from accounts.services import create_invitation, send_invitation_email
        from permissions.org_scope import OrgScopeLevel
        from permissions.roles import UserRole
        from sitecontrol.models import Denomination
        from sitecontrol.services import clear_settings_cache

        denomination = Denomination.objects.create(
            name="Regional Fellowship",
            display_name="Regional Fellowship",
            code="regional-fellowship",
            is_active=True,
        )
        inviter = User.objects.create_user(
            username="tenant_super_admin",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            denomination=denomination,
        )
        site = SiteSettings.load()
        site.smtp_host = "smtp.example.com"
        site.default_from_email = "noreply@example.com"
        site.save()
        clear_settings_cache()

        invitation = create_invitation(
            email="conference.admin@example.com",
            username="conference_admin",
            role=UserRole.CONFERENCE_ADMIN,
            church=None,
            denomination=denomination,
            scope_level=OrgScopeLevel.DENOMINATION,
            invited_by=inviter,
        )
        with patch("church_system.email_service.get_platform_connection") as mock_conn:
            from django.core.mail import get_connection

            mock_conn.return_value = get_connection(
                "django.core.mail.backends.locmem.EmailBackend"
            )
            sent = send_invitation_email(invitation, fail_silently=False)

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Regional Fellowship", mail.outbox[0].subject)
        self.assertIn("Regional Fellowship", mail.outbox[0].body)
        self.assertIn(str(invitation.token), mail.outbox[0].body)

    def test_get_platform_connection_uses_smtp_backend_not_platform_wrapper(self):
        """Regression: must not recurse when EMAIL_BACKEND is PlatformSMTPEmailBackend."""
        from django.core.mail.backends.smtp import EmailBackend
        from django.test import override_settings

        from church_system.email_service import get_platform_connection
        from sitecontrol.services import clear_settings_cache

        site = SiteSettings.load()
        site.smtp_host = "smtp.example.com"
        site.default_from_email = "noreply@example.com"
        site.save()
        clear_settings_cache()

        with override_settings(EMAIL_BACKEND="church_system.mail.PlatformSMTPEmailBackend"):
            conn = get_platform_connection()
        self.assertIsInstance(conn, EmailBackend)

class PasswordValidatorTests(TestCase):
    def test_platform_min_length_from_settings(self):
        site = SiteSettings.load()
        site.password_min_length = 10
        site.save()
        validator = PlatformMinimumLengthValidator()
        with self.assertRaises(Exception):
            validator.validate("short")

    def test_get_help_text_returns_string(self):
        site = SiteSettings.load()
        site.password_min_length = 12
        site.save()
        help_text = PlatformMinimumLengthValidator().get_help_text()
        self.assertIn("12", help_text)
