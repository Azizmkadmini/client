"""Découverte LinkedIn / Instagram via recherche web (Google par défaut)."""

from __future__ import annotations

import re

from scraper.web.search_engine import web_search_urls

_LINKEDIN_PROFILE_RE = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([a-zA-Z0-9\-_%]+)/?",
    re.IGNORECASE,
)
_LINKEDIN_COMPANY_RE = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/([a-zA-Z0-9\-_%]+)/?",
    re.IGNORECASE,
)
_INSTAGRAM_PROFILE_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/([a-zA-Z0-9._]+)/?",
    re.IGNORECASE,
)
_IG_RESERVED = frozenset(
    {
        "accounts",
        "stories",
        "direct",
        "reels",
        "explore",
        "p",
        "tv",
        "about",
        "legal",
        "developer",
    }
)


def _normalize_linkedin_profile_url(url: str) -> str:
    m = _LINKEDIN_PROFILE_RE.search(url)
    if not m:
        return ""
    slug = m.group(1).strip("/")
    if not slug or slug.lower() in {"login", "signup"}:
        return ""
    return f"https://www.linkedin.com/in/{slug}/"


def _normalize_linkedin_company_url(url: str) -> str:
    m = _LINKEDIN_COMPANY_RE.search(url)
    if not m:
        return ""
    slug = m.group(1).strip("/")
    if not slug:
        return ""
    return f"https://www.linkedin.com/company/{slug}/"


def discover_linkedin_urls(
    query: str,
    *,
    include_companies: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Profils / entreprises LinkedIn trouvés via Google (ou provider .env)."""
    from scraper.web.stability import max_discovery_results_per_query

    cap = limit if limit is not None else max_discovery_results_per_query()
    urls: list[str] = []
    seen: set[str] = set()

    people_queries = (
        f'{query} site:linkedin.com/in/',
        f'"{query}" linkedin profil',
    )
    for search_q in people_queries:
        for item in web_search_urls(search_q, max_results=cap * 3):
            url = _normalize_linkedin_profile_url(item)
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= cap:
                return urls[:cap]
        if urls:
            break

    if not include_companies:
        return urls[:cap]

    company_queries = (
        f'{query} site:linkedin.com/company/',
        f'"{query}" linkedin entreprise',
    )
    for search_q in company_queries:
        for item in web_search_urls(search_q, max_results=cap * 2):
            url = _normalize_linkedin_company_url(item)
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= cap:
                break
        if len(urls) >= cap:
            break
    return urls[:cap]


def discover_instagram_handles(query: str, *, limit: int | None = None) -> list[str]:
    from scraper.web.stability import max_discovery_results_per_query

    cap = limit if limit is not None else max_discovery_results_per_query()
    handles: list[str] = []
    seen: set[str] = set()
    for search_q in (
        f"{query} site:instagram.com",
        f'"{query}" instagram profil',
    ):
        for item in web_search_urls(search_q, max_results=cap * 3):
            m = _INSTAGRAM_PROFILE_RE.search(item)
            if not m:
                continue
            handle = m.group(1).lower().strip(".")
            if not handle or handle in _IG_RESERVED:
                continue
            if "/p/" in item or "/reel" in item.lower():
                continue
            if handle in seen:
                continue
            seen.add(handle)
            handles.append(handle)
            if len(handles) >= cap:
                return handles[:cap]
        if handles:
            break
    return handles[:cap]
