"""
Canonical money helpers — always use Decimal, never float, for currency.

Policy: ROUND_HALF_UP. Default is two decimal places; institutions may choose 0–4 for UI.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MONEY_QUANT = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")
MIN_MONEY_PLACES = 0
MAX_MONEY_PLACES = 4
DEFAULT_MONEY_PLACES = 2


def clamp_money_places(places: Any) -> int:
    """Bound display/posting decimal places to a safe 0–4 range."""
    try:
        value = int(places)
    except (TypeError, ValueError):
        value = DEFAULT_MONEY_PLACES
    return max(MIN_MONEY_PLACES, min(MAX_MONEY_PLACES, value))


def money_decimal_places(*, church=None, denomination=None) -> int:
    """Institution decimal places from the denomination SaaS tenant (default 2)."""
    if denomination is None and church is not None:
        denomination = getattr(church, "denomination", None)
    if denomination is not None:
        return clamp_money_places(getattr(denomination, "money_decimal_places", DEFAULT_MONEY_PLACES))
    return DEFAULT_MONEY_PLACES


def quantize_money(amount: Any, *, places: int | None = None) -> Decimal:
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
    dp = clamp_money_places(places) if places is not None else DEFAULT_MONEY_PLACES
    quant = Decimal("1").scaleb(-dp)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


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
