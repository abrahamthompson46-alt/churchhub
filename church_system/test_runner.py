"""ChurchHub test runner — suite-wide harness for local + CI consistency.

Applies:
- Python 3.14-safe template context capture (Django test client crash)
- Privileged MFA off by default (individual MFA tests re-enable explicitly)
- LocMem / settings cache cleared before each test (avoids rollback pollution)
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import testcases
from django.test.client import ContextList
from django.test.runner import DiscoverRunner

# Capture the underlying function (never a bound method). Accessing the attribute
# on the class is normally a function; if a bound method is seen, unwrap via __func__.
_pre_setup_attr = testcases.SimpleTestCase._pre_setup
_original_testcase_pre_setup = getattr(_pre_setup_attr, "__func__", _pre_setup_attr)


def _safe_store_rendered_templates(store, signal, sender, template, context, **kwargs):
    """Avoid Context.__copy__ / .dicts AttributeError on Python 3.14."""
    store.setdefault("templates", []).append(template)
    if "context" not in store:
        store["context"] = ContextList()
    store["context"].append(context)


def _churchhub_pre_setup(self):
    """Clear process-local caches that survive TestCase DB rollbacks."""
    cache.clear()
    try:
        from sitecontrol.services import clear_settings_cache

        clear_settings_cache()
    except Exception:
        pass
    try:
        from permissions.services import clear_request_permission_cache

        clear_request_permission_cache()
    except Exception:
        pass
    # Always invoke the raw function with self. The wrapper is installed as a
    # plain function on the class so Python binds instance methods correctly on
    # both Django 5.1 and 6.0.
    return _original_testcase_pre_setup(self)


class ChurchHubDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store_rendered_templates,
        )
        self._template_store_patcher.start()
        # Install unbound function — do not assign a bound method.
        testcases.SimpleTestCase._pre_setup = _churchhub_pre_setup

    def teardown_test_environment(self, **kwargs):
        testcases.SimpleTestCase._pre_setup = _original_testcase_pre_setup
        patcher = getattr(self, "_template_store_patcher", None)
        if patcher is not None:
            patcher.stop()
        super().teardown_test_environment(**kwargs)

    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        self._disable_privileged_mfa_for_suite()
        return old_config

    @staticmethod
    def _disable_privileged_mfa_for_suite():
        """Keep view/integration tests focused on domain assertions, not MFA redirects.

        MFA enforcement tests (accounts.tests_mfa) explicitly turn the flag back on.
        """
        from sitecontrol.models import SiteSettings
        from sitecontrol.services import clear_settings_cache

        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        clear_settings_cache()
