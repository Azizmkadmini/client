"""Audit logs enterprise (E3)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings


def log_audit(
    action: str,
    *,
    tenant_id: str | None = None,
    actor_user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    aid = str(uuid.uuid4())
    tid = tenant_id or settings.default_tenant_id
    meta = metadata or {}
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_logs (id, tenant_id, actor_user_id, action, resource_type, resource_id, metadata)
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (aid, tid, actor_user_id, action, resource_type, resource_id, json.dumps(meta)),
                )
            return aid
    except Exception:
        pass
    from storage.database import Database

    db = Database()
    db.migrate()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (id, tenant_id, actor_user_id, action, resource_type, resource_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                tid,
                actor_user_id,
                action,
                resource_type,
                resource_id,
                json.dumps(meta),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return aid
