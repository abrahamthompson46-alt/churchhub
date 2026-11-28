"""Quick period presets for Report Center filters."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone


def resolve_period_preset(preset: str, *, today: date | None = None) -> tuple[str, date | None, date | None]:
    """
    Return (period_key, start_date, end_date) for a preset slug.

    ``period_key`` is passed to ``resolve_date_range``; use ``custom`` when dates are set.
    """
    today = today or timezone.now().date()
    preset = (preset or "").strip().lower()

    if preset == "last_calendar_year":
        year = today.year - 1
        return "custom", date(year, 1, 1), date(year, 12, 31)

    if preset == "current_calendar_year":
        year = today.year
        return "custom", date(year, 1, 1), date(year, 12, 31)

    if preset == "ytd":
        return "annual", None, None

    if preset == "last_month":
        first_this_month = today.replace(day=1)
        end_prev = first_this_month - timedelta(days=1)
        start_prev = end_prev.replace(day=1)
        return "custom", start_prev, end_prev

    if preset == "last_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_this_q = today.replace(month=quarter_start_month, day=1)
        end_prev = start_this_q - timedelta(days=1)
        prev_q_month = ((end_prev.month - 1) // 3) * 3 + 1
        start_prev_q = end_prev.replace(month=prev_q_month, day=1)
        return "custom", start_prev_q, end_prev

    return "monthly", None, None


REPORT_PERIOD_PRESETS = [
    ("current_calendar_year", "Current calendar year"),
    ("last_calendar_year", "Last calendar year"),
    ("ytd", "Year to date"),
    ("last_month", "Last month"),
    ("last_quarter", "Last quarter"),
]

# First open (no query string / session): default period for core GL statements.
CURRENT_YEAR_DEFAULT_REPORTS = frozenset(
    {"trial_balance", "balance_sheet", "income_statement"}
)