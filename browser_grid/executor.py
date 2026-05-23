"""Exécuteur jobs navigateur — local Playwright ou remote HTTP (E1)."""

from __future__ import annotations

from typing import Any

from config import settings
from services.feature_flags import is_enabled


def execute_publish(body: str, *, tenant_id: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    mode = getattr(settings, "browser_grid_mode", "local").lower()
    if mode == "remote" or is_enabled("browser.grid.remote", tenant_id=tenant_id):
        return _remote_publish(body, tenant_id=tenant_id, account_id=account_id)
    from content.publishing.linkedin import publish_text_post

    return publish_text_post(body, tenant_id=tenant_id, account_id=account_id)


def _remote_publish(body: str, *, tenant_id: str | None, account_id: str | None) -> dict[str, Any]:
    import httpx

    base = getattr(settings, "browser_grid_url", "http://127.0.0.1:8090").rstrip("/")
    try:
        resp = httpx.post(
            f"{base}/jobs/publish",
            json={"body": body, "tenant_id": tenant_id, "account_id": account_id},
            timeout=180.0,
        )
        return resp.json()
    except Exception as exc:
        return {"success": False, "error": f"browser-grid remote: {exc}", "fallback": "use local"}


def execute_scrape(job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    from workers.jobs import execute_job
    from workers.queue import ScraperJob

    return execute_job(ScraperJob(job_type=job_type, payload=payload))
