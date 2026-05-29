from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from config import settings
from connector.logger import ConnectorLogger
from connector.queue_manager import QueueManager
from leads.store import LeadStore
from utils.outreach_logger import OutreachLogger
from scraper.cli import ScraperRunResult
from scraper.writer import resolve_scraper_csv_path
from utils.behavior import RateLimiter


def load_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def load_queue() -> list[dict[str, Any]]:
    path = settings.path(settings.connector_queue_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    return data if isinstance(data, list) else []


def _scraper_paths_for_app(app: str | None) -> list[Path]:
    """Un fichier par réseau : LinkedIn et Instagram ne sont pas fusionnés dans les listes UI."""
    app_l = (app or "").strip().lower()
    if app_l == "instagram":
        return [resolve_scraper_csv_path("instagram")]
    if app_l == "web":
        return [resolve_scraper_csv_path("web")]
    if app_l == "linkedin":
        return [settings.path(settings.scraper_output_csv)]
    paths: list[Path] = [settings.path(settings.scraper_output_csv)]
    extra = (getattr(settings, "scraper_instagram_output_csv", None) or "").strip()
    if extra:
        ig = settings.path(extra)
        if ig.resolve() not in {p.resolve() for p in paths}:
            paths.append(ig)
    return paths


def load_scraper_frame(app: str | None = None) -> pd.DataFrame:
    from scraper.models import CSV_COLUMNS

    paths = _scraper_paths_for_app(app)
    frames: list[pd.DataFrame] = []
    for p in paths:
        if p.exists():
            frames.append(pd.read_csv(p, dtype=str).fillna("vide"))
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    for column in CSV_COLUMNS:
        if column not in combined.columns:
            combined[column] = "vide"
    app_l = (app or "").strip().lower()
    if app_l and "app" in combined.columns:
        combined = combined[combined["app"].astype(str).str.strip().str.lower() == app_l]
    if "link" in combined.columns:
        combined = combined.drop_duplicates(subset=["link"], keep="last")
    return combined.reset_index(drop=True)


def load_leads_frame() -> pd.DataFrame:
    store = LeadStore()
    if not store.csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(store.csv_path, dtype=str).fillna("")


def load_opt_out_frame() -> pd.DataFrame:
    path = settings.path(settings.opt_out_csv)
    if not path.exists():
        return pd.DataFrame(columns=["identifier", "reason", "created_at"])
    return pd.read_csv(path, dtype=str).fillna("")


def snapshot() -> dict[str, Any]:
    store = LeadStore()
    outreach_logger = OutreachLogger()
    connector_logger = ConnectorLogger()
    queue = QueueManager()
    outreach_metrics = outreach_logger.metrics()
    connector_summary = connector_logger.summary()
    rate_limits = {
        channel: {
            "remaining": RateLimiter(channel, daily_max).remaining(),
            "daily_max": daily_max,
        }
        for channel, daily_max in {
            "linkedin": settings.linkedin_daily_max,
            "instagram": settings.instagram_daily_max,
            "email": settings.email_daily_max,
            "whatsapp": settings.whatsapp_daily_max,
        }.items()
    }
    sessions = settings.path(settings.session_dir)
    session_files = sorted(p.name for p in sessions.glob("*.json")) if sessions.exists() else []
    return {
        "lead_stats": store.stats(),
        "outreach_metrics": outreach_metrics,
        "connector_summary": connector_summary,
        "queue_size": queue.queue_size(),
        "processed": queue.processed_count(),
        "failed_pending": queue.failed_count(),
        "rate_limits": rate_limits,
        "session_files": session_files,
        "paths": {
            "scraper_output": str(settings.path(settings.scraper_output_csv)),
            "scraper_instagram_output": str(settings.path(settings.scraper_instagram_output_csv))
            if (settings.scraper_instagram_output_csv or "").strip()
            else "",
            "outreach_store": str(store.csv_path),
            "queue_file": str(settings.path(settings.connector_queue_path)),
            "log_dir": str(settings.path(settings.log_dir)),
            "app_db": str(settings.path(settings.app_db_path)),
        },
    }


def scraper_subprocess_timeout_seconds() -> int:
    return max(600, int(getattr(settings, "scraper_dashboard_subprocess_timeout_seconds", 14400)))


def _run_python(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    effective = timeout if timeout is not None else scraper_subprocess_timeout_seconds()
    return subprocess.run(
        [sys.executable, *command],
        cwd=str(settings.project_root),
        capture_output=True,
        text=True,
        timeout=effective,
        check=False,
    )


def _run_python_stream_stderr(
    command: list[str],
    *,
    on_progress: Callable[[dict[str, Any]], None],
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    effective = timeout if timeout is not None else scraper_subprocess_timeout_seconds()
    """Run Python subprocess; ``on_progress`` is invoked on the **calling thread** (Streamlit-safe)."""
    proc = subprocess.Popen(
        [sys.executable, "-u", *command],
        cwd=str(settings.project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    stderr_chunks: list[str] = []
    progress_q: queue.Queue[dict[str, Any]] = queue.Queue()
    prefix = "SCRAPER_PROGRESS:"

    def pump_stderr() -> None:
        assert proc.stderr is not None
        try:
            for line in proc.stderr:
                stderr_chunks.append(line)
                stripped = line.strip()
                if stripped.startswith(prefix):
                    try:
                        progress_q.put(json.loads(stripped[len(prefix) :]))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    th = threading.Thread(target=pump_stderr, daemon=True)
    th.start()
    assert proc.stdout is not None
    deadline = time.monotonic() + effective
    out: str = ""
    try:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd=command, timeout=effective)
            try:
                while True:
                    on_progress(progress_q.get_nowait())
                    time.sleep(0.02)
            except queue.Empty:
                pass
            time.sleep(0.05)

        th.join(timeout=30)
        try:
            while True:
                on_progress(progress_q.get_nowait())
                time.sleep(0.02)
        except queue.Empty:
            pass

        out = proc.stdout.read() or ""
        proc.wait(timeout=5)
    finally:
        if th.is_alive():
            th.join(timeout=2)
    err = "".join(stderr_chunks)
    return subprocess.CompletedProcess(
        args=[sys.executable, "-u", *command],
        returncode=int(proc.returncode) if proc.returncode is not None else 0,
        stdout=out,
        stderr=err,
    )


def run_web_scraper_isolated(**kwargs: Any) -> ScraperRunResult:
    """Google → sites web (commande scraper web-run)."""
    try:
        from workers.dashboard_queue import run_scraper_via_queue, scraper_queue_available

        if scraper_queue_available() and kwargs.get("on_progress") is None:
            return run_scraper_via_queue(app="web", **kwargs)
    except Exception:
        pass
    on_progress = kwargs.pop("on_progress", None)
    mode = str(kwargs.get("mode", "keyword"))
    query = str(kwargs.get("query", "")).strip()
    limit = int(kwargs.get("limit", 10))
    append = bool(kwargs.get("append", True))
    include_location = str(kwargs.get("include_location", "") or "").strip()
    exclude_location = kwargs.get("exclude_location")
    search_provider = str(kwargs.get("search_provider", "") or "").strip()

    command = [
        "scraper.py",
        "web-run",
        "--mode",
        mode,
        "--limit",
        str(limit),
        "--json",
    ]
    if query:
        command.extend(["--query", query])
    if include_location:
        command.extend(["--include-location", include_location])
    if exclude_location is not None:
        command.extend(["--exclude-location", str(exclude_location)])
    if search_provider:
        command.extend(["--search-provider", search_provider])
    if not append:
        command.append("--replace")

    try:
        if on_progress is not None:
            completed = _run_python_stream_stderr(command, on_progress=on_progress)
        else:
            completed = _run_python(command)
    except subprocess.TimeoutExpired:
        mins = scraper_subprocess_timeout_seconds() // 60
        return ScraperRunResult(
            written=0,
            output_path=str(resolve_scraper_csv_path("web")),
            mode=mode,
            app="web",
            query=query,
            error=f"Délai maximum dépassé ({mins} min). Réduisez --limit ou la requête Google.",
        )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
            return ScraperRunResult(**payload)
        except json.JSONDecodeError:
            pass
    if completed.returncode != 0:
        return ScraperRunResult(
            written=0,
            output_path=str(resolve_scraper_csv_path("web")),
            mode=mode,
            app="web",
            query=query,
            error=stderr or stdout or f"web-run terminé avec code {completed.returncode}",
        )
    return ScraperRunResult(
        written=0,
        output_path=str(resolve_scraper_csv_path("web")),
        mode=mode,
        app="web",
        query=query,
        error="Réponse web-run invalide (JSON attendu).",
    )


def run_scraper_isolated(**kwargs: Any) -> ScraperRunResult:
    try:
        from workers.dashboard_queue import run_scraper_via_queue, scraper_queue_available

        if scraper_queue_available() and kwargs.get("on_progress") is None:
            return run_scraper_via_queue(**kwargs)
    except Exception:
        pass
    on_progress = kwargs.pop("on_progress", None)
    mode = str(kwargs.get("mode", "keyword"))
    app = str(kwargs.get("app", "linkedin"))
    query = str(kwargs.get("query", "")).strip()
    limit = int(kwargs.get("limit", 10))
    append = bool(kwargs.get("append", True))
    linkedin_scopes = [str(scope) for scope in (kwargs.get("linkedin_scopes") or []) if str(scope).strip()]
    include_location = str(kwargs.get("include_location", "") or "").strip()
    exclude_location = kwargs.get("exclude_location")

    command = [
        "scraper.py",
        "run",
        "--mode",
        mode,
        "--app",
        app,
        "--limit",
        str(limit),
        "--json",
    ]
    if query:
        command.extend(["--query", query])
    if include_location:
        command.extend(["--include-location", include_location])
    if exclude_location is not None:
        command.extend(["--exclude-location", str(exclude_location)])
    for scope in linkedin_scopes:
        command.extend(["--linkedin-scope", scope])
    if not append:
        command.append("--replace")

    try:
        if on_progress is not None:
            completed = _run_python_stream_stderr(command, on_progress=on_progress)
        else:
            completed = _run_python(command)
    except subprocess.TimeoutExpired:
        mins = scraper_subprocess_timeout_seconds() // 60
        return ScraperRunResult(
            written=0,
            output_path=str(resolve_scraper_csv_path(app)),
            mode=mode,
            app=app,
            query=query,
            error=(
                f"Délai maximum dépassé ({mins} min). Réduisez les mots-clés (5–8 max), "
                f"une seule catégorie (personnes OU entreprises), ou augmentez "
                f"SCRAPER_DASHBOARD_SUBPROCESS_TIMEOUT_SECONDS dans .env."
            ),
        )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
            return ScraperRunResult(**payload)
        except json.JSONDecodeError:
            pass

    if "TimeoutExpired" in (stderr or "") or "timed out after" in (stderr or ""):
        mins = scraper_subprocess_timeout_seconds() // 60
        message = (
            f"Délai maximum dépassé ({mins} min). Réduisez les mots-clés (5–8 max), "
            f"une seule catégorie (personnes OU entreprises), ou augmentez "
            f"SCRAPER_DASHBOARD_SUBPROCESS_TIMEOUT_SECONDS dans .env."
        )
    else:
        message = stderr or stdout or "Échec du scraper."
    return ScraperRunResult(
        written=0,
        output_path=str(resolve_scraper_csv_path(app)),
        mode=mode,
        app=app,
        query=query,
        error=message,
    )


def import_session_isolated(channel: str, browser_source: str) -> str:
    completed = _run_python(
        ["outreach.py", "login", channel, "--from-browser", browser_source],
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Import échoué.").strip())
    return (completed.stdout or "Session importée.").strip()


def run_pipeline_isolated(
    *,
    source: str,
    retry_failed: bool,
    per_channel_limit: int | None,
    run_scraper_step: bool,
    run_outreach: bool,
) -> dict[str, Any]:
    command = ["run.py", "run", "--source", source]
    if not run_scraper_step:
        command.append("--no-scraper")
    if not run_outreach:
        command.append("--no-outreach")
    if retry_failed:
        command.append("--retry")
    if per_channel_limit is not None:
        command.extend(["--limit", str(per_channel_limit)])
    completed = _run_python(command)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Pipeline échoué.").strip())
    return json.loads(completed.stdout)


def run_email_campaign_isolated(
    *,
    limit: int | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    """Importe le CSV scraper puis envoie les e-mails personnalisés (canal email)."""
    from orchestrator.email_campaign import run_email_campaign_from_scraper_csv

    effective_limit = limit
    result = run_email_campaign_from_scraper_csv(
        limit=effective_limit,
        retry_failed=retry_failed,
    )
    return result.to_dict()


def run_channel_isolated(channel: str, *, limit: int) -> int:
    command = ["outreach.py", "run", channel, "--limit", str(limit), "--headless"]
    completed = _run_python(command)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Outreach échoué.").strip())
    for line in reversed(completed.stdout.splitlines()):
        if "Sent" in line:
            parts = line.strip().split()
            if parts and parts[0] == "Sent":
                return int(parts[1])
    return 0
