"""API Analytics — vue unifiée acquisition + content."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from analytics.overview import unified_overview
from api.deps import AuthContext
from leads.store import LeadStore

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def analytics_overview(ctx: AuthContext) -> dict[str, Any]:
    return unified_overview()


@router.get("/attribution")
def attribution(ctx: AuthContext) -> dict[str, Any]:
    store = LeadStore()
    leads = store.all()
    from_content = [
        l for l in leads
        if "linkedin_content" in (l.notes or "").lower() or "content:" in (l.notes or "").lower()
    ]
    return {
        "total_leads": len(leads),
        "attributed_to_content": len(from_content),
        "sample": [l.model_dump() for l in from_content[:10]],
    }
