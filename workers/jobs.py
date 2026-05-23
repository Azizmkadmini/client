from __future__ import annotations

import subprocess
import sys
from typing import Any

from config import settings
from workers.queue import ScraperJob


def _run_cli(args: list[str]) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "scraper.cli", *args]
    completed = subprocess.run(
        cmd,
        cwd=str(settings.root),
        capture_output=True,
        text=True,
        timeout=max(
            int(settings.scraper_dashboard_subprocess_timeout_seconds),
            3600,
        ),
    )
    return {
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[-8000:],
        "stderr": (completed.stderr or "")[-4000:],
        "cmd": " ".join(cmd),
    }


def execute_job(job: ScraperJob) -> dict[str, Any]:
    payload = job.payload or {}
    if job.job_type == "web-run":
        args = [
            "web-run",
            "--query",
            str(payload.get("query", "agence marketing digitale")),
            "--limit",
            str(int(payload.get("limit", 10))),
            "--json",
        ]
        if payload.get("replace"):
            args.append("--replace")
        ex = (payload.get("exclude_location") or "").strip()
        if ex:
            args.extend(["--exclude-location", ex])
        sp = (payload.get("search_provider") or "").strip()
        if sp:
            args.extend(["--search-provider", sp])
        return _run_cli(args)

    if job.job_type == "linkedin-run":
        args = ["run", "--app", "linkedin", "--json"]
        if payload.get("query"):
            args.extend(["--query", str(payload["query"])])
        if payload.get("limit") is not None:
            args.extend(["--limit", str(int(payload["limit"]))])
        if payload.get("mode"):
            args.extend(["--mode", str(payload["mode"])])
        for scope in payload.get("linkedin_scopes") or []:
            if str(scope).strip():
                args.extend(["--linkedin-scope", str(scope).strip()])
        inc = (payload.get("include_location") or "").strip()
        if inc:
            args.extend(["--include-location", inc])
        ex = payload.get("exclude_location")
        if ex is not None:
            args.extend(["--exclude-location", str(ex)])
        if payload.get("replace"):
            args.append("--replace")
        return _run_cli(args)

    if job.job_type == "instagram-run":
        args = ["run", "--app", "instagram", "--json"]
        if payload.get("query"):
            args.extend(["--query", str(payload["query"])])
        if payload.get("limit") is not None:
            args.extend(["--limit", str(int(payload["limit"]))])
        if payload.get("mode"):
            args.extend(["--mode", str(payload["mode"])])
        if payload.get("replace"):
            args.append("--replace")
        return _run_cli(args)

    raise ValueError(f"Type de job inconnu: {job.job_type}")
