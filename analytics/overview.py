"""Vue d'ensemble KPIs acquisition + content."""

from __future__ import annotations

from typing import Any

from config import settings
from content.store import ContentStore
from leads.store import LeadStore
from utils.outreach_logger import OutreachLogger


def acquisition_overview() -> dict[str, Any]:
    store = LeadStore()
    logger = OutreachLogger()
    return {
        "leads": store.stats(),
        "outreach": logger.metrics(),
    }


def content_overview() -> dict[str, Any]:
    cstore = ContentStore()
    tenant_id = cstore.ensure_default_tenant()
    drafts = len(cstore.list_drafts(limit=500))
    scheduled = len(cstore.list_posts(status="scheduled", limit=500))
    published = len(cstore.list_posts(status="published", limit=500))
    return {
        "drafts": drafts,
        "scheduled": scheduled,
        "published": published,
        "published_today": cstore.posts_published_today_count(),
        "max_posts_per_day": int(getattr(settings, "content_max_posts_per_day", 2)),
    }


def unified_overview() -> dict[str, Any]:
    return {
        "acquisition": acquisition_overview(),
        "content": content_overview(),
        "platform": "AI Acquisition OS",
    }
