"""Optional token gate for operational health endpoints."""

from __future__ import annotations

import hmac

from django.conf import settings


def health_check_authorized(request) -> bool:
    """
    When CHURCHHUB_HEALTH_TOKEN is configured, require it on health probes.

    Accept via query ?token=… or X-Health-Token header. When unset (typical dev/test),
    endpoints remain open for local tooling.
    """
    expected = (getattr(settings, "HEALTH_CHECK_TOKEN", "") or "").strip()
    if not expected:
        return True
    supplied = (request.headers.get("X-Health-Token") or request.GET.get("token") or "").strip()
    return hmac.compare_digest(
        hmac.new(b"churchhub-health", supplied.encode("utf-8"), "sha256").digest(),
        hmac.new(b"churchhub-health", expected.encode("utf-8"), "sha256").digest(),
    )
