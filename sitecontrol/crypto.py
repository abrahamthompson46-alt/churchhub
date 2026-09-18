"""Platform secret helpers — Fernet encryption for SMTP credentials."""

from __future__ import annotations

from church_system.crypto import decrypt_fernet, encrypt_fernet


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return encrypt_fernet(plaintext)


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    from cryptography.fernet import InvalidToken

    try:
        return decrypt_fernet(token)
    except (InvalidToken, ValueError):
        return ""


def resolve_smtp_password(site) -> str:
    """Prefer encrypted store; fall back to legacy plaintext field."""
    encrypted = getattr(site, "smtp_password_encrypted", "") or ""
    if encrypted:
        return decrypt_secret(encrypted)
    return getattr(site, "smtp_password", "") or ""
