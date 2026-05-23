#!/usr/bin/env python3
"""VACUUM ANALYZE tables chaudes — à lancer en cron basse charge."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TABLES = (
    "leads",
    "scraper_jobs",
    "domain_events",
    "content_posts",
    "outbox_events",
    "usage_events",
)


def main() -> None:
    from storage.postgres import postgres_configured

    if not postgres_configured():
        print("Postgres non configuré — skip")
        return
    from storage.postgres_backend import pg_cursor

    with pg_cursor() as cur:
        for table in TABLES:
            cur.execute(f"VACUUM ANALYZE {table}")
            print(f"VACUUM ANALYZE {table} OK")


if __name__ == "__main__":
    main()
