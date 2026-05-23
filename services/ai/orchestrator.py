"""AI Gateway — providers, cache, metering (E4)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from config import settings


def _cache_path(key: str) -> Path:
    d = settings.path("data/ai_cache")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def complete(
    prompt: str,
    *,
    job_type: str = "generic",
    tenant_id: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Point d'entrée unique génération texte."""
    tid = tenant_id or settings.default_tenant_id
    cache_key = hashlib.sha256(f"{tid}:{job_type}:{prompt}".encode()).hexdigest()[:32]
    cached = _cache_path(cache_key)
    if cached.exists():
        out = json.loads(cached.read_text(encoding="utf-8"))
        out["cached"] = True
        return out

    est_tokens = max(1, len(prompt) // 4)
    if not _budget_allows(tid, est_tokens):
        return {
            "text": f"[budget] Réponse template — quota IA atteint pour {job_type}",
            "provider": "template",
            "cached": False,
            "budget_limited": True,
        }

    provider = _route_provider(job_type, est_tokens, model)
    text, usage = _call_provider(provider, prompt, model=model, max_tokens=max_tokens)
    _record_usage(tid, model or provider, job_type, usage)
    result = {"text": text, "provider": provider, "cached": False}
    cached.write_text(json.dumps(result), encoding="utf-8")
    return result


def _route_provider(job_type: str, est_tokens: int, model: str | None) -> str:
    """Route vers modèle cheap si gros volume ou job simple."""
    configured = (settings.content_ai_provider or settings.ai_provider or "template").lower()
    if est_tokens > 3000:
        return "template"
    if job_type in ("hook", "cta") and settings.groq_api_key:
        return "groq"
    return configured


def _budget_allows(tenant_id: str, est_tokens: int) -> bool:
    cap = int(getattr(settings, "ai_daily_token_cap_per_tenant", 500_000) or 500_000)
    try:
        from storage.database import Database

        with Database().connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS t
                FROM ai_usage_events
                WHERE tenant_id = ? AND created_at > datetime('now', '-1 day')
                """,
                (tenant_id,),
            ).fetchone()
        used = int(row["t"] if row else 0)
        return used + est_tokens < cap
    except Exception:
        return True


def _call_provider(provider: str, prompt: str, *, model: str | None, max_tokens: int) -> tuple[str, dict]:
    if provider == "openai" and settings.openai_api_key:
        import httpx

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": model or settings.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage
    if provider == "groq" and settings.groq_api_key:
        import httpx

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": settings.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"], data.get("usage", {})
    return f"[AI:{provider}] {prompt[:500]}", {"prompt_tokens": len(prompt) // 4, "completion_tokens": 50}


def _record_usage(tenant_id: str, model: str, job_type: str, usage: dict) -> None:
    pt = int(usage.get("prompt_tokens", 0))
    ct = int(usage.get("completion_tokens", 0))
    cost = (pt + ct) * 0.000002
    try:
        from storage.postgres import postgres_configured
        from storage.postgres_backend import pg_cursor

        if postgres_configured():
            with pg_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_usage_events (tenant_id, model, job_type, prompt_tokens, completion_tokens, cost_usd)
                    VALUES (%s::uuid, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, model, job_type, pt, ct, cost),
                )
            return
    except Exception:
        pass
    from storage.database import Database
    import uuid
    from datetime import datetime, timezone

    with Database().connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_usage_events (id, tenant_id, model, job_type, prompt_tokens, completion_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), tenant_id, model, job_type, pt, ct, cost, datetime.now(timezone.utc).isoformat()),
        )
