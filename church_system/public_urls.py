"""Resolve the public site base URL for links in email (portal confirm, invites, etc.)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.conf import settings

# Common mistakes when setting CHURCHHUB_PUBLIC_URL (must be site root, not a deep link).
_MISTAKEN_PUBLIC_URL_SUFFIXES = (
    "/dashboard",
    "/portal",
    "/platform",
    "/admin",
    "/accounts/login",
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


def resolve_pythonanywhere_public_url(configured: str) -> str:
    """
    On PythonAnywhere, email links must use the web app hostname (PYTHONANYWHERE_SITE),
    not www.pythonanywhere.com or another host from a mis-set CHURCHHUB_PUBLIC_URL.
    """
    pa_site = (os.environ.get("PYTHONANYWHERE_SITE") or "").strip().lower()
    if not pa_site:
        return (configured or "").strip().rstrip("/")

    canonical = f"https://{pa_site}"
    cleaned = normalize_public_site_base(configured or "")
    if not cleaned:
        return canonical
    host = (urlparse(cleaned).hostname or "").lower()
    if host == pa_site:
        return cleaned.rstrip("/")
    return canonical


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
    if getattr(settings, "ON_PYTHONANYWHERE", False) and os.environ.get("PYTHONANYWHERE_SITE"):
        return resolve_pythonanywhere_public_url(
            getattr(settings, "CHURCHHUB_PUBLIC_URL", "") or ""
        )

    configured = normalize_public_site_base(
        getattr(settings, "CHURCHHUB_PUBLIC_URL", "") or ""
    )
    debug = getattr(settings, "DEBUG", True)

    if configured and (debug or not is_localhost_url(configured)):
        return configured

    if request is not None:
        try:
            built = request.build_absolute_uri("/").rstrip("/")
            if debug or not is_localhost_url(built):
                return built
        except Exception:
            pass

    if not debug:
        for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []:
            origin = (origin or "").strip().rstrip("/")
            if origin and not is_localhost_url(origin):
                return origin
        for host in getattr(settings, "ALLOWED_HOSTS", []) or []:
            host = (host or "").strip()
            if not host or host == "*" or host.startswith("."):
                continue
            if host in ("localhost", "127.0.0.1"):
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
