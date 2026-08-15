"""Storage backends — filesystem by default, optional S3-compatible media.

CH-SEC-001 / INV-MED-03: private FieldFile.url must never be a public S3 URL.
All media URLs point at the Django ``/media/`` authorization gate.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

from church_system.media_access import normalize_media_relative_path


def media_gate_url(name: str) -> str:
    """Return an application-relative ``/media/<key>`` URL (never a raw object store URL)."""
    rel = normalize_media_relative_path(name)
    if not rel:
        rel = str(name or "").replace("\\", "/").lstrip("/")
    base = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
    if not base.endswith("/"):
        base = f"{base}/"
    return f"{base}{rel}"


@deconstructible
class ChurchHubFileSystemStorage(FileSystemStorage):
    """Filesystem media; ``.url`` always goes through ``protected_media``."""

    def url(self, name):
        return media_gate_url(name)


try:
    from storages.backends.s3boto3 import S3Boto3Storage

    @deconstructible
    class ChurchHubS3Boto3Storage(S3Boto3Storage):
        """
        S3 media where FieldFile.url never bypasses Django authorization.

        ``url()`` always returns ``/media/<key>``. Bytes are delivered only after
        ACL (or public branding) via ``protected_media`` + ``default_storage.open``.
        """

        def url(self, name, parameters=None, expire=None, http_method=None):
            return media_gate_url(name)

        def signed_url(self, name, expire=None):
            """Short-lived direct GET — reserved for post-ACL redirects if enabled."""
            return super().url(name, expire=expire)

except ImportError:  # pragma: no cover - optional dependency

    @deconstructible
    class ChurchHubS3Boto3Storage(ChurchHubFileSystemStorage):  # type: ignore[no-redef]
        """Placeholder when django-storages is not installed."""

        pass


def build_storages(*, compressed_static: bool = True) -> dict:
    """
    Return Django STORAGES config.

    Media:
    - ChurchHubFileSystemStorage (default)
    - ChurchHubS3Boto3Storage when AWS_STORAGE_BUCKET_NAME (or S3_BUCKET) is set and
      django-storages[s3] / boto3 are installed

    Static:
    - WhiteNoise CompressedStaticFilesStorage (or Manifest when CHURCHHUB_MANIFEST_STATIC=1)
    """
    static_backend = "whitenoise.storage.CompressedStaticFilesStorage"
    if os.environ.get("CHURCHHUB_MANIFEST_STATIC", "").lower() in ("true", "1", "yes"):
        static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    elif not compressed_static:
        static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"

    media_backend = "church_system.storage.ChurchHubFileSystemStorage"
    bucket = (
        os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
        or os.environ.get("S3_BUCKET", "").strip()
    )
    if bucket:
        try:
            import storages  # noqa: F401

            media_backend = "church_system.storage.ChurchHubS3Boto3Storage"
        except ImportError:
            media_backend = "church_system.storage.ChurchHubFileSystemStorage"

    return {
        "default": {"BACKEND": media_backend},
        "staticfiles": {"BACKEND": static_backend},
    }


def apply_s3_settings(globals_dict: dict) -> None:
    """Populate AWS_* settings when using S3 media storage."""
    bucket = (
        os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
        or os.environ.get("S3_BUCKET", "").strip()
    )
    if not bucket:
        return
    globals_dict["AWS_STORAGE_BUCKET_NAME"] = bucket
    globals_dict["AWS_S3_REGION_NAME"] = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    # Never default private objects to public-read.
    globals_dict["AWS_DEFAULT_ACL"] = None
    globals_dict["AWS_QUERYSTRING_AUTH"] = (
        os.environ.get("AWS_QUERYSTRING_AUTH", "true").lower() in ("true", "1", "yes")
    )
    custom_domain = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "").strip()
    if custom_domain:
        globals_dict["AWS_S3_CUSTOM_DOMAIN"] = custom_domain
    endpoint = os.environ.get("AWS_S3_ENDPOINT_URL", "").strip()
    if endpoint:
        globals_dict["AWS_S3_ENDPOINT_URL"] = endpoint
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if access_key:
        globals_dict["AWS_ACCESS_KEY_ID"] = access_key
    if secret_key:
        globals_dict["AWS_SECRET_ACCESS_KEY"] = secret_key
