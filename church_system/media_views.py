"""Authenticated (and public-branding) media delivery with optional X-Accel-Redirect.

Uses ``default_storage`` so filesystem and S3-backed keys both work after ACL
(CH-SEC-001). Private bytes are never returned without ``user_may_access_media``.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET

from church_system.media_access import is_public_media_path, normalize_media_relative_path
from church_system.media_authorization import user_may_access_media


def _content_type(relative_path: str) -> str:
    guessed, _ = mimetypes.guess_type(relative_path)
    return guessed or "application/octet-stream"


def _try_x_accel(relative_path: str) -> HttpResponse | None:
    """Filesystem + Nginx internal redirect only; skip for remote storage."""
    if not getattr(settings, "MEDIA_X_ACCEL_REDIRECT", False):
        return None
    try:
        abs_path = Path(default_storage.path(relative_path)).resolve()
    except (NotImplementedError, AttributeError, ValueError, OSError):
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError:
        return None
    if not abs_path.is_file():
        return None
    internal_prefix = getattr(
        settings, "MEDIA_INTERNAL_URL_PREFIX", "/internal-media/"
    ).rstrip("/")
    response = HttpResponse(content_type=_content_type(relative_path))
    response["X-Accel-Redirect"] = f"{internal_prefix}/{relative_path}"
    response["Content-Disposition"] = f'inline; filename="{abs_path.name}"'
    return response


def _deliver(relative_path: str) -> HttpResponse:
    if not default_storage.exists(relative_path):
        raise Http404("Media not found.")
    accel = _try_x_accel(relative_path)
    if accel is not None:
        return accel
    handle = default_storage.open(relative_path, "rb")
    filename = Path(relative_path).name
    return FileResponse(
        handle,
        content_type=_content_type(relative_path),
        filename=filename,
    )


@require_GET
def protected_media(request, path: str):
    """
    Serve MEDIA files.

    Public branding paths: anonymous OK.
    Private paths: object- and tenant-scoped (INV-MED-01). Unauthorized → 404.
    """
    relative = normalize_media_relative_path(path)
    if not relative:
        raise Http404("Invalid media path.")

    if is_public_media_path(relative):
        return _deliver(relative)

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    if not user_may_access_media(request.user, relative):
        # INV-MED-02 / INV-MED-04: 404, no bytes, no successful download audit.
        raise Http404("Media not found.")

    return _deliver(relative)
