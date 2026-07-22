"""Storage backends — filesystem by default, optional S3-compatible media."""

from __future__ import annotations

import os


def build_storages(*, compressed_static: bool = True) -> dict:
    """
    Return Django STORAGES config.

    Media:
    - FileSystemStorage (default)
    - S3Boto3Storage when AWS_STORAGE_BUCKET_NAME (or S3_BUCKET) is set and
      django-storages[s3] / boto3 are installed

    Static:
    - WhiteNoise CompressedStaticFilesStorage (or Manifest when CHURCHHUB_MANIFEST_STATIC=1)
    """
    static_backend = "whitenoise.storage.CompressedStaticFilesStorage"
    if os.environ.get("CHURCHHUB_MANIFEST_STATIC", "").lower() in ("true", "1", "yes"):
        static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    elif not compressed_static:
        static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"

    media_backend = "django.core.files.storage.FileSystemStorage"
    bucket = (
        os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
        or os.environ.get("S3_BUCKET", "").strip()
    )
    if bucket:
        try:
            import storages  # noqa: F401

            media_backend = "storages.backends.s3boto3.S3Boto3Storage"
        except ImportError:
            # Fall back to filesystem; ops should install django-storages[boto3]
            media_backend = "django.core.files.storage.FileSystemStorage"

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
