"""PII field encryption for payroll sensitive data (Fernet)."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

_PREFIX_FERNET = "f1:"
_PREFIX_SIGNED_LEGACY = "s0:"  # optional marker; legacy may be unmarked signing dumps


class PayrollCryptoError(ValueError):
    """Raised when encrypted payroll PII cannot be decrypted."""


def _fernet():
    raw = getattr(settings, "PAYROLL_FERNET_KEY", None) or ""
    if raw:
        key = raw.encode("ascii") if isinstance(raw, str) else raw
        return Fernet(key)
    # Derive a stable Fernet key from SECRET_KEY (rotate by setting PAYROLL_FERNET_KEY).
    digest = hashlib.sha256(f"payroll.pii.v2|{settings.SECRET_KEY}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class PayrollFieldCrypto:
    """Encrypt/decrypt sensitive payroll fields with Fernet; migrate legacy signed values."""

    salt = "payroll.pii.v1"

    @classmethod
    def encrypt(cls, value):
        if not value:
            return ""
        token = _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")
        return f"{_PREFIX_FERNET}{token}"

    @classmethod
    def decrypt(cls, value, *, strict=False):
        if not value:
            return ""
        text = str(value)
        try:
            if text.startswith(_PREFIX_FERNET):
                return _fernet().decrypt(text[len(_PREFIX_FERNET):].encode("ascii")).decode("utf-8")
            # Legacy Django signing payloads (pre-enterprise).
            try:
                return signing.loads(text, salt=cls.salt, max_age=None)
            except signing.BadSignature:
                if text.startswith(_PREFIX_SIGNED_LEGACY):
                    return signing.loads(text[len(_PREFIX_SIGNED_LEGACY):], salt=cls.salt, max_age=None)
                raise
        except (InvalidToken, signing.BadSignature, ValueError) as exc:
            logger.warning("Payroll PII decrypt failed: %s", type(exc).__name__)
            if strict:
                raise PayrollCryptoError(
                    "Unable to decrypt payroll PII. Check PAYROLL_FERNET_KEY / SECRET_KEY."
                ) from exc
            return ""

    @classmethod
    def needs_reencrypt(cls, value):
        if not value:
            return False
        return not str(value).startswith(_PREFIX_FERNET)


def mask_account_number(value, visible=4):
    """Return masked bank account for display."""
    if not value or len(value) <= visible:
        return "****"
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"
