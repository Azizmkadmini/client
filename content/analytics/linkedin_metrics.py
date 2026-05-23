"""Sync métriques LinkedIn — OAuth API ou simulation."""

from __future__ import annotations

import random
import urllib.parse
from typing import Any

from config import settings
from content.analytics.sync import sync_post_metrics
from content.store import ContentStore


def oauth_configured() -> bool:
    return bool(
        getattr(settings, "oauth_linkedin_client_id", "")
        and getattr(settings, "oauth_linkedin_client_secret", "")
    )


def fetch_metrics_from_api(post_urn: str, access_token: str) -> dict[str, Any] | None:
    """LinkedIn socialActions / organizationalEntityShareStatistics (si scopes OK)."""
    import httpx

    urn = post_urn if post_urn.startswith("urn:") else f"urn:li:share:{post_urn}"
    headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"}
    try:
        resp = httpx.get(
            f"https://api.linkedin.com/v2/socialActions/{urllib.parse.quote(urn, safe='')}",
            headers=headers,
            timeout=25.0,
        )
        if resp.status_code == 404:
            stats = httpx.get(
                "https://api.linkedin.com/v2/organizationalEntityShareStatistics",
                params={"q": "organizationalEntity", "organizationalEntity": urn},
                headers=headers,
                timeout=25.0,
            )
            if stats.status_code >= 400:
                return None
            elements = stats.json().get("elements", [{}])
            el = elements[0] if elements else {}
            ts = el.get("totalShareStatistics", el)
            return {
                "impressions": int(ts.get("impressionCount", ts.get("impressions", 0)) or 0),
                "likes": int(ts.get("likeCount", ts.get("likes", 0)) or 0),
                "comments": int(ts.get("commentCount", ts.get("comments", 0)) or 0),
                "saves": int(ts.get("saveCount", 0) or 0),
                "profile_visits": int(ts.get("clickCount", 0) or 0),
                "dm_conversions": 0,
            }
        data = resp.json()
        likes = int(data.get("likesSummary", {}).get("totalLikes", 0) or 0)
        comments = int(data.get("commentsSummary", {}).get("totalFirstLevelComments", 0) or 0)
        return {
            "impressions": int(data.get("impressionCount", 0) or 0),
            "likes": likes,
            "comments": comments,
            "saves": 0,
            "profile_visits": 0,
            "dm_conversions": 0,
        }
    except Exception:
        return None


def sync_post_metrics_smart(post_id: str) -> dict[str, Any]:
    store = ContentStore()
    post = store.get_post(post_id)
    if oauth_configured() and post.get("linkedin_post_urn"):
        token = _load_oauth_token()
        if token:
            api_data = fetch_metrics_from_api(post["linkedin_post_urn"], token)
            if api_data:
                return store.record_metrics(post_id, api_data)
    return sync_post_metrics(post_id, simulate=True)


def _load_oauth_token() -> str | None:
    import json

    from services.secrets_store import load_secret

    raw = load_secret(settings.default_tenant_id, "linkedin_oauth")
    if raw:
        try:
            return json.loads(raw).get("access_token")
        except Exception:
            pass
    path = settings.path("data/oauth_linkedin.json")
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("enc"):
            from services.crypto import decrypt_text

            data = json.loads(decrypt_text(data["enc"]))
        return data.get("access_token")
    except Exception:
        return None
