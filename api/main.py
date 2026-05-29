from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.deps import AuthContext, get_auth_context, require_api_key
from api.routers import accounts as accounts_router
from api.routers import analytics as analytics_router
from api.routers import auth_router
from api.routers import content as content_router
from api.routers import billing as billing_router
from api.routers import oauth_linkedin as oauth_linkedin_router
from api.routers import enterprise as enterprise_router
from api.routers import platform as platform_router
from api.routers import webhooks as webhooks_router
from compliance.registry import ComplianceRegistry
from config import settings
from connector.ingest import QueueIngestor
from connector.pipeline import ConnectorPipeline
from leads.store import LeadStore
from utils.outreach_logger import OutreachLogger
from orchestrator.runner import Orchestrator, summarize_result
from utils.logging_config import configure_logging
from workers.jobs import execute_job
from workers.queue import JobQueue, ScraperJob
from api.middleware import TenantContextMiddleware
from api.telemetry import setup_telemetry

configure_logging()

from services.env_validation import validate_or_warn

validate_or_warn()

_origins = [o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()]

app = FastAPI(title="AI Acquisition OS API", version="2.2.0-production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type", "X-Tenant-Id"],
)
app.add_middleware(TenantContextMiddleware)
setup_telemetry(app)
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(content_router.router, prefix="/api/v1")
app.include_router(analytics_router.router, prefix="/api/v1")
app.include_router(accounts_router.router, prefix="/api/v1")
app.include_router(webhooks_router.router, prefix="/api/v1")
app.include_router(billing_router.router, prefix="/api/v1")
app.include_router(oauth_linkedin_router.router, prefix="/api/v1")
app.include_router(platform_router.router, prefix="/api/v1")
app.include_router(enterprise_router.router, prefix="/api/v1")

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics/prometheus")
except Exception:
    pass


@app.post("/api/v1/admin/migrate-postgres")
def migrate_postgres(ctx: AuthContext) -> dict:
    from storage.postgres_backend import apply_all_schemas

    return {"applied": apply_all_schemas()}




class OptOutRequest(BaseModel):
    identifier: str
    reason: str = "user_request"


class ConnectorRunRequest(BaseModel):
    source: str = "csv"
    retry_failed: bool = False
    auto_ingest: bool = True


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        from utils.platform_health import run_checks

        report = run_checks()
        return {
            "status": "ok" if report.get("ok") else "degraded",
            "checks": {k: v for k, v in report.items() if k != "ok"},
        }
    except Exception as exc:
        return {"status": "ok", "checks_error": str(exc)}


@app.get("/metrics")
def metrics(ctx: AuthContext) -> dict[str, Any]:
    store = LeadStore()
    logger = OutreachLogger()
    return {
        "leads": store.stats(),
        "outreach": logger.metrics(),
    }


@app.get("/leads")
def list_leads(
    ctx: AuthContext,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    store = LeadStore()
    items, total = store.list_page(offset=offset, limit=limit)
    return {
        "items": [lead.model_dump() for lead in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


class OrchestratorRunRequest(BaseModel):
    source: str = "csv"
    retry_failed: bool = False
    per_channel_limit: int | None = None
    run_scraper_step: bool = True
    run_outreach: bool = True


class ScraperJobRequest(BaseModel):
    job_type: str  # web-run | linkedin-run | instagram-run
    payload: dict[str, Any] = {}
    sync: bool = False


@app.post("/orchestrator/run")
def run_orchestrator(body: OrchestratorRunRequest, ctx: AuthContext) -> dict[str, Any]:
    result = Orchestrator().run_once(
        source=body.source,
        retry_failed=body.retry_failed,
        per_channel_limit=body.per_channel_limit,
        run_scraper_step=body.run_scraper_step,
        run_outreach=body.run_outreach,
    )
    return summarize_result(result)


@app.post("/connector/run")
def run_connector(body: ConnectorRunRequest, ctx: AuthContext) -> dict[str, Any]:
    pipeline = ConnectorPipeline()
    result = pipeline.run(source=body.source, retry_failed=body.retry_failed)
    ingest_result = None
    if body.auto_ingest:
        ingest_result = QueueIngestor().ingest()
    return {
        "connector": result.__dict__,
        "ingest": None if ingest_result is None else ingest_result.__dict__,
    }


@app.post("/connector/ingest")
def ingest_queue(ctx: AuthContext) -> dict[str, Any]:
    result = QueueIngestor().ingest()
    return result.__dict__


@app.post("/compliance/opt-out")
def opt_out(body: OptOutRequest, ctx: AuthContext) -> dict[str, str]:
    ComplianceRegistry().register_opt_out(body.identifier, body.reason)
    return {"status": "registered", "identifier": body.identifier.strip().lower()}


@app.post("/jobs/scraper")
def enqueue_scraper_job(body: ScraperJobRequest, ctx: AuthContext) -> dict[str, Any]:
    queue = JobQueue()
    if body.sync or not queue.enabled:
        if not queue.enabled and not settings.scraper_queue_sync_fallback:
            raise HTTPException(
                status_code=503,
                detail="Redis indisponible (REDIS_URL). Activez Redis ou sync=true.",
            )
        job = ScraperJob(job_type=body.job_type, payload=body.payload)
        try:
            result = execute_job(job)
            job.status = "done" if result.get("returncode") == 0 else "failed"
            job.result = result
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        return {
            "job_id": job.job_id,
            "status": job.status,
            "sync": True,
            "result": job.result,
            "error": job.error,
        }
    job = queue.enqueue(body.job_type, body.payload)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "sync": False,
        "message": "Job en file. Lancez: python -m workers.runner",
    }


@app.get("/jobs/scraper/{job_id}")
def get_scraper_job(job_id: str, ctx: AuthContext) -> dict[str, Any]:
    queue = JobQueue()
    if not queue.enabled:
        raise HTTPException(status_code=503, detail="REDIS_URL non configuré")
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }
