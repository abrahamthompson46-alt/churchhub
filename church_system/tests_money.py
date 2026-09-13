"""Tests for canonical Decimal money helpers."""

from decimal import Decimal

from django.test import SimpleTestCase

from church_system.money import clamp_money_places, money_export_value, quantize_money


class MoneyHelpersTests(SimpleTestCase):
    def test_quantize_money_two_places_half_up(self):
        self.assertEqual(quantize_money("10.005"), Decimal("10.01"))
        self.assertEqual(quantize_money(Decimal("1.234")), Decimal("1.23"))
        self.assertEqual(quantize_money(None), Decimal("0.00"))

    def test_quantize_money_custom_places(self):
        self.assertEqual(quantize_money("10.4", places=0), Decimal("10"))
        self.assertEqual(quantize_money("10.006", places=3), Decimal("10.006"))

    def test_clamp_money_places(self):
        self.assertEqual(clamp_money_places(9), 4)
        self.assertEqual(clamp_money_places(-1), 0)
        self.assertEqual(clamp_money_places("2"), 2)

    def test_quantize_money_avoids_float_binary_artifacts(self):
        # str(0.1) path keeps Decimal('0.1') rather than binary expansion
        self.assertEqual(quantize_money(0.1), Decimal("0.10"))

    def test_money_export_value_never_returns_float(self):
        value = money_export_value(Decimal("12.50"))
        self.assertEqual(value, "12.50")
        self.assertIsInstance(value, str)
        self.assertNotIsInstance(value, float)
