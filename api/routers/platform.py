"""API plateforme — jobs, rate limits, storage (phases 3–5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.deps import AuthContext
from config import settings
from services.rate_limit_engine import CentralRateLimiter
from storage.postgres import ping as pg_ping, postgres_configured
from workers.queue import JobQueue

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/status")
def platform_status(ctx: AuthContext) -> dict[str, Any]:
    queue = JobQueue()
    workers = []
    if queue.enabled:
        try:
            client = queue._client()
            for key in client.scan_iter("worker:heartbeat:*", count=20):
                workers.append({"id": key.replace("worker:heartbeat:", ""), "last": client.get(key)})
        except Exception:
            pass
    return {
        "tenant_id": ctx["tenant_id"],
        "auth": ctx.get("auth"),
        "postgres": pg_ping(),
        "storage_backend": settings.storage_backend,
        "redis": {
            "enabled": queue.enabled,
            "url_set": bool(settings.redis_url),
            "queues": queue.stats() if queue.enabled else {},
        },
        "workers": workers,
    }


@router.post("/jobs/queue/recover")
def recover_stale_jobs(ctx: AuthContext) -> dict[str, int]:
    queue = JobQueue()
    if not queue.enabled:
        raise HTTPException(status_code=503, detail="REDIS_URL non configuré")
    n = queue.recover_stale()
    return {"recovered": n}


@router.get("/jobs/queue/stats")
def queue_stats(ctx: AuthContext) -> dict[str, Any]:
    from workers.queue import CONTENT_QUEUE

    acq = JobQueue()
    content = JobQueue(names=CONTENT_QUEUE)
    return {
        "acquisition": acq.stats() if acq.enabled else {},
        "content": content.stats() if content.enabled else {},
    }


@router.get("/rate-limits")
def rate_limits(ctx: AuthContext) -> dict[str, Any]:
    channels = ("linkedin", "email", "instagram", "content_publish")
    out = {}
    for ch in channels:
        rl = CentralRateLimiter(ch, tenant_id=ctx["tenant_id"])
        out[ch] = {"remaining": rl.remaining(), "daily_max": rl.daily_max, "can_send": rl.can_send()}
    return out


@router.get("/jobs/scraper")
def list_scraper_jobs(ctx: AuthContext, limit: int = 20) -> dict[str, Any]:
    if postgres_configured():
        from storage.postgres_backend import pg_cursor

        with pg_cursor() as cur:
            cur.execute(
                """
                SELECT id::text, job_type, status, created_at, finished_at, error
                FROM scraper_jobs ORDER BY created_at DESC LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        return {"source": "postgres", "jobs": rows}
    queue = JobQueue()
    if not queue.enabled:
        return {"source": "none", "jobs": [], "message": "Redis ou Postgres requis"}
    ids = queue.list_dlq(limit=limit)
    jobs = []
    for jid in ids:
        j = queue.get(jid)
        if j:
            jobs.append(
                {
                    "id": j.job_id,
                    "job_type": j.job_type,
                    "status": j.status,
                    "error": j.error,
                }
            )
    return {"source": "redis_dlq_sample", "jobs": jobs}
