"""Exécution scraper via Redis pour le dashboard (poll jusqu'à fin ou timeout)."""

from __future__ import annotations

import json
import time
from typing import Any

from config import settings
from scraper.cli import ScraperRunResult
from scraper.writer import resolve_scraper_csv_path
from workers.queue import JobQueue


def scraper_queue_available() -> bool:
    if not getattr(settings, "scraper_use_redis_queue", True):
        return False
    return JobQueue().enabled


def _job_type_for_app(app: str) -> str:
    app_l = (app or "linkedin").strip().lower()
    if app_l == "web":
        return "web-run"
    if app_l == "instagram":
        return "instagram-run"
    return "linkedin-run"


def _result_from_job_payload(
    *,
    app: str,
    mode: str,
    query: str,
    job_result: dict[str, Any] | None,
    job_error: str | None,
) -> ScraperRunResult:
    output_path = str(resolve_scraper_csv_path(app))
    if job_error:
        return ScraperRunResult(
            written=0,
            output_path=output_path,
            mode=mode,
            app=app,
            query=query,
            error=job_error,
        )
    if not job_result:
        return ScraperRunResult(
            written=0,
            output_path=output_path,
            mode=mode,
            app=app,
            query=query,
            error="Job terminé sans résultat",
        )
    if job_result.get("returncode", 0) != 0:
        err = job_result.get("stderr") or job_result.get("stdout") or "exit non nul"
        return ScraperRunResult(
            written=0,
            output_path=output_path,
            mode=mode,
            app=app,
            query=query,
            error=str(err)[-2000:],
        )
    stdout = (job_result.get("stdout") or "").strip()
    if stdout:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    return ScraperRunResult(**payload)
                except (json.JSONDecodeError, TypeError):
                    continue
    return ScraperRunResult(
        written=0,
        output_path=output_path,
        mode=mode,
        app=app,
        query=query,
        error="Réponse scraper invalide (JSON attendu en fin de stdout)",
    )


def run_scraper_via_queue(**kwargs: Any) -> ScraperRunResult:
    app = str(kwargs.get("app", "linkedin"))
    mode = str(kwargs.get("mode", "keyword"))
    query = str(kwargs.get("query", "")).strip()
    limit = int(kwargs.get("limit", 10))
    append = bool(kwargs.get("append", True))

    payload: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "mode": mode,
        "replace": not append,
    }
    if kwargs.get("exclude_location") is not None:
        payload["exclude_location"] = kwargs.get("exclude_location")
    if kwargs.get("include_location"):
        payload["include_location"] = kwargs.get("include_location")
    if kwargs.get("search_provider"):
        payload["search_provider"] = kwargs.get("search_provider")
    scopes = kwargs.get("linkedin_scopes")
    if scopes:
        payload["linkedin_scopes"] = list(scopes)

    queue = JobQueue()
    job = queue.enqueue(_job_type_for_app(app), payload)
    timeout_s = max(
        600, int(getattr(settings, "scraper_dashboard_subprocess_timeout_seconds", 14400))
    )
    deadline = time.monotonic() + timeout_s
    poll = max(0.5, float(getattr(settings, "scraper_queue_poll_seconds", 2.0)))

    while time.monotonic() < deadline:
        current = queue.get(job.job_id)
        if current is None:
            time.sleep(poll)
            continue
        if current.status == "done":
            return _result_from_job_payload(
                app=app,
                mode=mode,
                query=query,
                job_result=current.result,
                job_error=None,
            )
        if current.status == "failed":
            return _result_from_job_payload(
                app=app,
                mode=mode,
                query=query,
                job_result=current.result,
                job_error=current.error or "Job échoué",
            )
        time.sleep(poll)

    return ScraperRunResult(
        written=0,
        output_path=str(resolve_scraper_csv_path(app)),
        mode=mode,
        app=app,
        query=query,
        error=(
            f"Timeout file Redis ({timeout_s // 60} min). "
            "Vérifiez que le worker tourne : python -m workers.runner"
        ),
    )
