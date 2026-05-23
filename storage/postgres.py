"""PostgreSQL optionnel (Phase 3). CSV + SQLite restent la source par défaut."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings


def postgres_configured() -> bool:
    backend = (settings.storage_backend or "sqlite").strip().lower()
    url = (getattr(settings, "database_url", None) or "").strip()
    return backend == "postgres" and bool(url)


def apply_schema() -> str:
    if not postgres_configured():
        raise RuntimeError(
            "Postgres non configuré : STORAGE_BACKEND=postgres et DATABASE_URL dans .env"
        )
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Installez psycopg2-binary : pip install psycopg2-binary"
        ) from exc
    schema_path = Path(__file__).resolve().parent / "postgres_schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
    return str(schema_path)


def ping() -> dict[str, Any]:
    if not postgres_configured():
        return {"ok": False, "skipped": True}
    try:
        import psycopg2

        conn = psycopg2.connect(settings.database_url)
        conn.close()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
