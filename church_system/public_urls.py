"""Resolve the public site base URL for links in email (portal confirm, invites, etc.)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.conf import settings

# Common mistakes when setting CHURCHHUB_PUBLIC_URL (must be site root, not a deep link).
_MISTAKEN_PUBLIC_URL_SUFFIXES = (
    "/dashboard",
    "/dashboard/logout",
    "/portal",
    "/platform",
    "/admin",
    "/accounts/login",
)

# PythonAnywhere console / marketing hosts — never valid as the webapp public URL.
_PYTHONANYWHERE_INVALID_HOSTS = frozenset(
    {
        "www.pythonanywhere.com",
        "pythonanywhere.com",
        "eu.pythonanywhere.com",
        "www.eu.pythonanywhere.com",
    }
)


def normalize_public_site_base(url: str) -> str:
    """Strip accidental path segments from a configured public site URL."""
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return cleaned
    lower = cleaned.lower()
    changed = True
    while changed:
        changed = False
        for suffix in _MISTAKEN_PUBLIC_URL_SUFFIXES:
            if lower.endswith(suffix.lower()):
                cleaned = cleaned[: -len(suffix)].rstrip("/")
                lower = cleaned.lower()
                changed = True
                break
    return cleaned


def _hostname(url: str) -> str:
    return (urlparse((url or "").strip()).hostname or "").lower()


def is_invalid_pythonanywhere_host(host: str) -> bool:
    host = (host or "").lower().strip()
    return host in _PYTHONANYWHERE_INVALID_HOSTS


def _webapp_host_from_allowed_hosts() -> str:
    """Pick username.pythonanywhere.com from ALLOWED_HOSTS when env is incomplete."""
    for host in getattr(settings, "ALLOWED_HOSTS", []) or []:
        host = (host or "").strip().lower()
        if not host or host == "*" or host.startswith("."):
            continue
        if is_invalid_pythonanywhere_host(host):
            continue
        if host.endswith(".pythonanywhere.com"):
            return host
    return ""


def resolve_pythonanywhere_public_url(configured: str) -> str:
    """
    On PythonAnywhere, email links must use the web app hostname
    (e.g. churchhub.pythonanywhere.com), never www.pythonanywhere.com.
    """
    pa_site = (os.environ.get("PYTHONANYWHERE_SITE") or "").strip().lower()
    if is_invalid_pythonanywhere_host(pa_site):
        pa_site = ""
    if not pa_site:
        pa_site = _webapp_host_from_allowed_hosts()

    cleaned = normalize_public_site_base(configured or "")
    host = _hostname(cleaned)

    if pa_site:
        canonical = f"https://{pa_site}"
        if host == pa_site:
            return cleaned.rstrip("/")
        return canonical

    if cleaned and not is_invalid_pythonanywhere_host(host):
        return cleaned.rstrip("/")

    fallback_host = _webapp_host_from_allowed_hosts()
    if fallback_host:
        return f"https://{fallback_host}"
    return cleaned.rstrip("/") if cleaned and not is_invalid_pythonanywhere_host(host) else ""


def is_localhost_url(url: str) -> bool:
    if not url:
        return True
    lower = url.lower()
    return (
        "localhost" in lower
        or "127.0.0.1" in lower
        or "[::1]" in lower
        or lower.startswith("http://0.0.0.0")
    )


def resolve_public_site_base(request=None) -> str:
    """
    Base URL (no trailing slash) for absolute links sent to users.

    Prefers CHURCHHUB_PUBLIC_URL when it is not a localhost URL in non-debug
    environments, then the incoming request, then CSRF trusted origins / allowed hosts.
    """
    on_pa = bool(
        getattr(settings, "ON_PYTHONANYWHERE", False)
        or os.environ.get("PYTHONANYWHERE_SITE")
        or _webapp_host_from_allowed_hosts()
    )
    if on_pa:
        resolved = resolve_pythonanywhere_public_url(
            getattr(settings, "CHURCHHUB_PUBLIC_URL", "") or ""
        )
        if resolved:
            return resolved

    configured = normalize_public_site_base(
        getattr(settings, "CHURCHHUB_PUBLIC_URL", "") or ""
    )
    if configured and is_invalid_pythonanywhere_host(_hostname(configured)):
        configured = ""
    debug = getattr(settings, "DEBUG", True)

    if configured and (debug or not is_localhost_url(configured)):
        return configured

    if request is not None:
        try:
            built = request.build_absolute_uri("/").rstrip("/")
            built_host = _hostname(built)
            if is_invalid_pythonanywhere_host(built_host):
                built = ""
            if built and (debug or not is_localhost_url(built)):
                return built
        except Exception:
            pass

    if not debug:
        for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []:
            origin = (origin or "").strip().rstrip("/")
            if (
                origin
                and not is_localhost_url(origin)
                and not is_invalid_pythonanywhere_host(_hostname(origin))
            ):
                return origin
        for host in getattr(settings, "ALLOWED_HOSTS", []) or []:
            host = (host or "").strip()
            if not host or host == "*" or host.startswith("."):
                continue
            if host in ("localhost", "127.0.0.1"):
                continue
            if is_invalid_pythonanywhere_host(host):
                continue
            scheme = "https"
            if getattr(settings, "SECURE_SSL_REDIRECT", False) is False:
                scheme = "http"
            return f"{scheme}://{host}"

    if configured:
        return configured
    if request is not None:
        return request.build_absolute_uri("/").rstrip("/")
    return "http://localhost:8000"


def build_public_absolute_uri(request, path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{resolve_public_site_base(request)}{path}"
