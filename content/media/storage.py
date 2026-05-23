"""Stockage médias — local (dev) ou Cloudflare R2 (prod)."""

from __future__ import annotations

import uuid
from pathlib import Path

from config import settings


def save_media_local(data: bytes, *, mime_type: str, draft_id: str | None = None) -> dict[str, str]:
    root = settings.path("data/content_media")
    root.mkdir(parents=True, exist_ok=True)
    ext = ".png" if "png" in mime_type else ".jpg" if "jpeg" in mime_type else ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    path = root / name
    path.write_bytes(data)
    from content.store import ContentStore

    store = ContentStore()
    tenant_id = store.ensure_default_tenant()
    mid = str(uuid.uuid4())
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with store.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO content_media (id, tenant_id, draft_id, local_path, mime_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mid, tenant_id, draft_id, str(path), mime_type, now),
        )
    return {"media_id": mid, "local_path": str(path), "url": f"/media/{name}"}


def r2_configured() -> bool:
    return bool(
        getattr(settings, "r2_access_key_id", "")
        and getattr(settings, "r2_secret_access_key", "")
        and getattr(settings, "r2_bucket", "")
    )
