from __future__ import annotations

import html as html_module
import re
import threading
import time
from collections import deque
from urllib.parse import unquote, urljoin, urlparse

import httpx

from config import settings
from scraper.extractors import (
    normalize_email,
    normalize_whatsapp_number,
    normalize_website_url,
    parse_email,
    parse_whatsapp,
    parse_whatsapp_from_links,
)
from scraper.models import EMPTY_VALUE
from scraper.progress import scraper_progress
from scraper.timing import (
    site_crawl_bfs_enabled,
    site_crawl_max_pages_effective,
    site_crawl_total_seconds_effective,
    website_triple_probe_per_request_seconds,
)

# Cache des domaines/sites déjà crawlés dans ce run.
# Clé : base URL normalisée → (email, phone).  Évite de recrawler la même agence
# pour chaque profil LinkedIn (ex. 8 profils de la même agence → 1 seul crawl).
_site_email_cache: dict[str, tuple[str, str]] = {}
_site_email_cache_lock = threading.Lock()


def clear_site_email_cache() -> None:
    """Réinitialise le cache entre deux runs scraper distincts."""
    with _site_email_cache_lock:
        _site_email_cache.clear()


# 3 pages ciblées avant le crawl complet (e-mails souvent ici sur les sites d'agences).
WEBSITE_TRIPLE_CONTACT_PATHS: tuple[str, ...] = (
    "contact",
    "contact/",
    "nous-contacter",
    "contactez-nous",
    "contact-us",
    "fr/contact",
    "en/contact",
)
WEBSITE_TRIPLE_LEGAL_PATHS: tuple[str, ...] = (
    "mentions-legales",
    "mentions-legales/",
    "legal",
    "legal-notice",
    "a-propos",
    "about",
    "about-us",
    "qui-sommes-nous",
)

# mailto:addr?subject=… — on ne garde que la partie avant ?
MAILTO_RE = re.compile(r"mailto:([^\"'\s<>]+)", re.IGNORECASE)
TEL_HREF_RE = re.compile(
    r'(?:href|data-href)\s*=\s*["\']?\s*tel:([^"\'\s<>]+)',
    re.IGNORECASE,
)
LD_JSON_BLOCK_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
ANCHOR_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_ROBOTS_SITEMAP_RE = re.compile(r"^Sitemap:\s*(\S+)", re.IGNORECASE | re.MULTILINE)

PRIORITY_PATH_KEYWORDS: tuple[str, ...] = (
    "contact",
    "nous-contacter",
    "contactez",
    "ecrivez",
    "about",
    "a-propos",
    "qui-sommes",
    "mentions",
    "legal",
    "notice",
    "imprint",
    "impressum",
    "kontakt",
    "contatti",
    "contacto",
    "support",
    "equipe",
    "team",
    "office",
    "agence",
    "location",
    "privacy",
    "politique",
    "conditions",
    "cgv",
    "cgu",
    "terms",
    "help",
    "aide",
    "faq",
    "recrutement",
    "careers",
)

# Entrées BFS : page d'accueil + variantes contact / légal / équipe (multi-langues).
SITE_SEED_SUBPATHS: tuple[str, ...] = (
    "contact",
    "contact/",
    "contact-us",
    "contact_us",
    "contactus",
    "contactez-nous",
    "ecrire",
    "ecrivez-nous",
    "nous-contacter",
    "nous-contacter/",
    "a-propos",
    "a-propos/",
    "about",
    "about-us",
    "about_us",
    "qui-sommes-nous",
    "mentions-legales",
    "mentions-legales/",
    "legal",
    "legal-notice",
    "notice-legale",
    "imprint",
    "impressum",
    "politique-de-confidentialite",
    "privacy",
    "privacy-policy",
    "cgv",
    "cgu",
    "conditions-generales",
    "terms",
    "terms-of-service",
    "kontakt",
    "de/kontakt",
    "de/contact",
    "en/contact",
    "en/about",
    "fr/contact",
    "fr/nous-contacter",
    "fr/a-propos",
    "it/contatti",
    "it/chi-siamo",
    "es/contacto",
    "nl/contact",
    "pt/contacto",
    "contact.html",
    "contact.php",
    "kontakt.html",
    "pages/contact",
    "pages/contact-us",
    "page/contact",
    "site/contact",
    "home/contact",
    "locations",
    "agences",
    "bureaux",
    "support",
    "help",
    "aide",
    "faq",
    "team",
    "equipe",
    "notre-equipe",
    "our-team",
)

# Sondage direct si l'e-mail manque encore après le crawl (URLs souvent non liées depuis l'accueil).
SITE_EXTRA_PROBE_SUBPATHS: tuple[str, ...] = (
    "contact",
    "contact/",
    "contact-us",
    "get-in-touch",
    "reach-us",
    "write-us",
    "nous-ecrire",
    "demande-de-contact",
    "request-info",
    "info/contact",
    "infos/contact",
    "company/contact",
    "corporate/contact",
    "global/contact",
    "worldwide/contact",
    "fr/contact",
    "en/contact",
    "de/kontakt",
    "es/contacto",
    "it/contatti",
    "nl/contact",
    "pt/contacto",
    "pl/kontakt",
    "sv/kontakt",
    "no/kontakt",
    "da/kontakt",
    "fi/yhteystiedot",
    "ja/contact",
    "zh/contact",
    "impressum",
    "imprint",
    "legal-notice",
    "mentions-legales",
    "politique-confidentialite",
    "service-client",
    "customer-service",
    "sales",
    "commercial",
)

SKIP_PATH_PREFIXES: tuple[str, ...] = (
    "/wp-login",
    "/wp-admin",
    "/wp-json",
    "/cart",
    "/checkout",
    "/my-account",
    "/account/login",
)

SKIP_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".css",
    ".js",
    ".m4v",
    ".mp4",
    ".woff",
    ".woff2",
    ".xml",
    ".rss",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _host_fetch_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return False
    if host.endswith(".local"):
        return False
    if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.16."):
        return False
    return True


def _mailto_to_email(raw: str) -> str:
    part = html_module.unescape(raw.split("?", 1)[0].strip())
    part = unquote(part)
    return normalize_email(part)


def _ld_json_blobs(html: str) -> str:
    parts = [m.group(1).strip() for m in LD_JSON_BLOCK_RE.finditer(html or "")]
    return "\n".join(parts) if parts else ""


def _looks_like_html(body: str) -> bool:
    head = (body or "")[:4000].lower()
    return "<html" in head or "<!doctype" in head or "<body" in head or "<head" in head


def _canonical_visit_key(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return url.rstrip("/")
    return parsed._replace(fragment="").geturl().rstrip("/")


def _allowed_hosts_for_site(base: str) -> set[str]:
    try:
        parsed = urlparse(base)
    except ValueError:
        return set()
    host = (parsed.hostname or "").lower()
    if not host:
        return set()
    hosts = {host}
    if host.startswith("www."):
        hosts.add(host.removeprefix("www."))
    else:
        hosts.add("www." + host)
    return hosts


def _origin_roots(base: str) -> list[str]:
    """Racines http(s) du site (apex + www) pour seeds, sitemap et sondes."""
    b = base.rstrip("/")
    origins: list[str] = [b]
    try:
        parsed = urlparse(b)
        host = (parsed.hostname or "").lower()
        if host and not host.startswith("www."):
            www_url = parsed._replace(netloc="www." + host).geturl().rstrip("/")
            origins.append(www_url)
    except ValueError:
        pass
    return origins


def _hostname_in_allowed(url: str, allowed_hosts: set[str]) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() in allowed_hosts
    except ValueError:
        return False


def _fetch_url_text(
    client: httpx.Client,
    url: str,
    deadline: float,
    *,
    max_chars: int = 3_000_000,
) -> str:
    if time.monotonic() > deadline:
        return ""
    try:
        response = client.get(url)
    except (httpx.HTTPError, OSError):
        return ""
    if response.status_code >= 400:
        return ""
    return (response.text or "")[:max_chars]


def _sitemap_urls_from_robots(
    client: httpx.Client,
    origins: list[str],
    deadline: float,
) -> list[str]:
    found: list[str] = []
    for root in origins:
        if time.monotonic() > deadline:
            break
        robots_url = urljoin(root.rstrip("/") + "/", "robots.txt")
        body = _fetch_url_text(client, robots_url, deadline, max_chars=512_000)
        for match in _ROBOTS_SITEMAP_RE.finditer(body):
            u = (match.group(1) or "").strip()
            if u:
                found.append(u)
    return found


def _sitemap_loc_is_interesting(url: str) -> bool:
    low = url.lower()
    if _link_is_priority(url):
        return True
    return any(
        seg in low
        for seg in (
            "/contact",
            "/about",
            "/legal",
            "/team",
            "/privacy",
            "impressum",
            "kontakt",
            "mentions",
            "conditions",
            "careers",
            "recrutement",
        )
    )


def _collect_sitemap_priority_urls(
    client: httpx.Client,
    base: str,
    allowed_hosts: set[str],
    deadline: float,
    *,
    max_return: int = 42,
) -> list[str]:
    """Lit sitemap(s) + robots.txt pour enfiler des pages « contact / légal » du même hôte."""
    origins = _origin_roots(base)
    candidates: list[str] = []
    for root in origins:
        prefix = root.rstrip("/") + "/"
        for path in (
            "sitemap.xml",
            "sitemap_index.xml",
            "wp-sitemap.xml",
            "page-sitemap.xml",
            "post-sitemap.xml",
        ):
            candidates.append(urljoin(prefix, path))
    candidates.extend(_sitemap_urls_from_robots(client, origins, deadline))

    seen_sm: set[str] = set()
    uniq_sm: list[str] = []
    for u in candidates:
        if u not in seen_sm:
            seen_sm.add(u)
            uniq_sm.append(u)

    collected: list[str] = []
    seen_page: set[str] = set()

    def maybe_add_page(url: str) -> None:
        if len(collected) >= max_return:
            return
        if not _hostname_in_allowed(url, allowed_hosts):
            return
        low = url.lower()
        if any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".zip")):
            return
        if not _sitemap_loc_is_interesting(url):
            return
        key = _canonical_visit_key(url)
        if key in seen_page:
            return
        seen_page.add(key)
        collected.append(url)

    def harvest_locs(body: str, depth: int) -> None:
        if depth > 4 or time.monotonic() > deadline:
            return
        locs = _LOC_RE.findall(body or "")
        xml_children = [loc for loc in locs if loc.lower().endswith(".xml")]
        if len(xml_children) >= 2 and len(locs) > 0 and len(xml_children) >= int(len(locs) * 0.85):
            for child in xml_children[:10]:
                if len(collected) >= max_return or time.monotonic() > deadline:
                    return
                sub_body = _fetch_url_text(client, child, deadline, max_chars=6_000_000)
                harvest_locs(sub_body, depth + 1)
            return
        for loc in locs:
            if len(collected) >= max_return or time.monotonic() > deadline:
                return
            low = loc.lower()
            if low.endswith(".xml"):
                if depth < 3:
                    sub_body = _fetch_url_text(client, loc, deadline, max_chars=6_000_000)
                    harvest_locs(sub_body, depth + 1)
                continue
            maybe_add_page(loc)

    for sm_url in uniq_sm[:22]:
        if len(collected) >= max_return or time.monotonic() > deadline:
            break
        body = _fetch_url_text(client, sm_url, deadline)
        if not body or "<loc" not in body.lower():
            continue
        harvest_locs(body, 0)

    return collected


def _candidate_seed_urls(site: str) -> list[str]:
    """High-value entry points (home + www + chemins contact fréquents)."""
    base = normalize_website_url(site.strip()).rstrip("/")
    if base == EMPTY_VALUE:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        key = _canonical_visit_key(u)
        if key in seen or not _host_fetch_allowed(u):
            return
        seen.add(key)
        out.append(key)

    for origin_root in _origin_roots(base):
        add(origin_root)
        prefix = origin_root if origin_root.endswith("/") else origin_root + "/"
        for sub in SITE_SEED_SUBPATHS:
            u = urljoin(prefix, sub.lstrip("/")).rstrip("/")
            add(u)
    return out


def _link_is_priority(url: str) -> bool:
    low = url.lower()
    return any(k in low for k in PRIORITY_PATH_KEYWORDS)


def discover_same_site_links(
    html: str,
    page_url: str,
    allowed_hosts: set[str],
    *,
    max_links: int = 110,
) -> list[str]:
    """Extract internal http(s) links to the same host set (ordered: pages utiles d'abord)."""
    collected: list[str] = []
    seen: set[str] = set()
    for match in ANCHOR_HREF_RE.finditer(html or ""):
        href = (match.group(1) or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        abs_url = urljoin(page_url, href)
        try:
            parsed = urlparse(abs_url)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"}:
            continue
        host = (parsed.hostname or "").lower()
        if host not in allowed_hosts:
            continue
        path = (parsed.path or "").lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        if any(path.startswith(pref) for pref in SKIP_PATH_PREFIXES):
            continue
        key = _canonical_visit_key(abs_url)
        if key in seen:
            continue
        seen.add(key)
        collected.append(key)
        if len(collected) >= max_links:
            break
    collected.sort(key=lambda u: (0 if _link_is_priority(u) else 1, len(u)))
    return collected


def extract_email_phone_from_html(html: str) -> tuple[str, str]:
    """Best-effort email and phone from raw HTML (JSON-LD, mailto:, tel:, visible text)."""
    ld = _ld_json_blobs(html)
    combined = f"{ld}\n{html}" if ld else html

    email = parse_email(combined)
    if email == EMPTY_VALUE:
        for match in MAILTO_RE.finditer(html):
            candidate = _mailto_to_email(match.group(1))
            if candidate != EMPTY_VALUE:
                email = candidate
                break
    if email == EMPTY_VALUE:
        plain = re.sub(r"<[^>]+>", " ", html or "")
        plain = html_module.unescape(plain)
        plain = re.sub(r"\s+", " ", plain).strip()
        email = parse_email(plain[:400_000])

    phone = parse_whatsapp_from_links(html)
    if phone == EMPTY_VALUE:
        for match in TEL_HREF_RE.finditer(html):
            phone = normalize_whatsapp_number(html_module.unescape(match.group(1)))
            if phone != EMPTY_VALUE:
                break
    if phone == EMPTY_VALUE:
        phone = parse_whatsapp(combined[:250_000])
    if phone == EMPTY_VALUE and ld:
        phone = parse_whatsapp(ld)
    if phone == EMPTY_VALUE:
        plain = re.sub(r"<[^>]+>", " ", html)
        plain = re.sub(r"\s+", " ", plain).strip()
        phone = parse_whatsapp(plain[:200_000])
    return email, phone


def _merge_contact(current: str, found: str) -> str:
    if current and current != EMPTY_VALUE:
        return current
    if found and found != EMPTY_VALUE:
        return found
    return EMPTY_VALUE


def _origin_roots_for_site(base: str) -> list[str]:
    roots: list[str] = []
    seen: set[str] = set()
    for origin in _origin_roots(base):
        key = _canonical_visit_key(origin)
        if key not in seen:
            seen.add(key)
            roots.append(origin.rstrip("/"))
    return roots


def _triple_probe_url_candidates(base: str) -> list[tuple[str, str]]:
    """3 étapes : accueil, contact, mentions / à propos."""
    steps: list[tuple[str, str]] = []
    for origin in _origin_roots_for_site(base):
        prefix = origin if origin.endswith("/") else origin + "/"
        steps.append(("accueil", prefix))
        for sub in WEBSITE_TRIPLE_CONTACT_PATHS:
            steps.append(("contact", urljoin(prefix, sub.lstrip("/")).rstrip("/")))
        for sub in WEBSITE_TRIPLE_LEGAL_PATHS:
            steps.append(("mentions / à propos", urljoin(prefix, sub.lstrip("/")).rstrip("/")))
        break
    return steps


def _http_get_html(client: httpx.Client, url: str, *, per_request: float) -> str:
    try:
        response = client.get(url, timeout=per_request)
    except (httpx.HTTPError, OSError):
        return ""
    if response.status_code >= 400:
        return ""
    body = (response.text or "")[:900_000]
    if len(body) < 25:
        return ""
    ctype = (response.headers.get("content-type") or "").lower()
    if ctype and "html" not in ctype and "text/" not in ctype:
        if not _looks_like_html(body):
            return ""
    return body


def probe_website_three_priority_pages(site_web: str) -> tuple[str, str]:
    """
    Visite 3 types de pages (accueil, contact, mentions) — rapide, avant le crawl BFS.
  """
    if not getattr(settings, "scraper_website_priority_three_pages", True):
        return EMPTY_VALUE, EMPTY_VALUE
    base = normalize_website_url((site_web or "").strip())
    if base == EMPTY_VALUE or not _host_fetch_allowed(base):
        return EMPTY_VALUE, EMPTY_VALUE

    per_request = website_triple_probe_per_request_seconds()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8",
    }
    email_out, phone_out = EMPTY_VALUE, EMPTY_VALUE
    candidates = _triple_probe_url_candidates(base)
    if not candidates:
        return EMPTY_VALUE, EMPTY_VALUE

    home_url = candidates[0][1]
    contact_urls = [u for label, u in candidates if label == "contact"]
    legal_urls = [u for label, u in candidates if label == "mentions / à propos"]

    steps: list[tuple[str, list[str]]] = [
        ("Site web 1/3 — page d'accueil", [home_url]),
        ("Site web 2/3 — page contact", contact_urls[:12]),
        ("Site web 3/3 — mentions légales / à propos", legal_urls[:12]),
    ]

    try:
        with httpx.Client(
            follow_redirects=True,
            headers=headers,
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=0),
        ) as client:
            for step_idx, (message, urls) in enumerate(steps, start=1):
                scraper_progress(
                    phase="website_probe",
                    fraction=0.0,
                    message=message,
                )
                for url in urls:
                    if email_out != EMPTY_VALUE:
                        return email_out, phone_out
                    body = _http_get_html(client, url, per_request=per_request)
                    if not body:
                        continue
                    e, p = extract_email_phone_from_html(body)
                    email_out = _merge_contact(email_out, e)
                    phone_out = _merge_contact(phone_out, p)
                    if email_out != EMPTY_VALUE:
                        break
    except Exception:
        return email_out, phone_out
    return email_out, phone_out


def supplement_contacts_from_website(site_web: str, *, timeout: float | None = None) -> tuple[str, str]:
    """
    Parcourt le site (même domaine, BFS limité) pour trouver e-mail / téléphone utiles à l'outreach.

    Contrôlé par ``SCRAPER_FETCH_CONTACTS_FROM_WEBSITE``, ``SCRAPER_SITE_CRAWL_MAX_PAGES``,
    ``SCRAPER_SITE_CRAWL_TOTAL_SECONDS``, ``SCRAPER_SITE_DEEP_SITEMAP``,
    ``SCRAPER_SITE_DEEP_PROBE_EXTRA``. Avec ``SCRAPER_FAST_MODE=true``, le budget effectif
    est réduit automatiquement (voir ``scraper.timing``).
    Résultat mis en cache : si plusieurs profils partagent le même domaine (ex. agence),
    le crawl n'est effectué qu'une seule fois par run.
    """
    if not settings.scraper_fetch_contacts_from_website:
        return EMPTY_VALUE, EMPTY_VALUE
    base = normalize_website_url((site_web or "").strip())
    if base == EMPTY_VALUE or not _host_fetch_allowed(base):
        return EMPTY_VALUE, EMPTY_VALUE

    with _site_email_cache_lock:
        if base in _site_email_cache:
            return _site_email_cache[base]

    email_out, phone_out = probe_website_three_priority_pages(base)
    if email_out != EMPTY_VALUE:
        with _site_email_cache_lock:
            _site_email_cache[base] = (email_out, phone_out)
        return email_out, phone_out
    if not site_crawl_bfs_enabled():
        with _site_email_cache_lock:
            _site_email_cache[base] = (email_out, phone_out)
        return email_out, phone_out

    max_pages = site_crawl_max_pages_effective()
    total_budget = site_crawl_total_seconds_effective()
    per_request = timeout if timeout is not None else min(22.0, max(8.0, total_budget / max(max_pages // 3, 1)))

    allowed_hosts = _allowed_hosts_for_site(base)
    seeds = _candidate_seed_urls(base)
    queue: deque[str] = deque()
    queued: set[str] = set()
    for s in seeds:
        key = _canonical_visit_key(s)
        if key not in queued:
            queued.add(key)
            queue.append(key)

    visited: set[str] = set()
    pages = 0
    deadline = time.monotonic() + total_budget

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8",
    }

    try:
        with httpx.Client(
            timeout=per_request,
            follow_redirects=True,
            headers=headers,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=0),
        ) as client:
            if settings.scraper_site_deep_sitemap:
                for sm_u in _collect_sitemap_priority_urls(client, base, allowed_hosts, deadline):
                    sk = _canonical_visit_key(sm_u)
                    if sk in visited or sk in queued:
                        continue
                    queued.add(sk)
                    queue.appendleft(sk)

            while queue and pages < max_pages and time.monotonic() < deadline:
                url = queue.popleft()
                key = _canonical_visit_key(url)
                if key in visited:
                    continue
                visited.add(key)
                try:
                    response = client.get(url)
                except (httpx.HTTPError, OSError):
                    continue
                if response.status_code >= 400:
                    continue
                body = (response.text or "")[:900_000]
                if len(body) < 25:
                    continue
                ctype = (response.headers.get("content-type") or "").lower()
                if ctype and "html" not in ctype and "text/" not in ctype and "xml" not in ctype:
                    if not _looks_like_html(body):
                        continue

                pages += 1
                final_url = str(response.url)
                e, p = extract_email_phone_from_html(body)
                email_out = _merge_contact(email_out, e)
                phone_out = _merge_contact(phone_out, p)
                if email_out != EMPTY_VALUE:
                    break

                for link in discover_same_site_links(body, final_url, allowed_hosts, max_links=110):
                    lk = _canonical_visit_key(link)
                    if lk in visited or lk in queued:
                        continue
                    queued.add(lk)
                    if _link_is_priority(link):
                        queue.appendleft(link)
                    else:
                        queue.append(link)

            if settings.scraper_site_deep_probe_extra and email_out == EMPTY_VALUE:
                for origin in _origin_roots(base):
                    if time.monotonic() >= deadline:
                        break
                    prefix = origin if origin.endswith("/") else origin + "/"
                    for sub in SITE_EXTRA_PROBE_SUBPATHS:
                        if time.monotonic() >= deadline:
                            break
                        probe_url = urljoin(prefix, sub.lstrip("/")).rstrip("/")
                        pk = _canonical_visit_key(probe_url)
                        if pk in visited:
                            continue
                        visited.add(pk)
                        try:
                            response = client.get(probe_url)
                        except (httpx.HTTPError, OSError):
                            continue
                        if response.status_code >= 400:
                            continue
                        body = (response.text or "")[:900_000]
                        if len(body) < 25:
                            continue
                        ctype = (response.headers.get("content-type") or "").lower()
                        if ctype and "html" not in ctype and "text/" not in ctype and "xml" not in ctype:
                            if not _looks_like_html(body):
                                continue
                        e2, p2 = extract_email_phone_from_html(body)
                        email_out = _merge_contact(email_out, e2)
                        phone_out = _merge_contact(phone_out, p2)
                        if email_out != EMPTY_VALUE:
                            break
                    if email_out != EMPTY_VALUE:
                        break
    except Exception:
        with _site_email_cache_lock:
            _site_email_cache[base] = (email_out, phone_out)
        return email_out, phone_out
    with _site_email_cache_lock:
        _site_email_cache[base] = (email_out, phone_out)
    return email_out, phone_out
