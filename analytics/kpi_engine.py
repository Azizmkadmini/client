"""KPI engine — agrégations (E2)."""

from __future__ import annotations

from typing import Any

from analytics.overview import unified_overview
from config import settings


def compute_kpis(tenant_id: str | None = None) -> dict[str, Any]:
    base = unified_overview()
    kpis: dict[str, Any] = {
        "overview": base,
        "tenant_id": tenant_id or settings.default_tenant_id,
    }
    try:
        from services.rate_limit_engine import CentralRateLimiter

        kpis["rate_limits"] = {
            ch: {
                "remaining": CentralRateLimiter(ch, tenant_id=tenant_id).remaining(),
            }
            for ch in ("linkedin", "email", "content_publish")
        }
    except Exception:
        pass
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured() and tenant_id:
            with pg_cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, COUNT(*) AS c
                    FROM analytics_events
                    WHERE tenant_id = %s::uuid AND occurred_at > NOW() - INTERVAL '7 days'
                    GROUP BY event_type
                    """,
                    (tenant_id,),
                )
                kpis["events_7d"] = {r["event_type"]: int(r["c"]) for r in cur.fetchall()}
    except Exception:
        kpis["events_7d"] = {}
    return kpis
