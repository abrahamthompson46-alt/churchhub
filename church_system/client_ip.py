"""Trusted client IP resolution for rate limits, audit, and access control."""

from __future__ import annotations

from django.conf import settings


def trust_forwarded_client_ip() -> bool:
    """Trust X-Forwarded-For only when the app sits behind a known reverse proxy."""
    return bool(
        getattr(settings, "TRUST_X_FORWARDED_FOR", False)
        or getattr(settings, "USE_X_FORWARDED_HOST", False)
        or getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
    )


def get_client_ip(request) -> str | None:
    """
    Return the best-effort client IP for the request.

    X-Forwarded-For is honored only when proxy headers are trusted (production/staging).
    """
    if trust_forwarded_client_ip():
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    remote = request.META.get("REMOTE_ADDR")
    return remote or None
