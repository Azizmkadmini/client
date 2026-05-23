"""Accès PostgreSQL unifié (acquisition + content) — Phase 3 SSOT."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from config import settings
from storage.postgres import postgres_configured

LEAD_COLUMNS = [
    "id",
    "name",
    "company",
    "link",
    "email",
    "phone",
    "tag",
    "status",
    "channel",
    "follow_up_stage",
    "last_contacted_at",
    "next_follow_up_at",
    "notes",
    "fingerprint",
    "created_at",
]


@contextmanager
def pg_connection():
    if not postgres_configured():
        raise RuntimeError("PostgreSQL non configuré (STORAGE_BACKEND=postgres, DATABASE_URL)")
    import psycopg2

    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def pg_cursor():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(settings.database_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def apply_all_schemas() -> list[str]:
    if not postgres_configured():
        raise RuntimeError("PostgreSQL non configuré")
    import psycopg2

    root = Path(__file__).resolve().parent
    applied: list[str] = []
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            for name in (
                "postgres_schema.sql",
                "postgres_schema_content.sql",
                "postgres_schema_phase5.sql",
                "postgres_schema_enterprise.sql",
                "postgres_indexes.sql",
            ):
                path = root / name
                if path.exists():
                    cur.execute(path.read_text(encoding="utf-8"))
                    applied.append(name)
        conn.commit()
    finally:
        conn.close()
    return applied


def upsert_lead_row(row: dict[str, Any]) -> None:
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO leads (
                id, fingerprint, name, company, email, phone, link, linkedin, instagram,
                tag, status, channel, follow_up_stage, last_contacted_at, next_follow_up_at,
                notes, consent, created_at, updated_at
            ) VALUES (
                %(id)s::uuid, %(fingerprint)s, %(name)s, %(company)s, %(email)s, %(phone)s,
                %(link)s, %(linkedin)s, %(instagram)s, %(tag)s, %(status)s, %(channel)s,
                %(follow_up_stage)s, %(last_contacted_at)s, %(next_follow_up_at)s, %(notes)s,
                TRUE, COALESCE(%(created_at)s::timestamptz, NOW()), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                company = EXCLUDED.company,
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                link = EXCLUDED.link,
                linkedin = EXCLUDED.linkedin,
                instagram = EXCLUDED.instagram,
                tag = EXCLUDED.tag,
                status = EXCLUDED.status,
                channel = EXCLUDED.channel,
                follow_up_stage = EXCLUDED.follow_up_stage,
                last_contacted_at = EXCLUDED.last_contacted_at,
                next_follow_up_at = EXCLUDED.next_follow_up_at,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """,
            _lead_params(row),
        )


def _lead_params(row: dict[str, Any]) -> dict[str, Any]:
    lid = row.get("id") or str(uuid.uuid4())
    channel = row.get("channel") or "linkedin"
    link = row.get("link") or ""
    return {
        "id": lid,
        "fingerprint": row.get("fingerprint") or lid,
        "name": row.get("name"),
        "company": row.get("company") or "",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
        "link": link,
        "linkedin": row.get("linkedin") or (link if channel == "linkedin" else ""),
        "instagram": row.get("instagram") or (link if channel == "instagram" else ""),
        "tag": row.get("tag") or "cold",
        "status": row.get("status") or "new",
        "channel": channel,
        "follow_up_stage": int(row.get("follow_up_stage") or 1),
        "last_contacted_at": row.get("last_contacted_at") or None,
        "next_follow_up_at": row.get("next_follow_up_at") or None,
        "notes": row.get("notes") or "",
        "created_at": row.get("created_at") or None,
    }


def fetch_leads_page(*, offset: int = 0, limit: int = 100) -> tuple[pd.DataFrame, int]:
    """Pagination leads — évite SELECT * sur gros tenants."""
    with pg_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM leads")
        total = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT id::text, fingerprint, name, company, email, phone, link,
                   tag, status, channel, follow_up_stage::text AS follow_up_stage,
                   last_contacted_at::text AS last_contacted_at,
                   next_follow_up_at::text AS next_follow_up_at,
                   notes, created_at::text AS created_at
            FROM leads ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=LEAD_COLUMNS), total
    df = _rows_to_leads_df(rows)
    return df, total


def _rows_to_leads_df(rows) -> pd.DataFrame:
    records = []
    for r in rows:
        d = dict(r)
        records.append(
            {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "company": d.get("company") or "",
                "link": d.get("link") or "",
                "email": d.get("email") or "",
                "phone": d.get("phone") or "",
                "tag": d.get("tag") or "cold",
                "status": d.get("status") or "new",
                "channel": d.get("channel") or "linkedin",
                "follow_up_stage": str(d.get("follow_up_stage") or "1"),
                "last_contacted_at": (d.get("last_contacted_at") or "").replace(" ", "T")[:19],
                "next_follow_up_at": (d.get("next_follow_up_at") or "").replace(" ", "T")[:19],
                "notes": d.get("notes") or "",
                "fingerprint": d.get("fingerprint") or "",
                "created_at": (d.get("created_at") or "").replace(" ", "T")[:19],
            }
        )
    return pd.DataFrame(records)


def fetch_all_leads_df() -> pd.DataFrame:
    with pg_cursor() as cur:
        cur.execute(
            """
            SELECT id::text, fingerprint, name, company, email, phone, link,
                   tag, status, channel, follow_up_stage::text AS follow_up_stage,
                   last_contacted_at::text AS last_contacted_at,
                   next_follow_up_at::text AS next_follow_up_at,
                   notes, created_at::text AS created_at
            FROM leads ORDER BY created_at ASC
            """
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=LEAD_COLUMNS)
    return _rows_to_leads_df(rows)


def save_leads_df(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        if not str(row.get("name", "")).strip():
            continue
        upsert_lead_row(dict(row))


def import_csv_to_postgres(csv_path: Path) -> int:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    n = 0
    for _, row in df.iterrows():
        if not str(row.get("name", "")).strip():
            continue
        upsert_lead_row(dict(row))
        n += 1
    return n


def persist_scraper_job(job: dict[str, Any]) -> None:
    with pg_cursor() as cur:
        cur.execute(
            """
            INSERT INTO scraper_jobs (id, job_type, status, payload, result, error, created_at, finished_at)
            VALUES (%(id)s::uuid, %(job_type)s, %(status)s, %(payload)s::jsonb, %(result)s::jsonb,
                    %(error)s, COALESCE(%(created_at)s::timestamptz, NOW()), %(finished_at)s::timestamptz)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                result = EXCLUDED.result,
                error = EXCLUDED.error,
                finished_at = EXCLUDED.finished_at
            """,
            {
                "id": job.get("job_id") or job.get("id") or str(uuid.uuid4()),
                "job_type": job.get("job_type", "unknown"),
                "status": job.get("status", "queued"),
                "payload": json.dumps(job.get("payload") or {}),
                "result": json.dumps(job.get("result") or {}),
                "error": job.get("error"),
                "created_at": job.get("created_at"),
                "finished_at": job.get("finished_at"),
            },
        )
