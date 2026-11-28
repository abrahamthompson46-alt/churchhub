"""Report run view helpers: presets, session filters, query preparation."""

from __future__ import annotations

from django.http import QueryDict

from .eoy_sections import EOY_SECTION_KEYS, EOY_SECTION_SPECS, default_eoy_sections, parse_eoy_sections
from .period_presets import (
    CURRENT_YEAR_DEFAULT_REPORTS,
    REPORT_PERIOD_PRESETS,
    resolve_period_preset,
)

SESSION_KEY = "report_center_filters"


def _serialize_filters(params: dict) -> dict:
    out = {}
    for key, value in params.items():
        if value is None or value == "":
            continue
        if hasattr(value, "pk"):
            out[key] = str(value.pk)
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = str(value)
    return out


def restore_session_filters(session, report_key: str) -> dict | None:
    store = session.get(SESSION_KEY) or {}
    return store.get(report_key)


def save_session_filters(session, report_key: str, params: dict) -> None:
    store = session.get(SESSION_KEY) or {}
    store[report_key] = _serialize_filters(params)
    session[SESSION_KEY] = store
    session.modified = True


def prepare_report_querydict(request, report_key: str) -> QueryDict:
    """
    Build GET params for ReportFilterForm: preset expansion, session restore, EOY defaults.
    """
    if request.GET:
        data = request.GET.copy()
    else:
        restored = restore_session_filters(request.session, report_key)
        if restored:
            data = QueryDict(mutable=True)
            for key, value in restored.items():
                data[key] = value
        else:
            data = QueryDict(mutable=True)
            if report_key == "end_of_year_detailed":
                period, start, end = resolve_period_preset("last_calendar_year")
                data["period"] = period
                if start:
                    data["start_date"] = start.isoformat()
                if end:
                    data["end_date"] = end.isoformat()
                for key in EOY_SECTION_KEYS:
                    data[f"eoy_{key}"] = "1" if default_eoy_sections()[key] else "0"
            elif report_key in CURRENT_YEAR_DEFAULT_REPORTS:
                period, start, end = resolve_period_preset("current_calendar_year")
                data["period"] = period
                if start:
                    data["start_date"] = start.isoformat()
                if end:
                    data["end_date"] = end.isoformat()

    preset = data.get("preset")
    if preset:
        period, start, end = resolve_period_preset(preset)
        data["period"] = period
        if start:
            data["start_date"] = start.isoformat()
        if end:
            data["end_date"] = end.isoformat()
        data.pop("preset", None)

    return data


def eoy_section_choices_for_template(get_params, request, active_church) -> list[dict]:
    from sitecontrol.services import church_has_feature

    current = parse_eoy_sections(get_params)
    church = active_church
    rows = []
    for key, label in EOY_SECTION_SPECS:
        if key == "budget" and church and not church_has_feature(church, "budgets"):
            continue
        if key == "settlement" and church and not church_has_feature(church, "remittance"):
            continue
        if key == "payroll" and church and not church_has_feature(church, "payroll"):
            continue
        rows.append({"key": key, "label": label, "enabled": current.get(key, False)})
    return rows