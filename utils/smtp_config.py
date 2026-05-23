"""Vérification de la configuration SMTP (.env)."""

from __future__ import annotations

from config import settings


def smtp_configured() -> bool:
    user = (settings.smtp_user or "").strip()
    password = (settings.smtp_password or "").strip()
    return bool(user and password)


def smtp_from_address() -> str:
    return (settings.smtp_from or settings.smtp_user or "").strip()
