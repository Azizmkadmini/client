"""API Content OS — génération, calendrier, publication, analytics."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from api.deps import AuthContext
from content import approval as approval_flow
from content.analytics.linkedin_metrics import sync_post_metrics_smart
from content.generation.service import generate_cta, generate_hooks, generate_post
from content.media.r2 import upload_bytes
from content.models import GenerateHookRequest, GeneratePostRequest
from content.optimization.recommendations import get_recommendations, predict_engagement
from content.store import ContentStore
from workers.content_jobs import execute_content_job
from workers.content_runner import ContentJobQueue
from workers.queue import ScraperJob

router = APIRouter(prefix="/content", tags=["content"])


class DraftCreate(BaseModel):
    body: str
    hook: str | None = None
    cta: str | None = None
    format: str = "text"
    category: str | None = None
    title: str | None = None


class DraftUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    hook: str | None = None
    cta: str | None = None
    format: str | None = None
    category: str | None = None
    status: str | None = None


class ScheduleRequest(BaseModel):
    scheduled_at: str
    timezone: str = "Europe/Paris"


class PublishRequest(BaseModel):
    sync: bool = False  # True bloque l'API (Playwright) — utiliser workers


class RejectRequest(BaseModel):
    reason: str = ""


@router.get("/status")
def content_module_status() -> dict[str, str]:
    return {"module": "content-os", "phase": "complete", "platform": "AI Acquisition OS"}


@router.post("/hooks/generate")
def api_generate_hooks(body: GenerateHookRequest, ctx: AuthContext) -> dict[str, Any]:
    try:
        hooks = generate_hooks(body)
        return {"hooks": [h.model_dump() for h in hooks]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/posts/generate")
def api_generate_post(body: GeneratePostRequest, ctx: AuthContext) -> dict[str, Any]:
    try:
        draft = generate_post(body)
        store = ContentStore()
        saved = store.create_draft(
            body=draft.body,
            hook=draft.hook,
            cta=draft.cta,
            format=draft.format.value if hasattr(draft.format, "value") else str(draft.format),
        )
        return {"draft": saved, "generated": draft.model_dump(mode="json")}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/cta/generate")
def api_generate_cta(topic: str, ctx: AuthContext, language: str = "fr") -> dict[str, str]:
    try:
        return {"cta": generate_cta(topic, language=language)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/drafts")
def list_drafts(ctx: AuthContext, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"drafts": ContentStore().list_drafts(status=status, limit=limit)}


@router.post("/drafts")
def create_draft(body: DraftCreate, ctx: AuthContext) -> dict[str, Any]:
    return {"draft": ContentStore().create_draft(**body.model_dump())}


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    try:
        return {"draft": ContentStore().get_draft(str(draft_id))}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: UUID, body: DraftUpdate, ctx: AuthContext) -> dict[str, Any]:
    return {"draft": ContentStore().update_draft(str(draft_id), **body.model_dump(exclude_none=True))}


@router.post("/drafts/{draft_id}/submit-review")
def submit_review(draft_id: UUID, ctx: AuthContext, note: str = "") -> dict[str, Any]:
    return {"draft": approval_flow.submit_for_review(str(draft_id), note)}


@router.post("/drafts/{draft_id}/approve")
def approve_draft_route(draft_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    return {"draft": approval_flow.approve_draft(str(draft_id))}


@router.post("/drafts/{draft_id}/reject")
def reject_draft_route(draft_id: UUID, body: RejectRequest, ctx: AuthContext) -> dict[str, Any]:
    return {"draft": approval_flow.reject_draft(str(draft_id), body.reason)}


@router.post("/media/upload")
async def media_upload(ctx: AuthContext, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    mime = file.content_type or "application/octet-stream"
    return upload_bytes(data, mime_type=mime, filename=file.filename)


@router.get("/posts")
def list_posts(ctx: AuthContext, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"posts": ContentStore().list_posts(status=status, limit=limit)}


@router.post("/posts/from-draft/{draft_id}")
def post_from_draft(draft_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    return {"post": ContentStore().create_post_from_draft(str(draft_id))}


@router.post("/posts/{post_id}/schedule")
def schedule_post(post_id: UUID, body: ScheduleRequest, ctx: AuthContext) -> dict[str, Any]:
    return {"post": ContentStore().schedule_post(str(post_id), body.scheduled_at, body.timezone)}


@router.patch("/posts/{post_id}/schedule")
def reschedule_post(post_id: UUID, body: ScheduleRequest, ctx: AuthContext) -> dict[str, Any]:
    return {"post": ContentStore().reschedule_slot(str(post_id), body.scheduled_at)}


@router.get("/calendar")
def get_calendar(
    ctx: AuthContext, from_iso: str | None = None, to_iso: str | None = None
) -> dict[str, Any]:
    return {"slots": ContentStore().list_calendar(from_iso=from_iso, to_iso=to_iso)}


@router.post("/posts/{post_id}/publish")
def publish_post(
    post_id: UUID,
    body: PublishRequest,
    ctx: AuthContext,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    from services.audit import log_audit
    from services.idempotency import get_cached, store

    if idempotency_key:
        cached = get_cached(idempotency_key)
        if cached:
            return cached
    store = ContentStore()
    try:
        job_info = store.enqueue_publish(str(post_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if body.sync:
        job = ScraperJob(
            job_type="content-publish",
            payload={"post_id": str(post_id), "job_id": job_info["job_id"]},
        )
        result = execute_content_job(job)
        out = {"job": job_info, "sync": True, "result": result}
    else:
        queue = ContentJobQueue()
        if not queue.enabled:
            raise HTTPException(status_code=503, detail="Redis requis pour publish async ou sync=true")
        job = queue.enqueue_content(
            "content-publish",
            {"post_id": str(post_id), "tenant_id": ctx["tenant_id"]},
            idempotency_key=f"publish:{ctx['tenant_id']}:{post_id}",
        )
        out = {"job_id": job.job_id, "post_id": str(post_id), "sync": False}
    log_audit(
        "content.publish",
        tenant_id=ctx["tenant_id"],
        actor_user_id=ctx.get("user_id"),
        resource_type="post",
        resource_id=str(post_id),
    )
    if idempotency_key:
        store(idempotency_key, ctx["tenant_id"], out)
    return out


@router.get("/publish/jobs/{job_id}")
def get_publish_job(job_id: str, ctx: AuthContext) -> dict[str, Any]:
    try:
        return ContentStore().get_publish_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/posts/{post_id}/metrics")
def post_metrics(post_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    return {"metrics": ContentStore().get_post_metrics(str(post_id))}


@router.post("/posts/{post_id}/metrics/sync")
def sync_metrics(post_id: UUID, ctx: AuthContext) -> dict[str, Any]:
    return sync_post_metrics_smart(str(post_id))


@router.get("/optimization/recommendations")
def optimization_recommendations(ctx: AuthContext) -> dict[str, Any]:
    return get_recommendations()


@router.get("/optimization/predict")
def optimization_predict(
    ctx: AuthContext, format: str = "expertise", hour_bucket: int = 9
) -> dict[str, float]:
    return {"predicted_engagement": predict_engagement(format, hour_bucket)}
