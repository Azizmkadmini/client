"""Clés d'idempotence API (E0)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from storage.database import Database


def get_cached(key: str) -> dict[str, Any] | None:
    if not key:
        return None
    return _get(key)


def store(key: str, tenant_id: str, response: dict[str, Any], *, ttl_hours: int = 24) -> None:
    if key:
        _set(key, tenant_id, response, ttl_hours=ttl_hours)


def check_or_store(key: str, tenant_id: str, response: dict[str, Any], *, ttl_hours: int = 24) -> dict[str, Any] | None:
    """Si existe retourne la réponse, sinon enregistre et retourne None."""
    if not key:
        return None
    existing = _get(key)
    if existing is not None:
        return existing
    _set(key, tenant_id, response, ttl_hours=ttl_hours)
    return None


def _get(key: str) -> dict[str, Any] | None:
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    "SELECT response FROM idempotency_keys WHERE key = %s AND expires_at > NOW()",
                    (key,),
                )
                row = cur.fetchone()
                if row:
                    return dict(row["response"])
            return None
    except Exception:
        pass
    with Database().connect() as conn:
        row = conn.execute(
            "SELECT response FROM idempotency_keys WHERE key = ? AND expires_at > ?",
            (key, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    if row:
        return json.loads(row["response"])
    return None


def _set(key: str, tenant_id: str, response: dict[str, Any], *, ttl_hours: int) -> None:
    expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO idempotency_keys (key, tenant_id, response, expires_at)
                    VALUES (%s, %s::uuid, %s::jsonb, %s)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    (key, tenant_id, json.dumps(response), expires),
                )
            return
    except Exception:
        pass
    with Database().connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO idempotency_keys (key, tenant_id, response, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, tenant_id, json.dumps(response), datetime.now(timezone.utc).isoformat(), expires.isoformat()),
        )
