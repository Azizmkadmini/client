"""Génération IA — hooks, posts, CTA (OpenAI / Claude / Ollama via config)."""

from __future__ import annotations

import httpx

from config import settings
from content.models import (
    ContentFormat,
    GenerateHookRequest,
    GeneratePostRequest,
    HookVariant,
    PostDraft,
)


def _content_provider() -> str:
    return (getattr(settings, "content_ai_provider", None) or settings.ai_provider or "ollama").strip().lower()


def _complete(system: str, user: str) -> str:
    provider = _content_provider()
    if provider == "openai" and settings.openai_api_key:
        model = getattr(settings, "content_openai_model", None) or settings.openai_model
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.85,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    if provider in ("claude", "anthropic") and getattr(settings, "content_claude_api_key", ""):
        key = settings.content_claude_api_key
        model = getattr(settings, "content_claude_model", "claude-3-5-sonnet-20241022")
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2048,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["content"][0]["text"].strip()
    # Ollama fallback
    base = settings.ollama_base_url.rstrip("/")
    model = getattr(settings, "content_ollama_model", None) or settings.ollama_model
    with httpx.Client(timeout=180.0) as client:
        r = client.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


def generate_hooks(req: GenerateHookRequest) -> list[HookVariant]:
    system = (
        "Tu es un expert copywriting LinkedIn. Génère des accroches courtes "
        "qui stoppent le scroll. Une accroche par ligne, sans numérotation."
    )
    user = (
        f"Langue: {req.language}\n"
        f"Sujet: {req.topic}\n"
        f"Audience: {req.audience}\n"
        f"Ton: {req.tone}\n"
        f"Nombre: {req.count}\n"
    )
    raw = _complete(system, user)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    hooks = [HookVariant(text=ln.lstrip("0123456789.-) ")) for ln in lines[: req.count]]
    while len(hooks) < req.count:
        hooks.append(HookVariant(text=f"{req.topic} — angle {len(hooks) + 1}"))
    return hooks[: req.count]


def generate_post(req: GeneratePostRequest) -> PostDraft:
    fmt = req.format.value if isinstance(req.format, ContentFormat) else str(req.format)
    system = (
        "Tu rédiges des posts LinkedIn structurés, lisibles mobile, paragraphes courts. "
        "Pas de hashtags sauf 3 max en fin si pertinent."
    )
    user = (
        f"Langue: {req.language}\nFormat: {fmt}\nSujet: {req.topic}\n"
        f"Longueur max: {req.max_chars} caractères\n"
    )
    if req.hook:
        user += f"Accroche imposée: {req.hook}\n"
    if req.brand_voice:
        user += f"Voix de marque: {req.brand_voice}\n"
    body = _complete(system, user)
    cta = generate_cta(req.topic, language=req.language) if req.include_cta else None
    return PostDraft(hook=req.hook, body=body, cta=cta, format=req.format)


def generate_cta(topic: str, *, language: str = "fr") -> str:
    system = "Génère une seule ligne CTA LinkedIn (question ou invitation claire)."
    user = f"Langue: {language}\nSujet du post: {topic}\n"
    return _complete(system, user).splitlines()[0].strip()
