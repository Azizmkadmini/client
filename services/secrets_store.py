"""Stockage secrets chiffrés par tenant (E0)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from services.crypto import decrypt_text, encrypt_text


def store_secret(tenant_id: str, secret_type: str, plaintext: str) -> None:
    enc = encrypt_text(plaintext)
    from storage.database import Database

    now = datetime.now(timezone.utc).isoformat()
    sid = str(uuid.uuid4())
    with Database().connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO encrypted_secrets (id, tenant_id, secret_type, ciphertext, created_at, updated_at)
            VALUES (?, ?, ?, ?, COALESCE(
                (SELECT created_at FROM encrypted_secrets WHERE tenant_id = ? AND secret_type = ?), ?
            ), ?)
            """,
            (sid, tenant_id, secret_type, enc, tenant_id, secret_type, now, now),
        )


def load_secret(tenant_id: str, secret_type: str) -> str | None:
    from storage.database import Database

    with Database().connect() as conn:
        row = conn.execute(
            "SELECT ciphertext FROM encrypted_secrets WHERE tenant_id = ? AND secret_type = ?",
            (tenant_id, secret_type),
        ).fetchone()
    if not row:
        return None
    try:
        return decrypt_text(row["ciphertext"])
    except Exception:
        return None
