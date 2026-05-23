"""Relay outbox → Redis Streams (E0/E2)."""

from __future__ import annotations

import json
import time

from services.events import EventBus


def relay_once(limit: int = 50) -> int:
    n = 0
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, event_type, payload FROM outbox_events
                    WHERE published_at IS NULL ORDER BY created_at LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
            bus = EventBus()
            for row in rows:
                data = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
                if bus.enabled:
                    bus.publish(row["event_type"], data)
                with pg_cursor() as cur:
                    cur.execute(
                        "UPDATE outbox_events SET published_at = NOW() WHERE id = %s::uuid",
                        (str(row["id"]),),
                    )
                n += 1
            return n
    except Exception:
        pass
    from storage.database import Database

    db = Database()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, event_type, payload FROM outbox_events WHERE published_at IS NULL LIMIT ?",
            (limit,),
        ).fetchall()
    bus = EventBus()
    for row in rows:
        data = json.loads(row["payload"])
        if bus.enabled:
            bus.publish(row["event_type"], data)
        with db.connect() as conn:
            conn.execute(
                "UPDATE outbox_events SET published_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
        n += 1
    return n


def run_loop(interval: float = 5.0) -> None:
    while True:
        relay_once()
        time.sleep(interval)


if __name__ == "__main__":
    run_loop()
