"""End-of-year report optional section toggles."""

from __future__ import annotations

EOY_SECTION_SPECS = [
    ("monthly", "Monthly giving trend"),
    ("operating", "Operating summary (tithe, income, expense)"),
    ("income_statement", "Income statement detail"),
    ("balance_sheet", "Balance sheet (period end)"),
    ("cash", "Cash & bank (period end)"),
    ("membership", "Membership & attendance"),
    ("budget", "Budget vs actual (optional)"),
    ("settlement", "Settlement register summary (optional)"),
    ("payroll", "Payroll summary (optional)"),
]

EOY_SECTION_KEYS = [key for key, _ in EOY_SECTION_SPECS]


def _flag_on(raw) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def default_eoy_sections() -> dict[str, bool]:
    return {key: key not in ("budget", "settlement", "payroll") for key in EOY_SECTION_KEYS}


def parse_eoy_sections(get_params) -> dict[str, bool]:
    """Parse ``eoy_<key>`` query params; default all core sections on first run."""
    if get_params is None:
        return default_eoy_sections()
    if not any(f"eoy_{key}" in get_params for key in EOY_SECTION_KEYS):
        return default_eoy_sections()
    out = default_eoy_sections()
    for key in EOY_SECTION_KEYS:
        out[key] = _flag_on(get_params.get(f"eoy_{key}"))
    return out


def eoy_sections_for_export(get_params) -> dict[str, str]:
    return {f"eoy_{k}": "1" if v else "0" for k, v in parse_eoy_sections(get_params).items()}