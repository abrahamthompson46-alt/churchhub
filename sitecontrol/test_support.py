"""Shared test harness for sitecontrol view tests (MFA off + Py3.14 client)."""

from unittest.mock import patch

from django.test.client import ContextList

from sitecontrol.models import SiteSettings
from sitecontrol.services import clear_settings_cache


class SiteControlClientHarness:
    """Disable privileged MFA and avoid Django/Py3.14 template context copy crash."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def _safe_store(store, signal, sender, template, context, **kwargs):
            store.setdefault("templates", []).append(template)
            if "context" not in store:
                store["context"] = ContextList()
            store["context"].append(context)

        cls._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store,
        )
        cls._template_store_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._template_store_patcher.stop()
        super().tearDownClass()

    def disable_privileged_mfa(self):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        clear_settings_cache()
