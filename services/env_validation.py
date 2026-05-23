"""
Validation env au démarrage — fail-fast en production.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from config import settings


def _is_production() -> bool:
    return os.getenv("ENV", os.getenv("APP_ENV", "development")).lower() in (
        "production",
        "prod",
        "staging",
    )


def validate_redis_url(url: str) -> list[str]:
    errors: list[str] = []
    if not url:
        if _is_production():
            errors.append("REDIS_URL requis en production")
        return errors
    parsed = urlparse(url)
    if _is_production():
        if parsed.hostname in ("localhost", "127.0.0.1", ""):
            errors.append("REDIS_URL ne doit pas pointer vers localhost en production")
        if not parsed.password and parsed.scheme.startswith("redis"):
            errors.append("REDIS_URL doit inclure un mot de passe (redis://:pass@host:6379)")
    return errors


def validate_secrets() -> list[str]:
    errors: list[str] = []
    if not _is_production():
        return errors
    if not (settings.jwt_secret or "").strip():
        errors.append("JWT_SECRET requis en production")
    if settings.storage_backend == "postgres" and not (settings.secrets_encryption_key or "").strip():
        errors.append("SECRETS_ENCRYPTION_KEY requis en production avec Postgres")
    if (settings.oauth_linkedin_client_id or settings.oauth_linkedin_client_secret) and not (
        settings.secrets_encryption_key or ""
    ).strip():
        errors.append("SECRETS_ENCRYPTION_KEY requis si OAuth LinkedIn activé")
    return errors


def validate_postgres() -> list[str]:
    errors: list[str] = []
    if settings.storage_backend != "postgres":
        return errors
    url = (getattr(settings, "database_url", None) or os.getenv("DATABASE_URL", "") or "").strip()
    if not url and _is_production():
        errors.append("DATABASE_URL requis avec STORAGE_BACKEND=postgres")
    return errors


def validate_all(*, strict: bool | None = None) -> list[str]:
    strict = _is_production() if strict is None else strict
    errors: list[str] = []
    errors.extend(validate_redis_url(settings.redis_url or ""))
    errors.extend(validate_secrets())
    errors.extend(validate_postgres())
    if strict and errors:
        for e in errors:
            print(f"[env] {e}", file=sys.stderr)
        sys.exit(1)
    return errors


def validate_or_warn() -> list[str]:
    return validate_all(strict=False)
