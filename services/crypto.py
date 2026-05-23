"""Chiffrement secrets (OAuth, sessions) — Fernet (E0)."""

from __future__ import annotations

import base64
import hashlib

from config import settings


def _fernet_key() -> bytes:
    raw = (
        getattr(settings, "secrets_encryption_key", None)
        or settings.jwt_secret
        or settings.api_key
        or "dev-insecure-change-secrets-encryption-key"
    )
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_bytes(data: bytes) -> bytes:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).decrypt(token)


def encrypt_text(text: str) -> str:
    return encrypt_bytes(text.encode("utf-8")).decode("latin-1")


def decrypt_text(blob: str) -> str:
    return decrypt_bytes(blob.encode("latin-1")).decode("utf-8")
