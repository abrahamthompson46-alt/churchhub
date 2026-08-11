"""Institution Super Admin branding self-service tests."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.forms import InstitutionBrandingForm
from accounts.models import UserActivityLog
from accounts.mfa import SESSION_MFA_VERIFIED, enable_mfa_for_user, generate_totp_secret
from organization.models import Church, Conference, District, Zone
from permissions.checks import can_manage_institution_branding
from permissions.roles import UserRole
from sitecontrol.models import Denomination

User = get_user_model()


class InstitutionBrandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="brand-tenant",
            name="Brand Tenant",
            display_name="Brand Tenant",
            allow_institution_branding=True,
            primary_color="#1e3a5f",
            accent_color="#1d4ed8",
            highlight_color="#0e7490",
        )
        cls.other_denomination = Denomination.objects.create(
            code="other-tenant",
            name="Other Tenant",
            display_name="Other Tenant",
            allow_institution_branding=True,
        )
        cls.conference = Conference.objects.create(
            code="BT1",
            name="Brand Conference",
            denomination=cls.denomination,
        )
        cls.zone = Zone.objects.create(
            conference=cls.conference,
            code="BZ1",
            name="Brand Zone",
        )
        cls.district = District.objects.create(
            zone=cls.zone,
            code="BD1",
            name="Brand District",
        )
        cls.church = Church.objects.create(
            district=cls.district,
            code="BC1",
            name="Brand Church",
        )

    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username="tenant_sa",
            password="pass12345",
            role=UserRole.SUPER_ADMIN,
            church=self.church,
            denomination=self.denomination,
        )
        enable_mfa_for_user(self.super_admin, generate_totp_secret(), [])
        self.pastor = User.objects.create_user(
            username="local_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        enable_mfa_for_user(self.pastor, generate_totp_secret(), [])
        self.platform_owner = User.objects.create_user(
            username="platform_owner",
            password="pass12345",
            is_platform_user=True,
            platform_role="OWNER",
            is_staff=True,
        )

    def _login(self, user):
        self.client.login(username=user.username, password="pass12345")
        session = self.client.session
        session[SESSION_MFA_VERIFIED] = True
        session.save()

    def test_super_admin_can_update_own_branding(self):
        self._login(self.super_admin)
        response = self.client.post(
            reverse("accounts:institution_branding"),
            {
                "display_name": "Updated Tenant Name",
                "tagline": "Faithful operations",
                "primary_color": "#112233",
                "accent_color": "#445566",
                "highlight_color": "#778899",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.denomination.refresh_from_db()
        self.assertEqual(self.denomination.display_name, "Updated Tenant Name")
        self.assertEqual(self.denomination.tagline, "Faithful operations")
        self.assertEqual(self.denomination.primary_color, "#112233")
        audit = UserActivityLog.objects.filter(
            action="INSTITUTION_BRANDING_UPDATE",
            user=self.super_admin,
        ).latest("created_at")
        self.assertIn("display_name", audit.details["changed_fields"])
        self.assertNotIn("logo", str(audit.details))

    def test_flag_off_denies_super_admin(self):
        self.denomination.allow_institution_branding = False
        self.denomination.save(update_fields=["allow_institution_branding", "updated_at"])
        self.assertFalse(can_manage_institution_branding(self.super_admin))
        self._login(self.super_admin)
        response = self.client.get(reverse("accounts:institution_branding"))
        self.assertEqual(response.status_code, 403)

    def test_non_super_admin_denied(self):
        self.assertFalse(can_manage_institution_branding(self.pastor))
        self._login(self.pastor)
        response = self.client.get(reverse("accounts:institution_branding"))
        self.assertEqual(response.status_code, 403)

    def test_platform_user_denied(self):
        self.assertFalse(can_manage_institution_branding(self.platform_owner))
        self._login(self.platform_owner)
        response = self.client.get(reverse("accounts:institution_branding"))
        # Lane middleware redirects platform operators away from institution settings.
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            self.assertNotEqual(response.url, reverse("accounts:institution_branding"))

    def test_tampered_denomination_id_is_ignored(self):
        self._login(self.super_admin)
        response = self.client.post(
            reverse("accounts:institution_branding"),
            {
                "id": str(self.other_denomination.pk),
                "display_name": "Should Apply To Own Tenant",
                "tagline": "",
                "primary_color": "#abcdef",
                "accent_color": "#1d4ed8",
                "highlight_color": "#0e7490",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.denomination.refresh_from_db()
        self.other_denomination.refresh_from_db()
        self.assertEqual(self.denomination.display_name, "Should Apply To Own Tenant")
        self.assertEqual(self.other_denomination.display_name, "Other Tenant")

    def test_form_rejects_svg_logo(self):
        form = InstitutionBrandingForm(
            {
                "display_name": "Brand Tenant",
                "tagline": "",
                "primary_color": "#1e3a5f",
                "accent_color": "#1d4ed8",
                "highlight_color": "#0e7490",
            },
            {
                "logo": SimpleUploadedFile(
                    "icon.svg",
                    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    content_type="image/svg+xml",
                )
            },
            instance=self.denomination,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)

    @override_settings()
    def test_form_rejects_oversized_branding_logo(self):
        from church_system.uploads import MAX_BRANDING_BYTES

        form = InstitutionBrandingForm(
            {
                "display_name": "Brand Tenant",
                "tagline": "",
                "primary_color": "#1e3a5f",
                "accent_color": "#1d4ed8",
                "highlight_color": "#0e7490",
            },
            {
                "logo": SimpleUploadedFile(
                    "logo.png",
                    b"x" * (MAX_BRANDING_BYTES + 1),
                    content_type="image/png",
                )
            },
            instance=self.denomination,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)

    def test_platform_branding_form_exposes_allow_toggle(self):
        from sitecontrol.denomination_forms import DenominationBrandingForm

        form = DenominationBrandingForm(
            {
                "display_name": "Brand Tenant",
                "tagline": "",
                "primary_color": "#1e3a5f",
                "accent_color": "#1d4ed8",
                "highlight_color": "#0e7490",
                "registration_intro": "",
                "allow_public_registration": "on",
                "default_role": UserRole.LOCAL_PASTOR,
            },
            instance=self.denomination,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertFalse(saved.allow_institution_branding)
