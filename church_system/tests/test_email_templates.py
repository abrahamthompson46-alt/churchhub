from django.test import TestCase, override_settings

from church_system.email_service import get_email_branding_context
from django.template.loader import render_to_string


class EmailTemplateRenderTests(TestCase):
    @override_settings(
        CHURCHHUB_PUBLIC_URL="https://churchhub.example.com",
    )
    def test_portal_device_confirm_html_renders(self):
        context = {
            **get_email_branding_context(preheader="Confirm sign-in"),
            "confirm_url": "https://churchhub.example.com/portal/confirm/test/",
            "expires_hours": 24,
            "member": None,
            "ip_address": "203.0.113.1",
            "device_hint": "",
        }
        html = render_to_string("emails/portal_device_confirm.html", context)
        self.assertIn("Confirm this device", html)
        self.assertIn(context["confirm_url"], html)
        self.assertIn(context["brand_color"], html)

    @override_settings(
        CHURCHHUB_PUBLIC_URL="https://churchhub.example.com",
    )
    def test_user_invitation_html_renders(self):
        class _Inv:
            username = "clerk1"

        context = {
            **get_email_branding_context(preheader="Invitation"),
            "invitation": _Inv(),
            "accept_url": "https://churchhub.example.com/accounts/invite/accept/x/",
            "church_name": "Grace Church",
            "invited_by": "Admin User",
            "expires_at": "2026-08-01",
        }
        html = render_to_string("emails/user_invitation.html", context)
        self.assertIn("Accept invitation", html)
        self.assertIn("Grace Church", html)
