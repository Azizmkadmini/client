"""Comptes LinkedIn multi-rôles par tenant."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from storage.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LinkedInAccountStore:
    def __init__(self) -> None:
        self.db = Database()
        self.db.migrate()

    def list_accounts(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        tid = tenant_id or settings.default_tenant_id
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM linkedin_accounts WHERE tenant_id = ? ORDER BY label",
                (tid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create(
        self,
        label: str,
        *,
        tenant_id: str | None = None,
        scrape: bool = False,
        outreach: bool = False,
        publish: bool = False,
        profile_url: str = "",
    ) -> dict[str, Any]:
        tid = tenant_id or settings.default_tenant_id
        aid = str(uuid.uuid4())
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO linkedin_accounts (
                    id, tenant_id, label, profile_url,
                    purpose_scrape, purpose_outreach, purpose_publish,
                    health_score, max_posts_per_day, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 100, ?, ?, ?)
                """,
                (
                    aid,
                    tid,
                    label,
                    profile_url,
                    int(scrape),
                    int(outreach),
                    int(publish),
                    int(getattr(settings, "content_max_posts_per_day", 2)),
                    now,
                    now,
                ),
            )
        return self.get(aid)

    def get(self, account_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM linkedin_accounts WHERE id = ?", (account_id,)
            ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return dict(row)

    def update_health(self, account_id: str, score: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE linkedin_accounts SET health_score = ?, updated_at = ? WHERE id = ?",
                (score, _now(), account_id),
            )

    def disable(self, account_id: str, *, reason: str = "") -> None:
        now = _now()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE linkedin_accounts SET disabled_at = ?, updated_at = ? WHERE id = ?",
                (now, now, account_id),
            )

    def update_proxy(self, account_id: str, proxy_url: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE linkedin_accounts SET proxy_url = ?, updated_at = ? WHERE id = ?",
                (proxy_url, _now(), account_id),
            )
