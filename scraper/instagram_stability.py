"""Garde-fous session Instagram (âge fichier, URL bloquée)."""

from __future__ import annotations

import time
from pathlib import Path

from config import settings


def session_file_age_days(channel: str = "instagram") -> float | None:
    path = settings.path(settings.session_dir) / f"{channel}.json"
    if not path.is_file():
        return None
    return (time.time() - path.stat().st_mtime) / 86400.0


def validate_instagram_session_file() -> Path:
    path = settings.path(settings.session_dir) / "instagram.json"
    if not path.is_file():
        raise RuntimeError(
            "Aucune session Instagram. Lancez :\n"
            "  python outreach.py login instagram\n"
            "Ou :\n"
            "  python outreach.py login instagram --from-browser chrome"
        )
    max_days = float(getattr(settings, "scraper_session_max_age_days", 10) or 10)
    age = session_file_age_days("instagram")
    if age is not None and age > max_days:
        raise RuntimeError(
            f"Session Instagram vieille ({age:.0f} j — max {max_days:.0f} j). "
            "Reconnectez : python outreach.py login instagram"
        )
    if path.stat().st_size < 500:
        raise RuntimeError(
            f"Session Instagram invalide ou vide ({path}). "
            "Relancez : python outreach.py login instagram"
        )
    return path


def instagram_url_is_blocked(url: str) -> bool:
    low = (url or "").lower()
    return any(
        token in low
        for token in (
            "/accounts/login",
            "/challenge",
            "checkpoint",
            "consent",
        )
    )
