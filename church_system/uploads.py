"""Shared upload validation — size, extension, and content-type allowlists.

Use for every user-facing FileField / ImageField clean path.
System-generated files (e.g. report export jobs) should not use these.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ValidationError

# ── Limits (bytes); overridable via environment ──────────────────────────────

def _env_bytes(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


MAX_IMAGE_BYTES = _env_bytes("CHURCHHUB_MAX_IMAGE_BYTES", 5 * 1024 * 1024)
MAX_DOCUMENT_BYTES = _env_bytes("CHURCHHUB_MAX_DOCUMENT_BYTES", 10 * 1024 * 1024)
MAX_BRANDING_BYTES = _env_bytes("CHURCHHUB_MAX_BRANDING_BYTES", 2 * 1024 * 1024)

# Hard ceiling for request body handling (forms + settings alignment)
MAX_REQUEST_UPLOAD_BYTES = _env_bytes(
    "CHURCHHUB_MAX_REQUEST_UPLOAD_BYTES",
    max(MAX_DOCUMENT_BYTES, MAX_IMAGE_BYTES, 12 * 1024 * 1024),
)

IMAGE_CONTENT_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})

DOCUMENT_CONTENT_TYPES = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
    "application/csv",
}) | IMAGE_CONTENT_TYPES

DOCUMENT_EXTENSIONS = frozenset({
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
    ".csv",
}) | IMAGE_EXTENSIONS

# Explicit denylist for common dangerous payloads (defense in depth)
BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".js", ".jsx", ".mjs",
    ".php", ".phtml", ".asp", ".aspx", ".jsp", ".cgi", ".sh", ".ps1",
    ".html", ".htm", ".svg", ".svgz", ".xml", ".xhtml",
    ".dll", ".so", ".dylib", ".jar", ".war", ".py", ".rb", ".pl",
})

_KIND_LIMITS = {
    "image": (MAX_IMAGE_BYTES, IMAGE_CONTENT_TYPES, IMAGE_EXTENSIONS, "images"),
    "branding": (MAX_BRANDING_BYTES, IMAGE_CONTENT_TYPES, IMAGE_EXTENSIONS, "branding images"),
    "document": (MAX_DOCUMENT_BYTES, DOCUMENT_CONTENT_TYPES, DOCUMENT_EXTENSIONS, "documents"),
}


def _human_mb(nbytes: int) -> str:
    mb = nbytes / (1024 * 1024)
    if mb >= 1 and abs(mb - round(mb)) < 0.05:
        return f"{int(round(mb))} MB"
    return f"{mb:.1f} MB"


def _filename(uploaded) -> str:
    return Path(getattr(uploaded, "name", "") or "").name


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _content_type(uploaded) -> str:
    raw = getattr(uploaded, "content_type", None) or ""
    return raw.split(";")[0].strip().lower()


def validate_upload(uploaded, *, kind: str = "image") -> None:
    """
    Validate an UploadedFile / FieldFile.

    kind: "image" | "document" | "branding"
    Raises django.core.exceptions.ValidationError on failure.
    """
    if not uploaded:
        return
    if kind not in _KIND_LIMITS:
        raise ValidationError(f"Unknown upload kind: {kind}.")

    max_bytes, allowed_types, allowed_exts, label = _KIND_LIMITS[kind]
    filename = _filename(uploaded)
    if not filename:
        raise ValidationError("Upload must include a file name.")
    if "\x00" in filename:
        raise ValidationError("Invalid file name.")

    ext = _extension(filename)
    if not ext:
        raise ValidationError(f"File must have an extension ({label}).")
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"File type “{ext}” is not allowed.")
    if ext not in allowed_exts:
        allowed = ", ".join(sorted(allowed_exts))
        raise ValidationError(f"Only these file types are allowed for {label}: {allowed}.")

    size = getattr(uploaded, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError(f"File must be {_human_mb(max_bytes)} or smaller.")

    content_type = _content_type(uploaded)
    # Some browsers omit or send application/octet-stream; extension remains authoritative.
    if content_type and content_type not in ("application/octet-stream", "binary/octet-stream"):
        if content_type not in allowed_types:
            raise ValidationError(
                f"File content type “{content_type}” is not allowed for {label}."
            )


def image_upload_validator(uploaded):
    validate_upload(uploaded, kind="image")


def document_upload_validator(uploaded):
    validate_upload(uploaded, kind="document")


def branding_upload_validator(uploaded):
    validate_upload(uploaded, kind="branding")
