"""Gestion proxies par compte LinkedIn (E1)."""

from __future__ import annotations

import time
from typing import Any

from config import settings


class ProxyManager:
    def __init__(self) -> None:
        self._health: dict[str, float] = {}

    def get_proxy(self, account_id: str) -> str | None:
        from content.accounts import LinkedInAccountStore

        try:
            acc = LinkedInAccountStore().get(account_id)
            url = (acc.get("proxy_url") or "").strip()
            if url and self._is_healthy(account_id):
                return url
        except KeyError:
            pass
        return None

    def mark_failure(self, account_id: str) -> None:
        self._health[account_id] = time.time() - 3600

    def mark_success(self, account_id: str) -> None:
        self._health[account_id] = time.time()

    def _is_healthy(self, account_id: str) -> bool:
        last = self._health.get(account_id, 0)
        return (time.time() - last) < float(getattr(settings, "proxy_cooldown_seconds", 300))

    def list_pool(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        from content.accounts import LinkedInAccountStore

        out = []
        for acc in LinkedInAccountStore().list_accounts(tenant_id):
            if acc.get("proxy_url"):
                out.append(
                    {
                        "account_id": acc["id"],
                        "proxy_url": acc["proxy_url"][:20] + "...",
                        "healthy": self._is_healthy(acc["id"]),
                    }
                )
        return out
