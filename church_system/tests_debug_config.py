"""Tests for safe DEBUG resolution (P0-7)."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from church_system.debug_config import is_production_like_env, resolve_debug


class DebugConfigTests(SimpleTestCase):
    def test_unset_debug_defaults_true_locally(self):
        self.assertTrue(
            resolve_debug(debug_env=None, production_like=False, allow_debug_in_prod=False)
        )

    def test_unset_debug_defaults_false_when_production_like(self):
        self.assertFalse(
            resolve_debug(debug_env=None, production_like=True, allow_debug_in_prod=False)
        )

    def test_explicit_true_allowed_locally(self):
        self.assertTrue(
            resolve_debug(debug_env=True, production_like=False, allow_debug_in_prod=False)
        )

    def test_explicit_true_rejected_on_production_like(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_debug(debug_env=True, production_like=True, allow_debug_in_prod=False)

    def test_allow_debug_in_prod_override(self):
        self.assertTrue(
            resolve_debug(debug_env=True, production_like=True, allow_debug_in_prod=True)
        )

    def test_database_url_marks_production_like(self):
        self.assertTrue(
            is_production_like_env(
                on_render=False,
                on_pythonanywhere=False,
                database_url="postgres://user:pass@host/db",
                dyno="",
            )
        )
        self.assertFalse(
            is_production_like_env(
                on_render=False,
                on_pythonanywhere=False,
                database_url="",
                dyno="",
            )
        )
