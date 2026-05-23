"""Webhooks n8n et intégrations externes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import AuthContext
from workers.queue import JobQueue, ScraperJob

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class N8nPayload(BaseModel):
    job_type: str
    payload: dict[str, Any] = {}


@router.post("/n8n/{workflow_id}")
def n8n_webhook(workflow_id: str, body: N8nPayload, ctx: AuthContext) -> dict[str, Any]:
    """n8n POST → enqueue job Redis."""
    queue = JobQueue()
    if not queue.enabled:
        raise HTTPException(status_code=503, detail="Redis requis pour webhooks n8n")
    enriched = {**body.payload, "workflow_id": workflow_id, "tenant_id": ctx["tenant_id"]}
    job = queue.enqueue(body.job_type, enriched)
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/dlq")
def list_dead_letter(ctx: AuthContext) -> dict:
    queue = JobQueue()
    return {"jobs": queue.list_dlq()}
