"""Tests for report period presets and EOY section toggles."""

from datetime import date

from django.test import SimpleTestCase

from reports.eoy_sections import default_eoy_sections, parse_eoy_sections
from reports.period_presets import resolve_period_preset


class PeriodPresetTests(SimpleTestCase):
    def test_last_calendar_year(self):
        period, start, end = resolve_period_preset("last_calendar_year", today=date(2026, 6, 15))
        self.assertEqual(period, "custom")
        self.assertEqual(start, date(2025, 1, 1))
        self.assertEqual(end, date(2025, 12, 31))

    def test_last_month(self):
        period, start, end = resolve_period_preset("last_month", today=date(2026, 3, 10))
        self.assertEqual(period, "custom")
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))


class EoySectionTests(SimpleTestCase):
    def test_defaults_exclude_optional_modules(self):
        flags = default_eoy_sections()
        self.assertTrue(flags["monthly"])
        self.assertFalse(flags["budget"])

    def test_parse_explicit_off(self):
        from django.http import QueryDict

        q = QueryDict(mutable=True)
        q["eoy_monthly"] = "1"
        q["eoy_operating"] = "0"
        flags = parse_eoy_sections(q)
        self.assertTrue(flags["monthly"])
        self.assertFalse(flags["operating"])