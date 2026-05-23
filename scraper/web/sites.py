"""Google → sites d'entreprises → crawl contacts (sans LinkedIn / Instagram)."""

from __future__ import annotations

from urllib.parse import urlparse

from config import settings
from scraper.extractors import parse_domain
from scraper.contact_recovery import is_placeholder_like_email
from scraper.extractors import normalize_email
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value
from scraper.progress import scraper_progress
from scraper.query_parse import split_scraper_queries
from scraper.site_contact_fetch import supplement_contacts_from_website
from scraper.web.search_engine import web_search_urls
from scraper.web.stability import max_queries_per_run, pause_between_web_requests

_SOCIAL_HOSTS = (
    "linkedin.com",
    "licdn.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "wa.me",
    "google.com",
    "wikipedia.org",
)

_EXCLUDE_SITES = (
    "-site:linkedin.com",
    "-site:instagram.com",
    "-site:facebook.com",
    "-site:youtube.com",
    "-site:twitter.com",
    "-site:x.com",
)


def _host_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _site_root(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _is_business_site(url: str) -> bool:
    host = _host_from_url(url)
    if not host or "." not in host:
        return False
    return not any(s in host for s in _SOCIAL_HOSTS)


def _google_queries_for_term(term: str) -> list[str]:
    """Variantes Bing orientées agences / PME (évite le bruit « immobilier » générique)."""
    base = term.strip()
    if not base:
        return []
    low = base.lower()
    if any(w in low for w in ("marketing", "communication", "digital", "publicité", "evenement", "événement")):
        return [
            f"agence {base} France contact email",
            f"{base} agence digitale contact",
            f"{base} studio créatif email",
        ]
    return [
        f"{base} entreprise contact email France",
        f"{base} agence contact",
        base,
    ]


def _email_usable(email: str) -> bool:
    if is_empty_value(email) or is_placeholder_like_email(email):
        return False
    cleaned = normalize_email(email)
    if is_empty_value(cleaned):
        return False
    low = cleaned.lower()
    if any(bad in low for bad in (".mjs", ".js@", "jquery", "webpack", "@2x.", "example.com")):
        return False
    return True


def _discover_business_sites(term: str, *, limit: int) -> list[str]:
    roots: list[str] = []
    seen_hosts: set[str] = set()
    for search_q in _google_queries_for_term(term):
        if len(roots) >= limit:
            break
        for url in web_search_urls(search_q, max_results=limit * 2):
            if not _is_business_site(url):
                continue
            root = _site_root(url)
            if not root:
                continue
            host = _host_from_url(root)
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            roots.append(root)
            if len(roots) >= limit:
                return roots
    return roots


def collect_web_sites(request) -> list[ScraperRecord]:
    """
    Recherche Google → crawl des sites → e-mail / WhatsApp.
    Aucune session LinkedIn ou Instagram.
    """
    raw = (request.query or "").strip()
    if not raw:
        raise RuntimeError(
            "Indiquez une requête Google (ex. « agence événementiel Tunis contact email »)."
        )
    queries = split_scraper_queries(raw, mode=request.mode)[: max_queries_per_run()]
    if not queries:
        raise RuntimeError("Aucune requête valide.")

    target = max(request.limit, 5)
    per_query = max(target * 2, 12)
    site_urls: list[str] = []
    seen_hosts: set[str] = set()

    for q_idx, term in enumerate(queries):
        scraper_progress(
            phase="google_search",
            fraction=0.05 + 0.2 * (q_idx / max(len(queries), 1)),
            message=f"Google (sites web) : « {term} » ({q_idx + 1}/{len(queries)})…",
        )
        pause_between_web_requests()
        for root in _discover_business_sites(term, limit=per_query):
            host = _host_from_url(root)
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            site_urls.append(root)
            if len(site_urls) >= per_query * len(queries):
                break
        if len(site_urls) >= per_query * len(queries):
            break

    if not site_urls:
        from scraper.web.search_engine import last_google_cse_error

        cse_hint = last_google_cse_error()
        extra = ""
        if cse_hint:
            extra = f"\n\nGoogle CSE : {cse_hint}"
            if "access" in cse_hint.lower() or "403" in cse_hint:
                extra += (
                    "\n→ Google Cloud : activer **Custom Search API** pour le projet de la clé "
                    "(APIs & Services → Bibliothèque → Custom Search API → Activer)."
                )
        raise RuntimeError(
            f"Aucun site web trouvé pour : {', '.join(queries)}.{extra}\n\n"
            "Essayez une requête plus précise (ex. « agence marketing Paris contact email »). "
            "Vérifiez SCRAPER_WEB_SEARCH_PROVIDER=bing et relancez."
        )

    records: list[ScraperRecord] = []
    seen_emails: set[str] = set()
    n = max(len(site_urls), 1)
    for idx, site in enumerate(site_urls, start=1):
        if len(records) >= target:
            break
        host = _host_from_url(site)
        scraper_progress(
            phase="web_site_crawl",
            fraction=0.25 + 0.72 * min(1.0, idx / n),
            message=f"Crawl {idx}/{n} — {host}… ({len(records)}/{target} leads)",
        )
        pause_between_web_requests()
        email, whatsapp = supplement_contacts_from_website(site)
        if _email_usable(email):
            email = normalize_email(email)
            if email.lower() in seen_emails:
                email = EMPTY_VALUE
            else:
                seen_emails.add(email.lower())
        else:
            email = EMPTY_VALUE
        if is_empty_value(email) and is_empty_value(whatsapp):
            continue
        records.append(
            ScraperRecord(
                nom=host or EMPTY_VALUE,
                email=email,
                whatsapp=whatsapp,
                pays=EMPTY_VALUE,
                entreprise=host or EMPTY_VALUE,
                domaine=parse_domain(site),
                site_web=site,
                about=EMPTY_VALUE,
                app="web",
                link=site,
            )
        )

    if not records:
        raise RuntimeError(
            f"{len(site_urls)} site(s) testé(s), aucun e-mail / WhatsApp valide. "
            "Changez la requête (ex. « agence marketing digitale Paris contact ») "
            "ou augmentez « Nombre de sites ». Cochez « Remplacer le CSV web » pour ne pas "
            "garder d'anciennes lignes."
        )
    scraper_progress(
        phase="web_done",
        fraction=1.0,
        message=f"Terminé — {len(records)} site(s) avec contact.",
    )
    return records
