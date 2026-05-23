"""Content OS — backend PostgreSQL (Phase 3 SSOT)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from storage.postgres_backend import pg_cursor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


class PostgresContentStore:
    @property
    def default_tenant_id(self) -> str:
        tid = (getattr(settings, "default_tenant_id", None) or "").strip()
        return tid or "00000000-0000-0000-0000-000000000001"

    def ensure_default_tenant(self) -> str:
        tid = self.default_tenant_id
        with pg_cursor() as cur:
            cur.execute("SELECT id FROM tenants WHERE id = %s::uuid", (tid,))
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO tenants (id, name, slug, plan, created_at, updated_at)
                    VALUES (%s::uuid, %s, %s, %s, NOW(), NOW())
                    """,
                    (tid, "Default Workspace", "default", "starter"),
                )
        return tid

    def ensure_default_linkedin_account(self, tenant_id: str) -> str:
        with pg_cursor() as cur:
            cur.execute(
                """
                SELECT id FROM linkedin_accounts
                WHERE tenant_id = %s::uuid AND purpose_publish = TRUE
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
            if row:
                return str(row["id"])
            aid = _id()
            cur.execute(
                """
                INSERT INTO linkedin_accounts (
                    id, tenant_id, label, purpose_publish, health_score, max_posts_per_day,
                    created_at, updated_at
                ) VALUES (%s::uuid, %s::uuid, %s, TRUE, 100, %s, NOW(), NOW())
                """,
                (aid, tenant_id, "default-publish", int(settings.content_max_posts_per_day)),
            )
            return aid

    def create_draft(self, **kwargs: Any) -> dict[str, Any]:
        tenant_id = self.ensure_default_tenant()
        draft_id = _id()
        body = kwargs["body"]
        with pg_cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_drafts (
                    id, tenant_id, title, body, hook, cta, format, category, status, metadata,
                    created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW()
                )
                """,
                (
                    draft_id,
                    tenant_id,
                    kwargs.get("title"),
                    body,
                    kwargs.get("hook"),
                    kwargs.get("cta"),
                    kwargs.get("format", "text"),
                    kwargs.get("category"),
                    kwargs.get("status", "draft"),
                    json.dumps(kwargs.get("metadata") or {}),
                ),
            )
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with pg_cursor() as cur:
            cur.execute("SELECT * FROM content_drafts WHERE id = %s::uuid", (draft_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(draft_id)
        return self._row_draft(row)

    def list_drafts(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = "SELECT * FROM content_drafts WHERE tenant_id = %s::uuid"
        params: list[Any] = [tenant_id]
        if status:
            q += " AND status = %s"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        with pg_cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return [self._row_draft(r) for r in rows]

    def update_draft(self, draft_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"title", "body", "hook", "cta", "format", "category", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_draft(draft_id)
        set_parts = [f"{k} = %s" for k in updates]
        vals = list(updates.values()) + [draft_id]
        with pg_cursor() as cur:
            cur.execute(
                f"UPDATE content_drafts SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s::uuid",
                vals,
            )
        return self.get_draft(draft_id)

    def create_post_from_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        tenant_id = draft["tenant_id"]
        account_id = self.ensure_default_linkedin_account(tenant_id)
        post_id = _id()
        with pg_cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_posts (
                    id, tenant_id, draft_id, linkedin_account_id, body, hook, cta, format,
                    status, created_at, updated_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, 'draft', NOW(), NOW()
                )
                """,
                (
                    post_id,
                    tenant_id,
                    draft_id,
                    account_id,
                    draft["body"],
                    draft.get("hook"),
                    draft.get("cta"),
                    draft["format"],
                ),
            )
        return self.get_post(post_id)

    def get_post(self, post_id: str) -> dict[str, Any]:
        with pg_cursor() as cur:
            cur.execute("SELECT * FROM content_posts WHERE id = %s::uuid", (post_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(post_id)
        return self._row_post(row)

    def list_posts(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = "SELECT * FROM content_posts WHERE tenant_id = %s::uuid"
        params: list[Any] = [tenant_id]
        if status:
            q += " AND status = %s"
            params.append(status)
        q += " ORDER BY COALESCE(scheduled_at, created_at) DESC LIMIT %s"
        params.append(limit)
        with pg_cursor() as cur:
            cur.execute(q, params)
            return [self._row_post(r) for r in cur.fetchall()]

    def schedule_post(self, post_id: str, scheduled_at: str, timezone_name: str = "Europe/Paris") -> dict[str, Any]:
        slot_id = _id()
        with pg_cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM content_posts WHERE id = %s::uuid",
                (post_id,),
            )
            row = cur.fetchone()
            cur.execute(
                """
                UPDATE content_posts SET status = 'scheduled', scheduled_at = %s::timestamptz, updated_at = NOW()
                WHERE id = %s::uuid
                """,
                (scheduled_at, post_id),
            )
            cur.execute(
                """
                INSERT INTO content_calendar_slots (id, tenant_id, post_id, slot_start, timezone, created_at)
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s::timestamptz, %s, NOW())
                """,
                (slot_id, row["tenant_id"], post_id, scheduled_at, timezone_name),
            )
        return self.get_post(post_id)

    def list_calendar(self, *, from_iso: str | None = None, to_iso: str | None = None) -> list[dict[str, Any]]:
        tenant_id = self.ensure_default_tenant()
        q = """
            SELECT s.id AS slot_id, s.slot_start, s.timezone, p.*
            FROM content_calendar_slots s
            JOIN content_posts p ON p.id = s.post_id
            WHERE s.tenant_id = %s::uuid
        """
        params: list[Any] = [tenant_id]
        if from_iso:
            q += " AND s.slot_start >= %s::timestamptz"
            params.append(from_iso)
        if to_iso:
            q += " AND s.slot_start <= %s::timestamptz"
            params.append(to_iso)
        q += " ORDER BY s.slot_start ASC"
        with pg_cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        out = []
        for r in rows:
            post = self._row_post(r)
            post["slot_id"] = str(r["slot_id"])
            post["slot_start"] = r["slot_start"].isoformat() if hasattr(r["slot_start"], "isoformat") else r["slot_start"]
            post["timezone"] = r["timezone"]
            out.append(post)
        return out

    def posts_published_today_count(self) -> int:
        tenant_id = self.ensure_default_tenant()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with pg_cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM content_posts
                WHERE tenant_id = %s::uuid AND status = 'published'
                  AND published_at::date = %s::date
                """,
                (tenant_id, today),
            )
            row = cur.fetchone()
        return int(row["c"] if row else 0)

    def enqueue_publish(self, post_id: str) -> dict[str, Any]:
        max_day = int(settings.content_max_posts_per_day or 2)
        if self.posts_published_today_count() >= max_day:
            raise RuntimeError(f"Limite publication ({max_day}/jour).")
        post = self.get_post(post_id)
        job_id = _id()
        with pg_cursor() as cur:
            cur.execute(
                "UPDATE content_posts SET status = 'publishing', updated_at = NOW() WHERE id = %s::uuid",
                (post_id,),
            )
            cur.execute(
                """
                INSERT INTO content_publish_jobs (id, tenant_id, post_id, status, scheduled_for, created_at)
                VALUES (%s::uuid, %s::uuid, %s::uuid, 'queued', NOW(), NOW())
                """,
                (job_id, post["tenant_id"], post_id),
            )
        return {"job_id": job_id, "post_id": post_id, "status": "queued"}

    def complete_publish_job(self, job_id: str, *, success: bool, linkedin_url: str | None = None, error: str | None = None, result: dict | None = None) -> None:
        with pg_cursor() as cur:
            cur.execute("SELECT post_id FROM content_publish_jobs WHERE id = %s::uuid", (job_id,))
            job = cur.fetchone()
            if job is None:
                return
            post_id = str(job["post_id"])
            status = "done" if success else "failed"
            cur.execute(
                """
                UPDATE content_publish_jobs
                SET status = %s, finished_at = NOW(), error = %s, result = %s::jsonb, attempts = attempts + 1
                WHERE id = %s::uuid
                """,
                (status, error, json.dumps(result or {}), job_id),
            )
            if success:
                cur.execute(
                    """
                    UPDATE content_posts
                    SET status = 'published', published_at = NOW(), linkedin_post_url = %s, updated_at = NOW(), error = NULL
                    WHERE id = %s::uuid
                    """,
                    (linkedin_url, post_id),
                )
            else:
                cur.execute(
                    "UPDATE content_posts SET status = 'failed', error = %s, updated_at = NOW() WHERE id = %s::uuid",
                    (error, post_id),
                )

    def get_publish_job(self, job_id: str) -> dict[str, Any]:
        with pg_cursor() as cur:
            cur.execute("SELECT * FROM content_publish_jobs WHERE id = %s::uuid", (job_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(job_id)
        return {k: (str(v) if k.endswith("_id") or k == "id" else v) for k, v in dict(row).items()}

    def record_metrics(self, post_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        mid = _id()
        snap = metrics.get("snapshot_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        imp = int(metrics.get("impressions", 0))
        likes = int(metrics.get("likes", 0))
        comments = int(metrics.get("comments", 0))
        saves = int(metrics.get("saves", 0))
        visits = int(metrics.get("profile_visits", 0))
        dm = int(metrics.get("dm_conversions", 0))
        eng = (likes + comments * 2 + saves * 3) / max(imp, 1) * 100
        with pg_cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_post_metrics (
                    id, post_id, snapshot_date, impressions, likes, comments, saves,
                    profile_visits, dm_conversions, engagement_score, created_at
                ) VALUES (
                    %s::uuid, %s::uuid, %s::date, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                ON CONFLICT DO NOTHING
                """,
                (mid, post_id, snap, imp, likes, comments, saves, visits, dm, eng),
            )
        return {"post_id": post_id, "snapshot_date": snap, "engagement_score": eng}

    def get_post_metrics(self, post_id: str) -> list[dict[str, Any]]:
        with pg_cursor() as cur:
            cur.execute(
                "SELECT * FROM content_post_metrics WHERE post_id = %s::uuid ORDER BY snapshot_date DESC",
                (post_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_due_scheduled_posts(self) -> list[dict[str, Any]]:
        now = _now()
        with pg_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM content_posts
                WHERE status = 'scheduled' AND scheduled_at IS NOT NULL AND scheduled_at <= NOW()
                ORDER BY scheduled_at ASC
                """
            )
            return [self._row_post(r) for r in cur.fetchall()]

    def reschedule_slot(self, post_id: str, scheduled_at: str) -> dict[str, Any]:
        with pg_cursor() as cur:
            cur.execute(
                "UPDATE content_posts SET scheduled_at = %s::timestamptz, updated_at = NOW() WHERE id = %s::uuid",
                (scheduled_at, post_id),
            )
            cur.execute(
                "UPDATE content_calendar_slots SET slot_start = %s::timestamptz WHERE post_id = %s::uuid",
                (scheduled_at, post_id),
            )
        return self.get_post(post_id)

    def _bump_template_score(self, post_id: str, *, engagement: float) -> None:
        pass  # optional PG implementation

    @staticmethod
    def _row_draft(row: Any) -> dict[str, Any]:
        d = {
            k: (str(v) if k in ("id", "tenant_id", "linkedin_account_id", "author_user_id") and v is not None else v)
            for k, v in dict(row).items()
        }
        meta = d.get("metadata")
        if isinstance(meta, str):
            try:
                d["metadata"] = json.loads(meta)
            except json.JSONDecodeError:
                d["metadata"] = {}
        elif meta is None:
            d["metadata"] = {}
        for ts in ("created_at", "updated_at"):
            if hasattr(d.get(ts), "isoformat"):
                d[ts] = d[ts].isoformat()
        d["id"] = str(d.get("id", ""))
        d["tenant_id"] = str(d.get("tenant_id", ""))
        return d

    @staticmethod
    def _row_post(row: Any) -> dict[str, Any]:
        d = dict(row)
        for k in ("id", "tenant_id", "draft_id", "linkedin_account_id"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        for ts in ("created_at", "updated_at", "scheduled_at", "published_at"):
            if hasattr(d.get(ts), "isoformat"):
                d[ts] = d[ts].isoformat()
        return d
