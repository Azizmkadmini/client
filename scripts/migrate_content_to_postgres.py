"""
Copie Content OS SQLite → PostgreSQL.

Prérequis: STORAGE_BACKEND=postgres, DATABASE_URL, schémas appliqués.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import settings
from storage.database import Database
from storage.postgres import postgres_configured
from storage.postgres_backend import apply_all_schemas, pg_cursor


def main() -> int:
    if not postgres_configured():
        print("STORAGE_BACKEND=postgres + DATABASE_URL requis")
        return 1
    apply_all_schemas()
    db = Database()
    stats = {"drafts": 0, "posts": 0, "metrics": 0}
    with db.connect() as conn:
        drafts = conn.execute("SELECT * FROM content_drafts").fetchall()
        posts = conn.execute("SELECT * FROM content_posts").fetchall()
        metrics = conn.execute("SELECT * FROM content_post_metrics").fetchall()
        tenants = conn.execute("SELECT * FROM tenants").fetchall()
    with pg_cursor() as cur:
        for t in tenants:
            cur.execute(
                """
                INSERT INTO tenants (id, name, slug, plan, created_at, updated_at)
                VALUES (%s::uuid, %s, %s, %s, %s::timestamptz, %s::timestamptz)
                ON CONFLICT (id) DO NOTHING
                """,
                (t["id"], t["name"], t["slug"], t["plan"], t["created_at"], t["updated_at"]),
            )
        tid = settings.default_tenant_id
        cur.execute(
            """
            INSERT INTO linkedin_accounts (
                id, tenant_id, label, purpose_publish, health_score, max_posts_per_day, created_at, updated_at
            )
            SELECT gen_random_uuid(), %s::uuid, 'migrated-default', TRUE, 100, 2, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM linkedin_accounts WHERE tenant_id = %s::uuid
            )
            """,
            (tid, tid),
        )
        cur.execute(
            "SELECT id FROM linkedin_accounts WHERE tenant_id = %s::uuid LIMIT 1",
            (tid,),
        )
        default_acct = str(cur.fetchone()["id"])
        for d in drafts:
            cur.execute(
                """
                INSERT INTO content_drafts (
                    id, tenant_id, title, body, hook, cta, format, category, status, metadata,
                    created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    d["id"],
                    d["tenant_id"],
                    d["title"],
                    d["body"],
                    d["hook"],
                    d["cta"],
                    d["format"],
                    d["category"],
                    d["status"],
                    d["metadata"] if isinstance(d["metadata"], str) else json.dumps(d["metadata"] or {}),
                    d["created_at"],
                    d["updated_at"],
                ),
            )
            stats["drafts"] += 1
        for p in posts:
            acct = p.get("linkedin_account_id") or default_acct
            cur.execute(
                """
                INSERT INTO content_posts (
                    id, tenant_id, draft_id, linkedin_account_id, body, hook, cta, format,
                    status, scheduled_at, published_at, linkedin_post_url, error, created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s,
                    %s::timestamptz, %s::timestamptz, %s, %s, %s::timestamptz, %s::timestamptz
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    p["id"],
                    p["tenant_id"],
                    p.get("draft_id"),
                    acct,
                    p["body"],
                    p.get("hook"),
                    p.get("cta"),
                    p["format"],
                    p["status"],
                    p.get("scheduled_at"),
                    p.get("published_at"),
                    p.get("linkedin_post_url"),
                    p.get("error"),
                    p["created_at"],
                    p["updated_at"],
                ),
            )
            stats["posts"] += 1
        for m in metrics:
            cur.execute(
                """
                INSERT INTO content_post_metrics (
                    id, post_id, snapshot_date, impressions, likes, comments, saves,
                    profile_visits, dm_conversions, engagement_score, created_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::date, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    m["id"],
                    m["post_id"],
                    m["snapshot_date"],
                    m["impressions"],
                    m["likes"],
                    m["comments"],
                    m["saves"],
                    m["profile_visits"],
                    m["dm_conversions"],
                    m["engagement_score"],
                    m["created_at"],
                ),
            )
            stats["metrics"] += 1
    print("Migration content OK:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
