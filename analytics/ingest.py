"""Ingestion événements analytics (E2)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings


def ingest_event(event_type: str, properties: dict[str, Any], *, tenant_id: str | None = None) -> str:
    eid = str(uuid.uuid4())
    tid = tenant_id or settings.default_tenant_id
    from services.outbox import emit_event

    emit_event(event_type, properties, tenant_id=tid, idempotency_key=eid)
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analytics_events (id, tenant_id, event_type, properties, occurred_at)
                    VALUES (%s::uuid, %s::uuid, %s, %s::jsonb, NOW())
                    """,
                    (eid, tid, event_type, json.dumps(properties)),
                )
            return eid
    except Exception:
        pass
    from storage.database import Database

    with Database().connect() as conn:
        conn.execute(
            """
            INSERT INTO analytics_events (id, tenant_id, event_type, properties, occurred_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (eid, tid, event_type, json.dumps(properties), datetime.now(timezone.utc).isoformat()),
        )
    return eid
