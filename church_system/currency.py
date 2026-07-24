"""Currency display helpers for templates and JS."""

from __future__ import annotations

# UI amounts are plain numbers (no inline currency glyphs in tables/KPIs).
# Keep ISO fallback for unknown codes when a symbol is still requested.
CURRENCY_SYMBOLS = {
    "GHS": "",
    "USD": "",
    "EUR": "",
    "GBP": "",
    "NGN": "",
    "KES": "",
    "ZAR": "",
    "CAD": "",
    "AUD": "",
}


def normalize_currency_code(code: str | None) -> str:
    return (code or "GHS").strip().upper() or "GHS"


def currency_symbol(code: str | None = None) -> str:
    """Return a display symbol for an ISO currency code."""
    normalized = normalize_currency_code(code)
    return CURRENCY_SYMBOLS.get(normalized, f"{normalized}\u00a0")
