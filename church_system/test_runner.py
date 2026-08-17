"""ChurchHub test runner — suite-wide harness for local + CI consistency.

Applies:
- Python 3.14-safe template context capture (Django test client crash)
- Privileged MFA off by default (individual MFA tests re-enable explicitly)
- LocMem / settings cache cleared before each test (avoids rollback pollution)
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

from django.core.cache import cache
from django.test import testcases
from django.test.client import ContextList
from django.test.runner import DiscoverRunner

# Django 6: classmethod descriptor. Django 5.1: plain function. Never use
# attribute access here — that would bind and hide the real descriptor type.
_original_pre_setup_descriptor = inspect.getattr_static(
    testcases.SimpleTestCase, "_pre_setup"
)
_pre_setup_is_classmethod = isinstance(_original_pre_setup_descriptor, classmethod)
if _pre_setup_is_classmethod:
    _original_pre_setup_func = _original_pre_setup_descriptor.__func__
else:
    _original_pre_setup_func = _original_pre_setup_descriptor


def _safe_store_rendered_templates(store, signal, sender, template, context, **kwargs):
    """Avoid Context.__copy__ / .dicts AttributeError on Python 3.14."""
    store.setdefault("templates", []).append(template)
    if "context" not in store:
        store["context"] = ContextList()
    store["context"].append(context)


def _clear_churchhub_test_caches():
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


if _pre_setup_is_classmethod:

    def _churchhub_pre_setup(cls):
        _clear_churchhub_test_caches()
        return _original_pre_setup_func(cls)

else:

    def _churchhub_pre_setup(self):
        _clear_churchhub_test_caches()
        return _original_pre_setup_func(self)


class ChurchHubDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._template_store_patcher = patch(
            "django.test.client.store_rendered_templates",
            _safe_store_rendered_templates,
        )
        self._template_store_patcher.start()
        if _pre_setup_is_classmethod:
            testcases.SimpleTestCase._pre_setup = classmethod(_churchhub_pre_setup)
        else:
            testcases.SimpleTestCase._pre_setup = _churchhub_pre_setup

    def teardown_test_environment(self, **kwargs):
        testcases.SimpleTestCase._pre_setup = _original_pre_setup_descriptor
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
