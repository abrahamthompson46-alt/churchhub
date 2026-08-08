"""Trusted client IP resolution for rate limits, audit, and access control."""

from __future__ import annotations

import ipaddress

from django.conf import settings


def trust_forwarded_client_ip() -> bool:
    """Trust X-Forwarded-For only when explicitly enabled."""
    return bool(getattr(settings, "TRUST_X_FORWARDED_FOR", False))


def _valid_ip(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _remote_is_trusted_proxy(remote: str | None) -> bool:
    if not remote:
        return False
    try:
        address = ipaddress.ip_address(remote)
    except ValueError:
        return False
    for value in getattr(settings, "TRUSTED_PROXY_IPS", ()) or ():
        try:
            if address in ipaddress.ip_network(value, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request) -> str | None:
    """
    Return the best-effort client IP for the request.

    X-Forwarded-For is honored only when proxy headers are trusted (production/staging).
    """
    remote = _valid_ip(request.META.get("REMOTE_ADDR"))
    if trust_forwarded_client_ip() and _remote_is_trusted_proxy(remote):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            forwarded_ip = _valid_ip(forwarded.split(",")[0])
            if forwarded_ip:
                return forwarded_ip
    return remote
