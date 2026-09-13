"""Institution Super Admin system settings tests."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserActivityLog
from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
from organization.models import Church, Conference, District, Zone
from permissions.checks import can_manage_system_settings
from permissions.roles import UserRole
from sitecontrol.models import Denomination

User = get_user_model()


class InstitutionSystemSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="ops-tenant",
            name="Ops Tenant",
            display_name="Ops Tenant",
        )
        cls.conference = Conference.objects.create(
            code="OT1",
            name="Ops Conference",
            denomination=cls.denomination,
        )
        cls.zone = Zone.objects.create(
            conference=cls.conference,
            code="OZ1",
            name="Ops Zone",
        )
        cls.district = District.objects.create(
            zone=cls.zone,
            code="OD1",
            name="Ops District",
        )
        cls.church = Church.objects.create(
            district=cls.district,
            code="OC1",
            name="Ops Church",
        )

    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username="ops_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
            denomination=self.denomination,
        )
        enable_mfa_for_user(self.super_admin, generate_totp_secret(), [])
        self.pastor = User.objects.create_user(
            username="ops_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        enable_mfa_for_user(self.pastor, generate_totp_secret(), [])

    def _login(self, user):
        self.client.login(username=user.username, password="pass12345")
        session = self.client.session
        session[SESSION_MFA_VERIFIED] = True
        session.save()

    def test_super_admin_can_update_settings(self):
        self.assertTrue(can_manage_system_settings(self.super_admin))
        self._login(self.super_admin)
        response = self.client.post(
            reverse("accounts:system_settings"),
            {
                "money_decimal_places": 0,
                "notification_retention_read_days": 60,
                "notification_retention_unread_days": 120,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.denomination.refresh_from_db()
        self.assertEqual(self.denomination.money_decimal_places, 0)
        self.assertEqual(self.denomination.notification_retention_read_days, 60)
        self.assertTrue(
            UserActivityLog.objects.filter(
                user=self.super_admin,
                action="SYSTEM_SETTINGS_UPDATE",
            ).exists()
        )

    def test_pastor_denied(self):
        self.assertFalse(can_manage_system_settings(self.pastor))
        self._login(self.pastor)
        response = self.client.get(reverse("accounts:system_settings"))
        self.assertEqual(response.status_code, 403)

    def test_unread_retention_must_meet_read_retention(self):
        self._login(self.super_admin)
        response = self.client.post(
            reverse("accounts:system_settings"),
            {
                "money_decimal_places": 2,
                "notification_retention_read_days": 90,
                "notification_retention_unread_days": 30,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.denomination.refresh_from_db()
        self.assertEqual(self.denomination.notification_retention_unread_days, 180)
