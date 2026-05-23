"""Outbox pattern — events métier (E0/E2)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings


def emit_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    idempotency_key: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Persiste outbox + tente publish immédiat sur Redis Stream."""
    event_id = str(uuid.uuid4())
    tid = tenant_id or settings.default_tenant_id
    envelope = {
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tid,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "idempotency_key": idempotency_key,
        "payload": payload,
        "version": 1,
    }
    _persist_outbox(envelope)
    _publish_stream(envelope)
    return event_id


def _persist_outbox(envelope: dict[str, Any]) -> None:
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outbox_events (id, tenant_id, event_type, payload, trace_id, idempotency_key)
                    VALUES (%s::uuid, %s::uuid, %s, %s::jsonb, %s, %s)
                    """,
                    (
                        envelope["event_id"],
                        envelope["tenant_id"],
                        envelope["event_type"],
                        json.dumps(envelope),
                        envelope.get("trace_id"),
                        envelope.get("idempotency_key"),
                    ),
                )
            return
    except Exception:
        pass
    from storage.database import Database

    db = Database()
    db.migrate()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO outbox_events (id, tenant_id, event_type, payload, trace_id, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope["event_id"],
                envelope["tenant_id"],
                envelope["event_type"],
                json.dumps(envelope),
                envelope.get("trace_id"),
                envelope.get("idempotency_key"),
                envelope["occurred_at"],
            ),
        )


def _publish_stream(envelope: dict[str, Any]) -> None:
    try:
        from services.events import EventBus

        EventBus().publish(envelope["event_type"], envelope)
    except Exception:
        pass
