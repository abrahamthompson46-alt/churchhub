"""Platform secret helpers — Fernet encryption for SMTP credentials."""

from __future__ import annotations

import base64
import hashlib

from django.conf import settings


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def resolve_smtp_password(site) -> str:
    """Prefer encrypted store; fall back to legacy plaintext field."""
    encrypted = getattr(site, "smtp_password_encrypted", "") or ""
    if encrypted:
        return decrypt_secret(encrypted)
    return getattr(site, "smtp_password", "") or ""
