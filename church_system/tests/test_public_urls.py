from django.test import RequestFactory, SimpleTestCase, override_settings

from church_system.public_urls import build_public_absolute_uri, resolve_public_site_base


class PublicUrlTests(SimpleTestCase):
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
