"""
Canonical money helpers — always use Decimal, never float, for currency.

Policy: two decimal places, ROUND_HALF_UP (common for church treasury / GHS).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MONEY_QUANT = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


def quantize_money(amount: Any) -> Decimal:
    """
    Normalize any numeric-like value to a Decimal money amount (2 dp).

    Accepts Decimal, int, float, or str. Floats are converted via str() to
    avoid binary float artifacts (e.g. 0.1 → Decimal('0.1') not a long binary).
    """
    if amount is None or amount == "":
        return ZERO_MONEY
    if isinstance(amount, Decimal):
        value = amount
    else:
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid money amount: {amount!r}") from exc
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def money_export_value(val: Any) -> Any:
    """
    Cell value for CSV/Excel/PDF that preserves decimal precision.

    Decimal → fixed string (never float). Other values pass through.
    """
    if val is None:
        return ""
    if isinstance(val, Decimal) or hasattr(val, "quantize"):
        return format(quantize_money(val), "f")
    return val
