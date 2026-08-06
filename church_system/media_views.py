"""Authenticated (and public-branding) media delivery with optional X-Accel-Redirect."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET

from church_system.media_access import is_public_media_path, normalize_media_relative_path


def _media_file(relative_path: str) -> Path:
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Http404("Invalid media path.") from exc
    if not candidate.is_file():
        raise Http404("Media not found.")
    return candidate


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _deliver(relative_path: str) -> HttpResponse:
    path = _media_file(relative_path)
    if getattr(settings, "MEDIA_X_ACCEL_REDIRECT", False):
        internal_prefix = getattr(
            settings, "MEDIA_INTERNAL_URL_PREFIX", "/internal-media/"
        ).rstrip("/")
        response = HttpResponse(content_type=_content_type(path))
        response["X-Accel-Redirect"] = f"{internal_prefix}/{relative_path}"
        response["Content-Disposition"] = f'inline; filename="{path.name}"'
        return response
    return FileResponse(path.open("rb"), content_type=_content_type(path))


@require_GET
def protected_media(request, path: str):
    """
    Serve MEDIA files.

    Public branding paths: anonymous OK.
    All other paths: authenticated session required (login redirect).
    """
    relative = normalize_media_relative_path(path)
    if not relative:
        raise Http404("Invalid media path.")

    if is_public_media_path(relative):
        return _deliver(relative)

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    return _deliver(relative)
