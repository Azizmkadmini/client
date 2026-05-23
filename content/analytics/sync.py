"""Synchronisation métriques posts (API OAuth futur ; estimation locale pour l'instant)."""

from __future__ import annotations

import random
from typing import Any

from content.store import ContentStore


def sync_post_metrics(post_id: str, *, simulate: bool = True) -> dict[str, Any]:
    """
    Enregistre un snapshot métriques. ``simulate=True`` génère des valeurs plausibles
    jusqu'à branchement API LinkedIn Marketing.
    """
    store = ContentStore()
    post = store.get_post(post_id)
    if post["status"] != "published":
        return {"skipped": True, "reason": "post not published"}
    if simulate:
        base = random.randint(800, 12000)
        metrics = {
            "impressions": base,
            "likes": random.randint(5, max(6, base // 80)),
            "comments": random.randint(0, max(1, base // 200)),
            "saves": random.randint(0, max(1, base // 150)),
            "profile_visits": random.randint(2, max(3, base // 50)),
            "dm_conversions": random.randint(0, 2),
        }
    else:
        metrics = {}
    return store.record_metrics(post_id, metrics)


def sync_all_published(*, limit: int = 50) -> list[dict[str, Any]]:
    store = ContentStore()
    posts = store.list_posts(status="published", limit=limit)
    return [sync_post_metrics(p["id"]) for p in posts]
