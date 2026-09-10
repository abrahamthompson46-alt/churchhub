"""Request metadata for enterprise audit events (thread-local, request-scoped)."""

from __future__ import annotations

import threading

_local = threading.local()


def bind_audit_request(request):
    _local.request = request


def clear_audit_request():
    _local.request = None


def current_audit_request():
    return getattr(_local, "request", None)
