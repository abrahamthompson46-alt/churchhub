"""Report screen/document presentation helpers."""

from __future__ import annotations

from django.utils import timezone

from church_system.church_scope import get_active_church, get_user_church

from . import selectors

_KPI_TONE_ALIASES = {
    "ok": "success",
    "primary": "primary",
    "success": "success",
    "danger": "danger",
    "warning": "warning",
    "accent": "accent",
}


def normalize_kpi_tone(tone: str | None) -> str:
    return _KPI_TONE_ALIASES.get((tone or "primary").lower(), "primary")


def normalize_statement_kpis(kpis: list[dict] | None) -> list[dict]:
    if not kpis:
        return []
    out = []
    for kpi in kpis:
        item = dict(kpi)
        item["tone"] = normalize_kpi_tone(item.get("tone"))
        out.append(item)
    return out


def _scope_detail_parts(**hierarchy) -> list[str]:
    from organization.models import Church, Conference, District, Zone

    parts = []
    if cid := hierarchy.get("church_id"):
        church = (
            Church.objects.filter(pk=cid)
            .select_related("district__zone__conference")
            .first()
        )
        if church:
            parts.append(church.name)
    elif did := hierarchy.get("district_id"):
        district = District.objects.filter(pk=did).first()
        if district:
            parts.append(f"District: {district.name}")
    elif zid := hierarchy.get("zone_id"):
        zone = Zone.objects.filter(pk=zid).first()
        if zone:
            parts.append(f"Zone: {zone.name}")
    elif conf_id := hierarchy.get("conference_id"):
        conf = Conference.objects.filter(pk=conf_id).first()
        if conf:
            parts.append(f"Conference: {conf.name}")
    return parts


def build_report_document_context(request, **hierarchy) -> dict:
    """Letterhead metadata shared by statement and ledger templates."""
    parts = _scope_detail_parts(**hierarchy)
    active = get_active_church(request)
    if not parts and active:
        parts.append(active.name)
    elif not parts:
        home = get_user_church(request.user)
        if home:
            parts.append(home.name)
        else:
            parts.append("All churches in your access scope")

    churches = selectors.churches_in_scope(request, **hierarchy)
    church_count = churches.count()
    logo_url = _report_logo_url(request, churches)

    scope_label = parts[0] if len(parts) == 1 else " · ".join(parts)
    scope_secondary = ""
    if church_count > 1:
        scope_secondary = f"{church_count} churches in report scope"
    elif active and active.name not in scope_label:
        scope_secondary = active.name

    user = request.user
    prepared = (user.get_full_name() or "").strip() or user.get_username()

    return {
        "scope_label": scope_label,
        "scope_secondary": scope_secondary,
        "scope_parts": parts,
        "prepared_by": prepared,
        "generated_at": timezone.now(),
        "multi_church": church_count > 1,
        "church_count": church_count,
        "logo_url": logo_url,
    }


def _report_logo_url(request, churches_qs) -> str:
    """Prefer denomination branding for scoped church, else platform logo."""
    from sitecontrol.services import get_site_settings

    active = get_active_church(request)
    church = active or churches_qs.first()
    if church:
        denomination = getattr(church, "denomination", None)
        if denomination and getattr(denomination, "logo", None):
            try:
                return denomination.logo.url
            except (ValueError, AttributeError):
                pass
    settings_obj = get_site_settings()
    if settings_obj and settings_obj.logo:
        try:
            return settings_obj.logo.url
        except (ValueError, AttributeError):
            pass
    return ""