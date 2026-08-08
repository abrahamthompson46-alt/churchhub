"""Regression tests for proxy-aware client IP resolution."""

from django.test import RequestFactory, SimpleTestCase, override_settings

from church_system.client_ip import get_client_ip


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        TRUST_X_FORWARDED_FOR=True,
        TRUSTED_PROXY_IPS=["127.0.0.1", "10.0.0.0/8"],
    )
    def test_trusted_proxy_may_supply_forwarded_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 10.0.0.1",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.10")

    @override_settings(
        TRUST_X_FORWARDED_FOR=True,
        TRUSTED_PROXY_IPS=["127.0.0.1"],
    )
    def test_untrusted_remote_cannot_spoof_forwarded_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.20",
            HTTP_X_FORWARDED_FOR="203.0.113.99",
        )
        self.assertEqual(get_client_ip(request), "198.51.100.20")

    @override_settings(
        TRUST_X_FORWARDED_FOR=True,
        TRUSTED_PROXY_IPS=["127.0.0.1"],
    )
    def test_invalid_forwarded_value_falls_back_to_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="not-an-ip",
        )
        self.assertEqual(get_client_ip(request), "127.0.0.1")

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_forwarded_ip_is_ignored_when_disabled(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.21",
            HTTP_X_FORWARDED_FOR="203.0.113.100",
        )
        self.assertEqual(get_client_ip(request), "198.51.100.21")
