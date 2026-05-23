"""Pool de comptes LinkedIn — sélection par rôle, santé, proxy (Phase 4)."""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pathlib import Path

from config import settings
from content.accounts import LinkedInAccountStore

Purpose = Literal["scrape", "outreach", "publish"]

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "rate_limits.yaml"


def _health_threshold() -> float:
    if _CONFIG.exists():
        cfg = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        return float(cfg.get("account_health", {}).get("disable_below", 20))
    return 20.0


class LinkedInAccountPool:
    def __init__(self, tenant_id: str | None = None) -> None:
        self.tenant_id = tenant_id or settings.default_tenant_id
        self.store = LinkedInAccountStore()

    def list_active(self, purpose: Purpose) -> list[dict[str, Any]]:
        col = f"purpose_{purpose}"
        threshold = _health_threshold()
        out: list[dict[str, Any]] = []
        for acc in self.store.list_accounts(self.tenant_id):
            if acc.get("disabled_at"):
                continue
            if float(acc.get("health_score") or 0) < threshold:
                continue
            if acc.get(col) in (1, True, "1"):
                out.append(acc)
        return sorted(out, key=lambda a: float(a.get("health_score") or 0), reverse=True)

    def pick(self, purpose: Purpose) -> dict[str, Any] | None:
        active = self.list_active(purpose)
        if not active:
            return None
        # round-robin simple via health_score ordering (best first)
        return active[0]

    def record_failure(self, account_id: str, *, delta: float = 15.0) -> None:
        acc = self.store.get(account_id)
        score = max(0.0, float(acc.get("health_score", 100)) - delta)
        self.store.update_health(account_id, score)
        if score < _health_threshold():
            self.store.disable(account_id, reason="health_below_threshold")

    def record_success(self, account_id: str, *, delta: float = 2.0) -> None:
        acc = self.store.get(account_id)
        score = min(100.0, float(acc.get("health_score", 50)) + delta)
        self.store.update_health(account_id, score)
