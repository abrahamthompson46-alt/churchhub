from django.test import RequestFactory, SimpleTestCase, override_settings

from church_system.public_urls import (
    build_public_absolute_uri,
    normalize_public_site_base,
    resolve_public_site_base,
    resolve_pythonanywhere_public_url,
)


class PublicUrlTests(SimpleTestCase):
    def test_strips_dashboard_suffix_from_public_url(self):
        self.assertEqual(
            normalize_public_site_base("https://churchhub.pythonanywhere.com/dashboard"),
            "https://churchhub.pythonanywhere.com",
        )

    def test_pythonanywhere_ignores_www_marketing_host(self):
        import os

        previous = os.environ.get("PYTHONANYWHERE_SITE")
        os.environ["PYTHONANYWHERE_SITE"] = "churchhub.pythonanywhere.com"
        try:
            resolved = resolve_pythonanywhere_public_url("https://www.pythonanywhere.com")
            self.assertEqual(resolved, "https://churchhub.pythonanywhere.com")
        finally:
            if previous is None:
                os.environ.pop("PYTHONANYWHERE_SITE", None)
            else:
                os.environ["PYTHONANYWHERE_SITE"] = previous

    @override_settings(
        DEBUG=False,
        CHURCHHUB_PUBLIC_URL="http://localhost:8000",
        CSRF_TRUSTED_ORIGINS=["https://church.example.com"],
        ALLOWED_HOSTS=["church.example.com"],
        SECURE_SSL_REDIRECT=True,
    )
    def test_ignores_localhost_public_url_in_production(self):
        self.assertEqual(
            resolve_public_site_base(),
            "https://church.example.com",
        )

    @override_settings(
        DEBUG=False,
        CHURCHHUB_PUBLIC_URL="https://app.churchhub.org",
    )
    def test_uses_configured_public_url(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="localhost:8000")
        url = build_public_absolute_uri(request, "/portal/confirm/abc/")
        self.assertTrue(url.startswith("https://app.churchhub.org/portal/confirm/"))
