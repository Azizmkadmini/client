"""Collecte Instagram : handles trouvés sur le web → HTTP public puis Playwright."""

from __future__ import annotations

from config import settings
from scraper.instagram_login import (
    ensure_instagram_logged_in_with_password,
    instagram_password_login_configured,
    instagram_session_storage_ready,
    launch_chromium_for_instagram_password,
)
from scraper.location_filter import apply_location_filters, request_has_location_filters
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value
from scraper.progress import scraper_progress
from scraper.query_parse import split_scraper_queries
from scraper.web.discovery import discover_instagram_handles
from scraper.web.public_fetch import instagram_record_from_public_page
from scraper.web.stability import max_queries_per_run, pause_between_web_requests
from scraper.browser import require_session
from utils.browser_session import close_session, open_channel_context, persist_context_state


def collect_web_instagram(request) -> list[ScraperRecord]:
    raw = (request.query or "").strip()
    if not raw:
        raise RuntimeError("Indiquez un mot-clé ou hashtag pour la collecte web Instagram.")
    queries = split_scraper_queries(raw, mode=request.mode)[: max_queries_per_run()]
    if not queries:
        raise RuntimeError("Aucun mot-clé valide.")

    handles: list[str] = []
    seen: set[str] = set()
    per_query = max(request.limit, 5)
    for q_idx, term in enumerate(queries):
        scraper_progress(
            phase="web_discover",
            fraction=0.05 + 0.12 * (q_idx / max(len(queries), 1)),
            message=f"Recherche web Instagram « {term} »…",
        )
        pause_between_web_requests()
        for handle in discover_instagram_handles(term, limit=per_query):
            if handle in seen:
                continue
            seen.add(handle)
            handles.append(handle)
    handles = handles[: request.limit * max(len(queries), 1)]
    if not handles:
        raise RuntimeError(
            f"Aucun profil Instagram trouvé sur le web pour : {', '.join(queries)}. "
            "Essayez d'autres mots-clés ou le mode app : "
            "`python -m scraper.cli run --app instagram`."
        )

    use_playwright = bool(
        getattr(settings, "scraper_web_instagram_playwright_fallback", True)
    )
    records: list[ScraperRecord] = []
    need_browser: list[str] = []

    n = len(handles)
    for i, handle in enumerate(handles, start=1):
        scraper_progress(
            phase="web_public",
            fraction=0.18 + 0.35 * (i / n),
            message=f"Lecture publique @{handle} ({i}/{n})…",
        )
        pause_between_web_requests()
        public = instagram_record_from_public_page(handle, request.app)
        if public is not None and (
            not is_empty_value(public.email)
            or not is_empty_value(public.whatsapp)
            or len((public.about or "")) > 20
        ):
            records.append(public)
        elif use_playwright:
            need_browser.append(handle)
        else:
            if public is not None:
                records.append(public)

    if need_browser:
        records.extend(_enrich_handles_playwright(need_browser, request.app, base_fraction=0.55))

    records = [r for r in records if r.nom != EMPTY_VALUE or not is_empty_value(r.email)]
    total_before = len(records)
    records = apply_location_filters(
        records,
        include_keywords=request.include_location_keywords,
        exclude_keywords=request.exclude_location_keywords,
    )
    if not records and total_before > 0 and request_has_location_filters(
        request.include_location_keywords,
        request.exclude_location_keywords,
    ):
        raise RuntimeError(
            f"{total_before} profil(s) Instagram via le web, filtre géographique trop strict."
        )
    if not records:
        raise RuntimeError(
            f"Aucune donnée exploitable pour {len(handles)} profil(s). "
            "Connectez Instagram : `python outreach.py login instagram`."
        )
    scraper_progress(
        phase="web_done",
        fraction=1.0,
        message=f"Collecte web Instagram terminée — {len(records)} profil(s).",
    )
    return records


def _enrich_handles_playwright(handles: list[str], app: str, *, base_fraction: float) -> list[ScraperRecord]:
    from playwright.sync_api import sync_playwright

    from scraper.collectors import _scrape_instagram_profile

    from scraper.instagram_stability import validate_instagram_session_file

    use_password = instagram_password_login_configured() and not instagram_session_storage_ready()
    if not use_password:
        validate_instagram_session_file()
        require_session("instagram")

    out: list[ScraperRecord] = []
    n = len(handles)
    with sync_playwright() as playwright:
        if use_password:
            browser, context = launch_chromium_for_instagram_password(playwright)
            owns_browser = True
        else:
            browser, context, owns_browser = open_channel_context(
                playwright,
                "instagram",
                headless=settings.scraper_headless,
            )
        if use_password:
            page = context.new_page()
            ensure_instagram_logged_in_with_password(page)
            page.close()

        for i, handle in enumerate(handles):
            lo = base_fraction + (1.0 - base_fraction) * (i / n)
            hi = base_fraction + (1.0 - base_fraction) * ((i + 1) / n)
            out.append(
                _scrape_instagram_profile(
                    context,
                    handle,
                    app,
                    progress_base=lo,
                    progress_width=hi - lo,
                    profile_index=i + 1,
                    profile_total=n,
                )
            )
        persist_context_state("instagram", context)
        close_session(browser, context, owns_browser=owns_browser)
    return out
