"""Tenant branding resolution and CSS variable helpers."""

from __future__ import annotations

import re

from sitecontrol.services import clear_settings_cache, get_site_settings

HEX_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

DEFAULT_PRIMARY = "#1e3a5f"
DEFAULT_ACCENT = "#1d4ed8"
DEFAULT_HIGHLIGHT = "#0e7490"
DEFAULT_SURFACE = "#f4f7fb"


def normalize_hex_color(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    raw = str(value).strip()
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if len(raw) == 4 and HEX_RE.match(raw):
        r, g, b = raw[1], raw[2], raw[3]
        raw = f"#{r}{r}{g}{g}{b}{b}"
    if HEX_RE.match(raw):
        return raw.lower()
    return fallback


def resolve_institution_branding(*, denomination=None, settings_obj=None) -> dict[str, str]:
    """Merge platform defaults with denomination tenant overrides."""
    settings_obj = settings_obj or get_site_settings()
    branding = {
        "primary_color": normalize_hex_color(settings_obj.admin_primary_color, DEFAULT_PRIMARY),
        "accent_color": normalize_hex_color(settings_obj.accent_color, DEFAULT_ACCENT),
        "highlight_color": normalize_hex_color(
            getattr(settings_obj, "highlight_color", None), DEFAULT_HIGHLIGHT
        ),
        "surface_color": DEFAULT_SURFACE,
    }
    if denomination:
        branding["primary_color"] = normalize_hex_color(
            denomination.primary_color, branding["primary_color"]
        )
        branding["accent_color"] = normalize_hex_color(
            denomination.accent_color, branding["accent_color"]
        )
        branding["highlight_color"] = normalize_hex_color(
            getattr(denomination, "highlight_color", None), branding["highlight_color"]
        )
    return branding


def branding_css_block(branding: dict[str, str]) -> str:
    primary = branding["primary_color"]
    accent = branding["accent_color"]
    highlight = branding["highlight_color"]
    return f"""
            --ch-brand: {primary};
            --ch-brand-mid: color-mix(in srgb, {primary} 82%, white);
            --ch-navy: var(--ch-brand);
            --ch-navy-mid: var(--ch-brand-mid);
            --ch-action: {accent};
            --ch-action-hover: color-mix(in srgb, {accent} 82%, black);
            --ch-primary: var(--ch-action);
            --ch-primary-hover: var(--ch-action-hover);
            --ch-accent: {highlight};
            --ch-focus-ring: color-mix(in srgb, var(--ch-action) 22%, transparent);
            --ch-table-head-bg: color-mix(in srgb, {primary} 82%, #020617);
            --ch-table-head-text: #f1f5f9;
            --ch-surface: {branding.get("surface_color", DEFAULT_SURFACE)};
    """.strip()


def apply_branding_to_form_instance(form, instance):
    """Normalize hex colors before save."""
    for field in ("admin_primary_color", "accent_color", "highlight_color", "primary_color"):
        if field in form.cleaned_data:
            fallback = DEFAULT_PRIMARY if "primary" in field else (
                DEFAULT_ACCENT if field == "accent_color" else DEFAULT_HIGHLIGHT
            )
            normalized = normalize_hex_color(form.cleaned_data.get(field), fallback)
            setattr(instance, field, normalized)


def clear_branding_caches() -> None:
    clear_settings_cache()
