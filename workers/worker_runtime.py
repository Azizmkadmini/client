"""
Runtime worker — heartbeat, shutdown gracieux, timeout jobs, ack/retry/DLQ.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable

from config import settings
from workers.queue import JobQueue, ScraperJob

_shutdown = threading.Event()
_heartbeat_stop = threading.Event()


def request_shutdown(*_args) -> None:
    _shutdown.set()
    _heartbeat_stop.set()
    print("[worker] shutdown demandé — fin du job en cours…", file=sys.stderr)


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_shutdown)


def heartbeat_loop(worker_id: str, queue: JobQueue) -> None:
    """TTL clé Redis — détecte workers morts."""
    if not queue.enabled:
        return
    client = queue._client()
    key = f"worker:heartbeat:{worker_id}"
    ttl = int(getattr(settings, "worker_heartbeat_ttl_seconds", 60))
    while not _heartbeat_stop.wait(15):
        try:
            client.setex(key, ttl, str(time.time()))
        except Exception:
            pass


def execute_with_timeout(fn: Callable[[], dict], timeout: int | None = None) -> dict:
    timeout = timeout or int(getattr(settings, "worker_job_timeout_seconds", 3600))
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout:
            return {"success": False, "error": f"job_timeout_{timeout}s", "timeout": True}


def process_job(
    queue: JobQueue,
    job: ScraperJob,
    execute_fn: Callable[[ScraperJob], dict],
    *,
    success_fn: Callable[[ScraperJob, dict], bool] | None = None,
) -> None:
    """Exécute un job, ack ou retry/DLQ."""
    if success_fn is None:
        success_fn = _default_success

    def _run() -> dict:
        return execute_fn(job)

    result = execute_with_timeout(_run)
    ok = success_fn(job, result)

    if any(x in job.job_type for x in ("linkedin", "content-publish", "outreach")):
        from services.linkedin_risk import record_outcome

        record_outcome(
            tenant_id=job.payload.get("tenant_id"),
            account_id=job.payload.get("account_id"),
            success=ok,
            error=job.error or result.get("error"),
        )

    if ok:
        job.status = "done"
        job.result = result
        job.error = None
        queue.ack(job)
    else:
        job.result = result
        job.error = (result.get("stderr") or result.get("error") or "échec")[:2000]
        if job.attempts + 1 < job.max_attempts and not result.get("timeout"):
            queue.requeue(job)
            print(f"[worker] {job.job_id} retry {job.attempts}/{job.max_attempts}")
        else:
            job.status = "failed"
            queue.move_to_dlq(job)
    job.finished_at = time.time()
    queue.save(job)


def _default_success(job: ScraperJob, result: dict) -> bool:
    if job.job_type.startswith("outreach-"):
        return int(result.get("returncode", 0)) == 0
    if job.job_type.startswith("content-"):
        if "returncode" in result:
            return int(result.get("returncode", 0)) == 0
        return bool(result.get("success", True)) and not result.get("error")
    return int(result.get("returncode", 0)) == 0


def _linkedin_risk_gate(queue: JobQueue, job: ScraperJob) -> bool:
    if not any(x in job.job_type for x in ("linkedin", "content-publish", "outreach")):
        return True
    from services.linkedin_risk import assess, wait_if_needed

    channel = "linkedin" if "linkedin" in job.job_type else "content_publish"
    risk = assess(channel, operation=job.job_type, tenant_id=job.payload.get("tenant_id"))
    if not risk.allowed:
        queue.requeue(job, delay_seconds=int(min(risk.delay_seconds, 3600)))
        print(f"[worker] {job.job_id} throttled risk={risk.risk_score}")
        return False
    wait_if_needed(risk)
    return True


def run_loop(
    queue: JobQueue,
    execute_fn: Callable[[ScraperJob], dict],
    *,
    worker_id: str = "main",
    poll_seconds: float = 2.0,
    success_fn: Callable[[ScraperJob, dict], bool] | None = None,
) -> None:
    install_signal_handlers()
    hb = threading.Thread(target=heartbeat_loop, args=(worker_id, queue), daemon=True)
    hb.start()

    print(f"[worker:{worker_id}] démarré — Ctrl+C pour arrêter.")
    while not _shutdown.is_set():
        queue.promote_delayed()
        recovered = queue.recover_stale()
        if recovered:
            print(f"[worker:{worker_id}] recovered {recovered} stale jobs")
        job = queue.claim(timeout=2)
        if job is None:
            time.sleep(poll_seconds)
            continue
        if not _linkedin_risk_gate(queue, job):
            continue
        try:
            process_job(queue, job, execute_fn, success_fn=success_fn)
            print(f"[worker:{worker_id}] {job.job_id} {job.job_type} → {job.status}")
        except Exception as exc:
            job.error = str(exc)
            if job.attempts + 1 < job.max_attempts:
                queue.requeue(job)
            else:
                job.status = "failed"
                queue.move_to_dlq(job)
            job.finished_at = time.time()
            queue.save(job)
            print(f"[worker:{worker_id}] {job.job_id} exception → {job.error[:120]}")

    _heartbeat_stop.set()
    print(f"[worker:{worker_id}] arrêt propre.", file=sys.stderr)
