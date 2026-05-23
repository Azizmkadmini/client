"""Vérifications pré-run (sessions, SMTP, Redis, web)."""

from __future__ import annotations

from typing import Any

from config import settings


def _check_linkedin_scrape() -> dict[str, Any]:
    try:
        from scraper.linkedin_stability import session_file_age_days, validate_linkedin_session_file

        path = validate_linkedin_session_file()
        age = session_file_age_days("linkedin")
        return {"ok": True, "path": str(path), "age_days": age}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_linkedin_outreach() -> dict[str, Any]:
    from utils.session_channels import first_existing_session

    path = first_existing_session("linkedin", role="outreach")
    if path is None:
        return {
            "ok": False,
            "error": "Aucune session outreach — python outreach.py login linkedin-outreach",
        }
    return {"ok": True, "path": str(path)}


def _check_instagram() -> dict[str, Any]:
    try:
        from scraper.instagram_stability import session_file_age_days, validate_instagram_session_file

        path = validate_instagram_session_file()
        age = session_file_age_days("instagram")
        return {"ok": True, "path": str(path), "age_days": age}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_smtp() -> dict[str, Any]:
    from utils.smtp_config import smtp_configured

    if not smtp_configured():
        return {"ok": False, "error": "SMTP non configuré (SMTP_USER, SMTP_PASSWORD, SMTP_FROM)"}
    return {"ok": True}


def _check_redis() -> dict[str, Any]:
    url = (settings.redis_url or "").strip()
    if not url:
        return {"ok": True, "skipped": True, "message": "REDIS_URL vide — mode subprocess/sync"}
    try:
        from workers.queue import JobQueue

        client = JobQueue()._client()
        client.ping()
        return {"ok": True, "url": url.split("@")[-1] if "@" in url else url}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_web_provider() -> dict[str, Any]:
    provider = (settings.scraper_web_search_provider or "bing").strip().lower()
    return {
        "ok": True,
        "provider": provider,
        "hint": "google_cse souvent 403 sur nouveaux comptes Google — préférer bing",
    }


def run_checks() -> dict[str, Any]:
    checks = {
        "linkedin_scrape": _check_linkedin_scrape(),
        "linkedin_outreach": _check_linkedin_outreach(),
        "instagram": _check_instagram(),
        "smtp": _check_smtp(),
        "redis": _check_redis(),
        "web_search": _check_web_provider(),
    }
    checks["ok"] = all(
        c.get("ok") or c.get("skipped") for c in checks.values() if isinstance(c, dict)
    )
    return checks
