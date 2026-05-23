"""Jobs outreach — email, linkedin DM."""

from __future__ import annotations

from typing import Any

from config import settings
from workers.queue import ScraperJob


def execute_outreach_job(job: ScraperJob) -> dict[str, Any]:
    payload = job.payload or {}
    if job.job_type == "outreach-email":
        limit = int(payload.get("limit", 5))
        from orchestrator.email_campaign import run_email_campaign_from_scraper_csv

        result = run_email_campaign_from_scraper_csv(limit=limit)
        return result.to_dict()
    if job.job_type == "outreach-channel":
        channel = str(payload.get("channel", "email"))
        limit = int(payload.get("limit", 5))
        import subprocess
        import sys

        cmd = [sys.executable, "outreach.py", "run", channel, "--limit", str(limit), "--headless"]
        completed = subprocess.run(cmd, cwd=str(settings.root), capture_output=True, text=True)
        return {
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[-2000:],
            "stderr": (completed.stderr or "")[-1000:],
        }
    raise ValueError(f"Job outreach inconnu: {job.job_type}")
