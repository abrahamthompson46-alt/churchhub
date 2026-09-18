"""Fernet helpers with optional dedicated encryption key.

MFA (and other Fernet payloads) prefer ``MFA_ENCRYPTION_KEY`` when set so
rotating ``DJANGO_SECRET_KEY`` does not orphan ciphertext. Decrypt tries the
dedicated key first, then ``SECRET_KEY``, so existing secrets keep working.
"""

from __future__ import annotations

import base64
import hashlib

from django.conf import settings


def _key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def fernet_key_material() -> list[bytes]:
    """Ordered Fernet keys: dedicated MFA key (if any), then Django SECRET_KEY."""
    keys: list[bytes] = []
    seen: set[bytes] = set()
    dedicated = (getattr(settings, "MFA_ENCRYPTION_KEY", "") or "").strip()
    for secret in (dedicated, settings.SECRET_KEY):
        if not secret:
            continue
        material = _key_from_secret(secret)
        if material in seen:
            continue
        seen.add(material)
        keys.append(material)
    if not keys:
        raise ValueError("No Fernet key material is configured.")
    return keys


def encrypt_fernet(plaintext: str) -> str:
    from cryptography.fernet import Fernet

    if not plaintext:
        return ""
    return Fernet(fernet_key_material()[0]).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_fernet(token: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken

    if not token:
        return ""
    last_error: Exception | None = None
    for material in fernet_key_material():
        try:
            return Fernet(material).decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    return ""
