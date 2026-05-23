"""
Scheduler Content OS — publie les posts planifiés + sync métriques.

Usage (cron / Planificateur Windows toutes les 15 min) :
  python scripts/content_scheduler.py
  python scripts/content_scheduler.py --sync-metrics
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content.analytics.sync import sync_all_published
from content.store import ContentStore
from workers.content_jobs import execute_content_job
from workers.queue import ScraperJob


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduler publication Content OS")
    parser.add_argument("--sync-metrics", action="store_true")
    parser.add_argument("--max", type=int, default=2)
    args = parser.parse_args()

    store = ContentStore()
    due = store.list_due_scheduled_posts()
    published = 0
    for post in due[: args.max]:
        job = ScraperJob(job_type="content-publish", payload={"post_id": post["id"]})
        result = execute_content_job(job)
        print(f"Publish {post['id']}: {result}")
        if result.get("success"):
            published += 1

    if args.sync_metrics:
        synced = sync_all_published()
        print(f"Métriques synchronisées: {len(synced)} posts")

    print(f"Terminé — {published} publication(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
