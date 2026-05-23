"""Persistance Content OS — SQLite (Postgres via storage/postgres_schema_content.sql en prod)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from storage.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _postgres_backend():
    from storage.postgres import postgres_configured

    if postgres_configured():
        from content.postgres_store import PostgresContentStore

        return PostgresContentStore()
    return None


class ContentStore:
    def __new__(cls):
        pg = _postgres_backend()
        if pg is not None:
            return pg
        return super().__new__(cls)

    def __init__(self) -> None:
        self.db = Database()
        self.db.migrate()

    @property
    def default_tenant_id(self) -> str:
        tid = (getattr(settings, "default_tenant_id", None) or "").strip()
        return tid or "00000000-0000-0000-0000-000000000001"

    def ensure_default_tenant(self) -> str:
        tid = self.default_tenant_id
        now = _now()
        with self.db.connect() as conn:
            row = conn.execute("SELECT id FROM tenants WHERE id = ?", (tid,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO tenants (id, name, slug, plan, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (tid, "Default Workspace", "default", "starter", now, now),
                )
        return tid

    def create_draft(
        self,
        *,
        body: str,
        hook: str | None = None,
        cta: str | None = None,
        format: str = "text",
        category: str | None = None,
        title: str | None = None,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_id = self.ensure_default_tenant()
        draft_id = _id()
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_drafts (
                    id, tenant_id, title, body, hook, cta, format, category, status, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    tenant_id,
                    title,
                    body,
                    hook,
                    cta,
                    format,
                    category,
                    status,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError(f"Draft {draft_id} introuvable")
        return self._row_draft(row)

    def list_drafts(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = "SELECT * FROM content_drafts WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_draft(r) for r in rows]

    def update_draft(self, draft_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"title", "body", "hook", "cta", "format", "category", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_draft(draft_id)
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self.db.connect() as conn:
            conn.execute(
                f"UPDATE content_drafts SET {set_clause} WHERE id = ?",
                (*updates.values(), draft_id),
            )
        return self.get_draft(draft_id)

    def create_post_from_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        post_id = _id()
        now = _now()
        tenant_id = draft["tenant_id"]
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_posts (
                    id, tenant_id, draft_id, body, hook, cta, format, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
                """,
                (
                    post_id,
                    tenant_id,
                    draft_id,
                    draft["body"],
                    draft.get("hook"),
                    draft.get("cta"),
                    draft["format"],
                    now,
                    now,
                ),
            )
        return self.get_post(post_id)

    def get_post(self, post_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM content_posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise KeyError(f"Post {post_id} introuvable")
        return self._row_post(row)

    def list_posts(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = "SELECT * FROM content_posts WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY COALESCE(scheduled_at, created_at) DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_post(r) for r in rows]

    def schedule_post(self, post_id: str, scheduled_at: str, timezone_name: str = "Europe/Paris") -> dict[str, Any]:
        now = _now()
        slot_id = _id()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE content_posts SET status = 'scheduled', scheduled_at = ?, updated_at = ? WHERE id = ?",
                (scheduled_at, now, post_id),
            )
            post = conn.execute("SELECT tenant_id FROM content_posts WHERE id = ?", (post_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO content_calendar_slots (id, tenant_id, post_id, slot_start, timezone, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (slot_id, post["tenant_id"], post_id, scheduled_at, timezone_name, now),
            )
        return self.get_post(post_id)

    def reschedule_slot(self, post_id: str, scheduled_at: str) -> dict[str, Any]:
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE content_posts SET scheduled_at = ?, updated_at = ? WHERE id = ?",
                (scheduled_at, now, post_id),
            )
            conn.execute(
                "UPDATE content_calendar_slots SET slot_start = ? WHERE post_id = ?",
                (scheduled_at, post_id),
            )
        return self.get_post(post_id)

    def list_calendar(self, *, from_iso: str | None = None, to_iso: str | None = None) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = """
            SELECT s.id AS slot_id, s.slot_start, s.timezone, p.*
            FROM content_calendar_slots s
            JOIN content_posts p ON p.id = s.post_id
            WHERE s.tenant_id = ?
        """
        params: list[Any] = [tenant_id]
        if from_iso:
            q += " AND s.slot_start >= ?"
            params.append(from_iso)
        if to_iso:
            q += " AND s.slot_start <= ?"
            params.append(to_iso)
        q += " ORDER BY s.slot_start ASC"
        with self.db.connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            post = self._row_post(r)
            post["slot_id"] = r["slot_id"]
            post["slot_start"] = r["slot_start"]
            post["timezone"] = r["timezone"]
            out.append(post)
        return out

    def posts_published_today_count(self) -> int:
        tenant_id = self.ensure_default_tenant()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM content_posts
                WHERE tenant_id = ? AND status = 'published' AND published_at LIKE ?
                """,
                (tenant_id, f"{today}%"),
            ).fetchone()
        return int(row["c"] if row else 0)

    def enqueue_publish(self, post_id: str) -> dict[str, Any]:
        max_day = int(getattr(settings, "content_max_posts_per_day", 2) or 2)
        if self.posts_published_today_count() >= max_day:
            raise RuntimeError(
                f"Limite publication ({max_day}/jour). Réessayez demain ou augmentez CONTENT_MAX_POSTS_PER_DAY."
            )
        post = self.get_post(post_id)
        job_id = _id()
        now = _now()
        tenant_id = post["tenant_id"]
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE content_posts SET status = 'publishing', updated_at = ? WHERE id = ?",
                (now, post_id),
            )
            conn.execute(
                """
                INSERT INTO content_publish_jobs (
                    id, tenant_id, post_id, status, scheduled_for, created_at
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (job_id, tenant_id, post_id, now, now),
            )
        return {"job_id": job_id, "post_id": post_id, "status": "queued"}

    def complete_publish_job(
        self,
        job_id: str,
        *,
        success: bool,
        linkedin_url: str | None = None,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        now = _now()
        with self.db.connect() as conn:
            job = conn.execute(
                "SELECT post_id FROM content_publish_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                return
            post_id = job["post_id"]
            status = "done" if success else "failed"
            conn.execute(
                """
                UPDATE content_publish_jobs
                SET status = ?, finished_at = ?, error = ?, result = ?, attempts = attempts + 1
                WHERE id = ?
                """,
                (status, now, error, json.dumps(result or {}), job_id),
            )
            if success:
                conn.execute(
                    """
                    UPDATE content_posts
                    SET status = 'published', published_at = ?, linkedin_post_url = ?, updated_at = ?, error = NULL
                    WHERE id = ?
                    """,
                    (now, linkedin_url, now, post_id),
                )
            else:
                conn.execute(
                    "UPDATE content_posts SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                    (error, now, post_id),
                )

    def get_publish_job(self, job_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM content_publish_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def record_metrics(self, post_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        mid = _id()
        now = _now()
        snap = metrics.get("snapshot_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        imp = int(metrics.get("impressions", 0))
        likes = int(metrics.get("likes", 0))
        comments = int(metrics.get("comments", 0))
        saves = int(metrics.get("saves", 0))
        visits = int(metrics.get("profile_visits", 0))
        dm = int(metrics.get("dm_conversions", 0))
        eng = (likes + comments * 2 + saves * 3) / max(imp, 1) * 100
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO content_post_metrics (
                    id, post_id, snapshot_date, impressions, likes, comments, saves,
                    profile_visits, dm_conversions, engagement_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, post_id, snap, imp, likes, comments, saves, visits, dm, eng, now),
            )
        self._bump_template_score(post_id, engagement=eng)
        return {"post_id": post_id, "snapshot_date": snap, "engagement_score": eng}

    def get_post_metrics(self, post_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM content_post_metrics WHERE post_id = ? ORDER BY snapshot_date DESC",
                (post_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _bump_template_score(self, post_id: str, *, engagement: float) -> None:
        post = self.get_post(post_id)
        tenant_id = post["tenant_id"]
        hour = 12
        if post.get("published_at"):
            try:
                hour = datetime.fromisoformat(post["published_at"].replace("Z", "+00:00")).hour
            except ValueError:
                pass
        key = f"{post.get('format', 'text')}"
        now = _now()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, sample_count, engagement_ema FROM content_template_scores
                WHERE tenant_id = ? AND template_key = ? AND hour_bucket = ?
                """,
                (tenant_id, key, hour),
            ).fetchone()
            if row:
                n = int(row["sample_count"]) + 1
                ema = (float(row["engagement_ema"]) * 0.8) + (engagement * 0.2)
                conn.execute(
                    """
                    UPDATE content_template_scores
                    SET sample_count = ?, engagement_ema = ?, viral_score_ema = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (n, ema, ema * 1.1, now, row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO content_template_scores (
                        id, tenant_id, template_key, format, hour_bucket,
                        sample_count, engagement_ema, viral_score_ema, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (_id(), tenant_id, key, post.get("format"), hour, engagement, engagement, now),
                )

    def list_due_scheduled_posts(self) -> list[dict[str, Any]]:
        now = _now()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM content_posts
                WHERE status = 'scheduled' AND scheduled_at IS NOT NULL AND scheduled_at <= ?
                ORDER BY scheduled_at ASC
                """,
                (now,),
            ).fetchall()
        return [self._row_post(r) for r in rows]

    @staticmethod
    def _row_draft(row: Any) -> dict[str, Any]:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.get("metadata") or "{}")
        except json.JSONDecodeError:
            d["metadata"] = {}
        return d

    @staticmethod
    def _row_post(row: Any) -> dict[str, Any]:
        return dict(row)
