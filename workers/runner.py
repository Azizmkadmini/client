"""Worker Redis acquisition + outreach : python -m workers.runner"""

from __future__ import annotations

import argparse
import sys

from utils.logging_config import configure_logging
from workers.jobs import execute_job
from workers.outreach_jobs import execute_outreach_job
from workers.queue import JobQueue, ScraperJob
from workers.worker_runtime import run_loop

configure_logging()


def _execute(job: ScraperJob) -> dict:
    if job.job_type.startswith("content-"):
        from workers.content_jobs import execute_content_job

        return execute_content_job(job)
    if job.job_type.startswith("outreach-"):
        return execute_outreach_job(job)
    return execute_job(job)


def run_once() -> bool:
    queue = JobQueue()
    if not queue.enabled:
        print("REDIS_URL manquant — worker arrêté.", file=sys.stderr)
        return False
    from workers.worker_runtime import _linkedin_risk_gate, process_job

    queue.promote_delayed()
    queue.recover_stale()
    job = queue.claim(timeout=2)
    if job is None:
        return False
    if not _linkedin_risk_gate(queue, job):
        return True
    process_job(queue, job, _execute)
    print(f"[worker] {job.job_id} {job.job_type} → {job.status}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker acquisition/outreach (Redis)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--worker-id", default="acquisition")
    args = parser.parse_args()
    queue = JobQueue()
    if not queue.enabled:
        print("REDIS_URL manquant.", file=sys.stderr)
        sys.exit(1)
    if args.once:
        run_once()
        return
    run_loop(queue, _execute, worker_id=args.worker_id, poll_seconds=args.poll)


if __name__ == "__main__":
    main()
