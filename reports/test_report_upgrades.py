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


class ProfitLossGridTests(SimpleTestCase):
    def test_month_columns_span_year(self):
        from reports.profit_loss_grid import _month_columns
        from datetime import date

        cols = _month_columns(date(2025, 1, 1), date(2025, 3, 15))
        self.assertEqual(len(cols), 3)
        self.assertEqual(cols[0]["label"], "Jan")

    def test_grid_template_renders_total_row_labels(self):
        from decimal import Decimal

        from django.template import Context, Template

        snippet = Template(
            '{% with pl=data.profit_loss_grid %}{{ pl.labels.total_income }}{% endwith %}'
        )
        html = snippet.render(
            Context(
                {
                    "data": {
                        "profit_loss_grid": {
                            "labels": {"total_income": "Total receipts"},
                        }
                    }
                }
            )
        )
        self.assertEqual(html, "Total receipts")

    def test_grid_include_shows_total_labels(self):
        from decimal import Decimal

        from django.template.loader import render_to_string
        from django.test import RequestFactory

        from reports.profit_loss_grid import GRID_LABELS

        rf = RequestFactory()
        request = rf.get("/reports/end_of_year_detailed/")
        data = {
            "profit_loss_grid": {
                "title": "Monthly income and expense (posted books)",
                "labels": GRID_LABELS,
                "columns": [{"label": "Jan", "key": "2025-01"}],
                "income_rows": [],
                "expense_rows": [],
                "income_totals": [Decimal("0")],
                "expense_totals": [Decimal("0")],
                "net_totals": [Decimal("0")],
                "grand_income": Decimal("0"),
                "grand_expense": Decimal("0"),
                "grand_net": Decimal("0"),
                "net_positive": True,
            },
            "drill_query": "start_date=2025-01-01&end_date=2025-12-31",
        }
        html = render_to_string(
            "reports/includes/profit_loss_grid.html",
            {"data": data, "request": request},
        )
        self.assertIn("Total receipts", html)
        self.assertIn("Total expense", html)
        self.assertIn("Net total", html)


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