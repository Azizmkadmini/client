"""Collecte LinkedIn : URLs trouvées sur le web → enrichissement Playwright."""

from __future__ import annotations

import re

from config import settings
from scraper.collectors import (
    _filter_linkedin_records_with_contact,
    _linkedin_has_email_or_whatsapp,
    _profile_cache_lookup,
    _profile_cache_mark_seen,
)
from scraper.linkedin_company import enrich_linkedin_company_fast_email
from scraper.linkedin_profile import enrich_linkedin_profile_fast_email
from scraper.linkedin_stability import (
    assert_linkedin_page_ok,
    inter_profile_pause_jitter_ms,
    maybe_long_pause_between_profiles,
    validate_linkedin_session_file,
)
from scraper.location_filter import apply_location_filters, request_has_location_filters
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value
from scraper.progress import scraper_progress
from scraper.query_parse import split_scraper_queries
from scraper.web.discovery import discover_linkedin_urls
from scraper.web.stability import max_queries_per_run, pause_between_web_requests
from scraper.browser import require_session
from utils.browser_session import close_session, open_channel_context, persist_context_state


def _slug_to_title(slug: str) -> str:
    text = slug.replace("-", " ").replace("_", " ").strip()
    return text.title() if text else EMPTY_VALUE


def _record_from_linkedin_url(url: str) -> ScraperRecord:
    low = url.lower()
    if "/company/" in low:
        match = re.search(r"/company/([^/?#]+)", url, re.IGNORECASE)
        slug = match.group(1) if match else ""
        return ScraperRecord(
            nom=_slug_to_title(slug),
            entreprise=_slug_to_title(slug),
            app="linkedin",
            link=url,
        )
    match = re.search(r"/in/([^/?#]+)", url, re.IGNORECASE)
    slug = match.group(1) if match else ""
    return ScraperRecord(
        nom=_slug_to_title(slug),
        app="linkedin",
        link=url,
    )


def collect_web_linkedin(request) -> list[ScraperRecord]:
    from playwright.sync_api import sync_playwright

    raw = (request.query or "").strip()
    if not raw:
        raise RuntimeError("Indiquez un mot-clé pour la collecte web LinkedIn.")
    queries = split_scraper_queries(raw, mode=request.mode)[: max_queries_per_run()]
    if not queries:
        raise RuntimeError("Aucun mot-clé valide.")

    scopes = tuple(request.linkedin_scopes or ())
    if scopes:
        include_companies = "companies" in scopes
        people_only = "people" in scopes and "companies" not in scopes
    else:
        include_companies = bool(
            getattr(settings, "scraper_web_linkedin_include_companies", False)
        )
        people_only = not include_companies

    validate_linkedin_session_file()
    require_session("linkedin")

    discovered: list[ScraperRecord] = []
    seen_urls: set[str] = set()
    per_query = max(request.limit, 5)
    for q_idx, term in enumerate(queries):
        scraper_progress(
            phase="web_discover",
            fraction=0.05 + 0.15 * (q_idx / max(len(queries), 1)),
            message=f"Google → LinkedIn « {term} » ({q_idx + 1}/{len(queries)})…",
        )
        pause_between_web_requests()
        urls = discover_linkedin_urls(
            term,
            include_companies=include_companies and not people_only,
            limit=per_query,
        )
        if people_only:
            urls = [u for u in urls if "/in/" in u.lower()]
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            discovered.append(_record_from_linkedin_url(url))
        if len(discovered) >= request.limit * len(queries):
            break
    discovered = discovered[: request.limit * max(len(queries), 1)]
    if not discovered:
        raise RuntimeError(
            f"Aucune URL LinkedIn trouvée sur le web pour : {', '.join(queries)}. "
            "Essayez d'autres mots-clés ou utilisez le mode classique : "
            "`python -m scraper.cli run --app linkedin`."
        )

    records: list[ScraperRecord] = []
    n = len(discovered)
    with sync_playwright() as playwright:
        from utils.session_channels import scrape_session_channel

        browser, context, owns_browser = open_channel_context(
            playwright,
            scrape_session_channel("linkedin"),
            headless=settings.scraper_headless,
        )
        page = context.new_page()
        page.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_timeout(2500)
        assert_linkedin_page_ok(page)

        for idx, stub in enumerate(discovered, start=1):
            scraper_progress(
                phase="web_enrich",
                fraction=0.2 + 0.78 * (idx / n),
                message=f"Enrichissement web {idx}/{n} — {stub.link}…",
            )
            status, cached = _profile_cache_lookup(stub)
            if status == "fresh" and cached is not None:
                records.append(cached)
                continue
            if status == "stale" and cached is not None:
                records.append(cached)
                _profile_cache_mark_seen(cached)
                continue

            try:
                page.goto(stub.link, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(1500)
                assert_linkedin_page_ok(page)
                if "/company/" in (stub.link or "").lower():
                    enriched = enrich_linkedin_company_fast_email(page, stub)
                else:
                    enriched = enrich_linkedin_profile_fast_email(page, stub)
            except Exception:
                enriched = stub
            _profile_cache_mark_seen(enriched)
            records.append(enriched)
            maybe_long_pause_between_profiles(idx)
            page.wait_for_timeout(inter_profile_pause_jitter_ms())

        persist_context_state("linkedin", context)
        close_session(browser, context, owns_browser=owns_browser)

    records = [r for r in records if not is_empty_value(r.nom) or not is_empty_value(r.link)]
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
            f"{total_before} profil(s) trouvé(s) via le web, mais aucun ne passe le filtre géographique."
        )
    records = _filter_linkedin_records_with_contact(records)
    if not records and total_before > 0:
        raise RuntimeError(
            f"{total_before} profil(s) enrichi(s) sans e-mail exploitable. "
            "Activez SCRAPER_FETCH_CONTACTS_FROM_WEBSITE ou assouplissez SCRAPER_LINKEDIN_PRIORITIZE_EMAIL."
        )
    with_contact = [r for r in records if _linkedin_has_email_or_whatsapp(r)]
    scraper_progress(
        phase="web_done",
        fraction=1.0,
        message=f"Collecte web LinkedIn terminée — {len(with_contact)} contact(s) utile(s).",
    )
    return records
