"""Classify and sanitize MEDIA_ROOT-relative paths for protected media serving."""

from __future__ import annotations

# Served anonymously by Nginx (and by Django in DEBUG without Nginx).
PUBLIC_MEDIA_PREFIXES: tuple[str, ...] = (
    "platform/branding/",
    "denominations/branding/",
)

# URL prefixes that remain middleware-exempt (login logos before auth).
PUBLIC_MEDIA_URL_PREFIXES: tuple[str, ...] = tuple(
    f"/media/{prefix}" for prefix in PUBLIC_MEDIA_PREFIXES
)


def normalize_media_relative_path(raw_path: str) -> str | None:
    """
    Return a safe MEDIA_ROOT-relative path, or None if the path is unsafe.

    Rejects absolute paths, empty segments, and ``..`` traversal.
    """
    if raw_path is None:
        return None
    path = str(raw_path).replace("\\", "/").lstrip("/")
    if not path or path.startswith("/") or "\x00" in path:
        return None
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or part.startswith(".."):
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def is_public_media_path(relative_path: str) -> bool:
    """True when the path may be served without authentication."""
    normalized = normalize_media_relative_path(relative_path)
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in PUBLIC_MEDIA_PREFIXES)


def is_public_media_url(path: str) -> bool:
    """True when a request path is under a public branding URL prefix."""
    if not path:
        return False
    return any(path.startswith(prefix) for prefix in PUBLIC_MEDIA_URL_PREFIXES)
