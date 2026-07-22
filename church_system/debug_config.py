"""Resolve Django DEBUG safely for local vs production-like environments.

Default when ``DJANGO_DEBUG`` is unset:
- Local (no production markers) → True (developer convenience)
- Production-like (DATABASE_URL / Render / PythonAnywhere / Dyno) → False

Explicit ``DJANGO_DEBUG=True`` on a production-like host raises unless
``DJANGO_ALLOW_DEBUG_IN_PROD=True`` is set for temporary debugging.
"""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured


def env_flag(name: str) -> bool | None:
    """Return True/False for a boolean env var, or None if unset."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("true", "1", "yes")


def is_production_like_env(
    *,
    on_render: bool | None = None,
    on_pythonanywhere: bool | None = None,
    database_url: str | None = None,
    dyno: str | None = None,
) -> bool:
    """True when deploy markers indicate a non-local hosting environment."""
    if on_render is None:
        on_render = bool(os.environ.get("RENDER"))
    if on_pythonanywhere is None:
        on_pythonanywhere = bool(os.environ.get("PYTHONANYWHERE_SITE"))
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL", "")
    if dyno is None:
        dyno = os.environ.get("DYNO", "")
    return bool(
        on_render
        or on_pythonanywhere
        or (database_url or "").strip()
        or (dyno or "").strip()
    )


def resolve_debug(
    *,
    debug_env: bool | None = None,
    production_like: bool | None = None,
    allow_debug_in_prod: bool | None = None,
) -> bool:
    """
    Compute DEBUG.

    Raises ImproperlyConfigured if DEBUG would be True on a production-like
    host without an explicit allow override.
    """
    if debug_env is None:
        debug_env = env_flag("DJANGO_DEBUG")
    if production_like is None:
        production_like = is_production_like_env()
    if allow_debug_in_prod is None:
        allow_debug_in_prod = bool(env_flag("DJANGO_ALLOW_DEBUG_IN_PROD"))

    if debug_env is None:
        debug = not production_like
    else:
        debug = debug_env

    if debug and production_like and not allow_debug_in_prod:
        raise ImproperlyConfigured(
            "DJANGO_DEBUG cannot be True when DATABASE_URL or another production "
            "marker (RENDER, PYTHONANYWHERE_SITE, DYNO) is set. Set "
            "DJANGO_DEBUG=False, or set DJANGO_ALLOW_DEBUG_IN_PROD=True only for "
            "temporary debugging."
        )
    return debug
