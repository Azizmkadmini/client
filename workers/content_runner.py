"""Worker Redis — jobs Content OS : python -m workers.content_runner"""

from __future__ import annotations

import argparse
import sys

from utils.logging_config import configure_logging
from workers.content_jobs import execute_content_job
from workers.queue import CONTENT_QUEUE, JobQueue, ScraperJob
from workers.worker_runtime import run_loop

configure_logging()


class ContentJobQueue(JobQueue):
    """File Content OS — même moteur BRPOPLPUSH / ack / DLQ."""

    def __init__(self, redis_url: str | None = None) -> None:
        super().__init__(redis_url, names=CONTENT_QUEUE)

    def enqueue_content(self, job_type: str, payload: dict, **kwargs) -> ScraperJob:
        return self.enqueue(job_type, payload, **kwargs)

    def dequeue_content(self, timeout: int = 5) -> ScraperJob | None:
        return self.claim(timeout=timeout)

    def save_content(self, job: ScraperJob) -> None:
        self.save(job)


def run_once() -> bool:
    from workers.worker_runtime import process_job

    queue = ContentJobQueue()
    if not queue.enabled:
        print("REDIS_URL manquant.", file=sys.stderr)
        return False
    queue.promote_delayed()
    job = queue.claim(timeout=2)
    if job is None:
        return False
    process_job(queue, job, execute_content_job)
    print(f"[content-worker] {job.job_id} {job.job_type} → {job.status}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker Content OS")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default="content")
    args = parser.parse_args()
    queue = ContentJobQueue()
    if not queue.enabled:
        print("REDIS_URL manquant.", file=sys.stderr)
        sys.exit(1)
    if args.once:
        run_once()
        return
    run_loop(queue, execute_content_job, worker_id=args.worker_id)


if __name__ == "__main__":
    main()
