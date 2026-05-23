#!/usr/bin/env python3
"""Purge données anciennes — events, jobs scraper (cron quotidien)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings


def purge_domain_events(days: int) -> int:
    from storage.postgres import postgres_configured

    if not postgres_configured():
        return 0
    from storage.postgres_backend import pg_cursor

    with pg_cursor() as cur:
        cur.execute(
            "DELETE FROM domain_events WHERE created_at < NOW() - make_interval(days => %s)",
            (days,),
        )
        return cur.rowcount


def purge_scraper_jobs(days: int) -> int:
    from storage.postgres import postgres_configured

    if not postgres_configured():
        return 0
    from storage.postgres_backend import pg_cursor

    with pg_cursor() as cur:
        cur.execute(
            """
            DELETE FROM scraper_jobs
            WHERE finished_at IS NOT NULL
              AND finished_at < NOW() - make_interval(days => %s)
            """,
            (days,),
        )
        return cur.rowcount


def trim_redis_streams(maxlen: int) -> None:
    url = (settings.redis_url or "").strip()
    if not url:
        return
    import redis

    client = redis.from_url(url, decode_responses=True)
    for key in client.scan_iter("events:*", count=50):
        try:
            client.xtrim(key, maxlen=maxlen, approximate=True)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Retention / purge")
    parser.add_argument("--events-days", type=int, default=settings.retention_events_days)
    parser.add_argument("--jobs-days", type=int, default=settings.retention_scraper_jobs_days)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(f"Would purge events>{args.events_days}d jobs>{args.jobs_days}d")
        return
    ev = purge_domain_events(args.events_days)
    jobs = purge_scraper_jobs(args.jobs_days)
    trim_redis_streams(settings.redis_stream_maxlen)
    print(f"purged events={ev} scraper_jobs={jobs}")


if __name__ == "__main__":
    main()
