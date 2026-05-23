"""Réglages et garde-fous LinkedIn (session, rythme, limites)."""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from pathlib import Path

from config import settings


def linkedin_stable_mode() -> bool:
    return bool(getattr(settings, "scraper_stable_linkedin_mode", True))


def linkedin_fast_timing_allowed() -> bool:
    """En mode stable, les pauses LinkedIn ignorent ``scraper_fast_mode``."""
    if linkedin_stable_mode():
        return False
    return bool(getattr(settings, "scraper_fast_mode", False))


def effective_max_profiles_to_try(limit: int) -> int:
    configured = int(getattr(settings, "scraper_linkedin_max_profiles_to_try", 0) or 0)
    cap = int(getattr(settings, "scraper_linkedin_stable_max_profiles_per_search", 25) or 25)
    if linkedin_stable_mode():
        base = configured if configured > 0 else max(limit * 8, 12)
        return min(max(base, limit), cap)
    if configured > 0:
        return max(configured, limit)
    floor = 50 if linkedin_fast_timing_allowed() else 80
    return max(limit * 25, floor)


def effective_search_scroll_rounds() -> int:
    configured = int(getattr(settings, "scraper_linkedin_max_search_scroll_rounds", 12) or 12)
    if linkedin_stable_mode():
        return min(configured, 5) if configured > 0 else 4
    if linkedin_fast_timing_allowed():
        return 1
    return min(configured, 8) if configured > 0 else 3


def effective_search_terms_cap(query_count: int) -> int:
    max_terms = int(getattr(settings, "scraper_linkedin_max_search_terms", 0) or 0)
    stable_cap = int(getattr(settings, "scraper_linkedin_stable_max_search_terms", 4) or 4)
    if linkedin_stable_mode() and max_terms <= 0:
        return min(query_count, stable_cap)
    if max_terms > 0:
        return min(query_count, max_terms)
    return query_count


def inter_profile_pause_jitter_ms() -> int:
    base_s = float(getattr(settings, "scraper_inter_profile_pause_seconds", 3.0) or 3.0)
    if linkedin_stable_mode():
        base_s = max(2.5, min(base_s, 8.0))
        jitter = random.uniform(0.85, 1.25)
        return int(base_s * jitter * 1000)
    base_s = max(0.25, min(base_s, 6.0))
    return int(base_s * 1000)


def maybe_long_pause_between_profiles(profile_index: int) -> None:
    """Pause longue aléatoire tous les N profils (comportement humain)."""
    if not linkedin_stable_mode() or profile_index < 2:
        return
    every_min = int(getattr(settings, "scraper_linkedin_long_pause_every_min", 6) or 6)
    every_max = int(getattr(settings, "scraper_linkedin_long_pause_every_max", 10) or 10)
    if every_min < 2:
        return
    slot = random.randint(every_min, max(every_min, every_max))
    if profile_index % slot != 0:
        return
    lo = int(getattr(settings, "scraper_linkedin_long_pause_seconds_min", 45) or 45)
    hi = int(getattr(settings, "scraper_linkedin_long_pause_seconds_max", 120) or 120)
    time.sleep(random.uniform(lo, hi))


def session_file_age_days(channel: str = "linkedin") -> float | None:
    from utils.session_channels import first_existing_session

    if channel in ("linkedin", "linkedin-scrape", "linkedin-outreach"):
        path = first_existing_session(channel, role="scrape")
    else:
        path = settings.path(settings.session_dir) / f"{channel}.json"
        if not path.is_file():
            return None
    if path is None or not path.is_file():
        return None
    mtime = path.stat().st_mtime
    return (time.time() - mtime) / 86400.0


def validate_linkedin_session_file() -> Path:
    from utils.session_channels import first_existing_session

    path = first_existing_session("linkedin", role="scrape")
    if path is None:
        raise RuntimeError(
            "Aucune session LinkedIn (scrape). Lancez :\n"
            "  python outreach.py login linkedin-scrape\n"
            "Ou (legacy, un seul compte) :\n"
            "  python outreach.py login linkedin\n"
            "Ou (Chrome déjà connecté) :\n"
            "  python outreach.py login linkedin-scrape --from-browser chrome"
        )
    max_days = float(getattr(settings, "scraper_session_max_age_days", 10) or 10)
    age = session_file_age_days("linkedin")
    if age is not None and age > max_days:
        raise RuntimeError(
            f"Session LinkedIn vieille ({age:.0f} j — max recommandé {max_days:.0f} j). "
            "Reconnectez : python outreach.py login linkedin-scrape"
        )
    return path


def linkedin_url_is_blocked(url: str) -> bool:
    low = (url or "").lower()
    return any(
        token in low
        for token in (
            "/login",
            "/uas/login",
            "/checkpoint",
            "authwall",
            "/challenge",
            "security-verification",
        )
    )


def assert_linkedin_page_ok(page, *, context: str = "linkedin") -> None:
    url = (page.url or "").lower()
    if linkedin_url_is_blocked(url):
        hint = (
            "Session LinkedIn expirée ou vérification demandée. "
            "Arrêtez le scraper, ouvrez LinkedIn dans Chrome, terminez la vérif, puis :\n"
            "  python outreach.py login linkedin"
        )
        if "/checkpoint" in url or "challenge" in url:
            hint += (
                "\nAttendez 24–48 h sans automation si LinkedIn a bloqué le compte."
            )
        raise RuntimeError(f"{context}: {hint}\nURL: {page.url}")
