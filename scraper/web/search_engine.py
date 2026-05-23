"""
Recherche web type Google / Bing / DuckDuckGo pour découvrir des URLs.

Providers :
- ``google_cse`` : API Google Custom Search (recommandé si clés .env)
- ``google_playwright`` : google.com dans Chromium (le plus proche d'une recherche manuelle)
- ``google`` : HTML google.com (httpx, souvent bloqué)
- ``bing`` : Bing HTML
- ``duckduckgo`` : DuckDuckGo HTML
- ``auto`` : essaie dans l'ordre ci-dessus selon la config
"""

from __future__ import annotations

import html as html_module
import logging
import re
from collections.abc import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from config import settings
from scraper.web.stability import max_discovery_results_per_query, pause_between_web_requests

log = logging.getLogger(__name__)

# Dernier message d'erreur Google CSE (pour affichage utilisateur).
_last_cse_error: str = ""


def last_google_cse_error() -> str:
    return _last_cse_error

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_GOOGLE_URL_Q_RE = re.compile(r"/url\?q=([^&\"'>]+)", re.IGNORECASE)
_GOOGLE_HREF_RE = re.compile(
    r'<a[^>]+href="(/url\?q=[^"]+|https?://[^"]+)"[^>]*>',
    re.IGNORECASE,
)
_BING_CITE_RE = re.compile(r"<cite[^>]*>([^<]+)</cite>", re.IGNORECASE)
_BING_RESULT_RE = re.compile(
    r'<li class="b_algo"[\s\S]*?<a[^>]+href="(https?://[^"]+)"',
    re.IGNORECASE,
)
_DDG_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"',
    re.IGNORECASE,
)
_UDDG_RE = re.compile(r"uddg=([^&\"']+)", re.IGNORECASE)

_BLOCKED_RESULT_HOSTS = (
    "google.com",
    "google.fr",
    "gstatic.com",
    "googleusercontent.com",
    "bing.com",
    "duckduckgo.com",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "x.com",
)


def web_search_urls(query: str, *, max_results: int | None = None) -> list[str]:
    """Lance une recherche web et retourne les URLs des résultats (ordre SERP)."""
    q = (query or "").strip()
    if not q:
        return []
    cap = max_results if max_results is not None else max_discovery_results_per_query()
    cap = max(1, min(cap, 50))
    provider = (getattr(settings, "scraper_web_search_provider", "auto") or "auto").strip().lower()
    if provider == "auto":
        return _search_auto(q, max_results=cap)
    if provider in {"google", "google_html"}:
        return _search_google_html(q, max_results=cap)
    if provider == "google_playwright":
        return _search_google_playwright(q, max_results=cap)
    if provider == "google_cse":
        urls = _search_google_cse(q, max_results=cap)
        if urls:
            return urls
        return _search_fallback_after_cse(q, max_results=cap)
    if provider == "bing":
        return _search_bing(q, max_results=cap)
    if provider == "duckduckgo":
        return _search_duckduckgo_html(q, max_results=cap)
    raise RuntimeError(
        f"Provider inconnu : {provider}. "
        "Valeurs : auto, google, google_playwright, google_cse, bing, duckduckgo"
    )


def _search_auto(query: str, *, max_results: int) -> list[str]:
    """Bing (navigateur) en priorité — CSE souvent indisponible pour nouveaux comptes."""
    urls = _search_bing(query, max_results=max_results)
    if urls:
        return urls
    if getattr(settings, "scraper_web_google_use_playwright", True):
        urls = _search_google_playwright(query, max_results=max_results)
        if urls:
            return urls
    key = (getattr(settings, "scraper_web_google_api_key", "") or "").strip()
    cx = (getattr(settings, "scraper_web_google_cx", "") or "").strip()
    if key and cx:
        urls = _search_google_cse(query, max_results=max_results)
        if urls:
            return urls
    for fn in (_search_google_html, _search_duckduckgo_html):
        urls = fn(query, max_results=max_results)
        if urls:
            log.info("Recherche web : fallback %s → %d URL(s)", fn.__name__, len(urls))
            return urls
    return []


def _search_bing(query: str, *, max_results: int) -> list[str]:
    """Bing : Playwright d'abord (fiable), puis HTML httpx."""
    for fn in (_search_bing_playwright, _search_bing_html):
        urls = fn(query, max_results=max_results)
        if urls:
            return urls
    return []


def _http_client() -> httpx.Client:
    timeout = float(getattr(settings, "scraper_web_http_timeout_seconds", 25.0) or 25.0)
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        },
    )


def _clean_result_url(raw: str) -> str:
    href = html_module.unescape((raw or "").strip())
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "/url?q=" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "q" in qs and qs["q"]:
            href = unquote(qs["q"][0])
    if "duckduckgo.com/l/" in href and "uddg=" in href:
        match = _UDDG_RE.search(href)
        if match:
            href = unquote(match.group(1))
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.netloc.lower().replace("www.", "")
    if any(blocked in host for blocked in _BLOCKED_RESULT_HOSTS):
        return ""
    path = (parsed.path or "").rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _dedupe_urls(urls: Iterable[str], *, max_results: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = _clean_result_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= max_results:
            break
    return out


def _search_fallback_after_cse(query: str, *, max_results: int) -> list[str]:
    """Si CSE échoue ou renvoie 0 résultat, essaie Bing puis Playwright."""
    global _last_cse_error
    hint = _last_cse_error or "aucun résultat"
    log.warning("Google CSE indisponible (%s) — repli Bing / navigateur.", hint)
    urls = _search_bing(query, max_results=max_results)
    if urls:
        return urls
    urls = _search_google_playwright(query, max_results=max_results)
    if urls:
        return urls
    return _search_duckduckgo_html(query, max_results=max_results)


def _search_google_cse(query: str, *, max_results: int) -> list[str]:
    global _last_cse_error
    _last_cse_error = ""
    key = (getattr(settings, "scraper_web_google_api_key", "") or "").strip()
    cx = (getattr(settings, "scraper_web_google_cx", "") or "").strip()
    if not key or not cx:
        _last_cse_error = "SCRAPER_WEB_GOOGLE_API_KEY ou SCRAPER_WEB_GOOGLE_CX manquant"
        log.debug("Google CSE : %s", _last_cse_error)
        return []
    pause_between_web_requests()
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),
        "hl": getattr(settings, "scraper_web_google_hl", "fr") or "fr",
    }
    gl = (getattr(settings, "scraper_web_google_gl", "") or "").strip()
    if gl:
        params["gl"] = gl
    try:
        with _http_client() as client:
            response = client.get(url, params=params)
            data = response.json()
            if response.status_code != 200:
                err = data.get("error") or {}
                _last_cse_error = str(err.get("message") or response.status_code)
                log.warning("Google CSE HTTP %s : %s", response.status_code, _last_cse_error)
                return []
            response.raise_for_status()
    except Exception as exc:
        _last_cse_error = str(exc)
        log.warning("Google CSE échec : %s", exc)
        return []
    items = data.get("items") or []
    if not items:
        _last_cse_error = (
            "0 résultat — activez « Rechercher sur tout le Web » sur programmablesearchengine.google.com"
        )
    raw = [str(item.get("link") or "") for item in items if item.get("link")]
    return _dedupe_urls(raw, max_results=max_results)


def _google_search_url(query: str, *, num: int) -> str:
    hl = getattr(settings, "scraper_web_google_hl", "fr") or "fr"
    gl = (getattr(settings, "scraper_web_google_gl", "") or "").strip()
    params = f"q={quote_plus(query)}&num={min(num, 20)}&hl={hl}"
    if gl:
        params += f"&gl={gl}"
    return f"https://www.google.com/search?{params}"


def _search_google_html(query: str, *, max_results: int) -> list[str]:
    pause_between_web_requests()
    try:
        with _http_client() as client:
            response = client.get(_google_search_url(query, num=max_results))
            response.raise_for_status()
            body = response.text
    except Exception as exc:
        log.warning("Google HTML échec : %s", exc)
        return []
    if "unusual traffic" in body.lower() or "captcha" in body.lower():
        log.warning("Google HTML : CAPTCHA / trafic inhabituel — utilisez google_playwright ou google_cse")
        return []
    raw: list[str] = []
    for match in _GOOGLE_URL_Q_RE.finditer(body):
        raw.append(unquote(match.group(1)))
    for match in _GOOGLE_HREF_RE.finditer(body):
        raw.append(match.group(1))
    return _dedupe_urls(raw, max_results=max_results)


def _search_google_playwright(query: str, *, max_results: int) -> list[str]:
    from playwright.sync_api import sync_playwright

    pause_between_web_requests()
    raw: list[str] = []
    headless = bool(getattr(settings, "scraper_headless", False))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(user_agent=_USER_AGENT, locale="fr-FR")
            page = context.new_page()
            page.goto(
                _google_search_url(query, num=max_results),
                wait_until="domcontentloaded",
                timeout=90000,
            )
            page.wait_for_timeout(2500)
            if page.locator("text=unusual traffic").count() or page.locator("form#captcha").count():
                browser.close()
                log.warning(
                    "Google Playwright : CAPTCHA. Connectez-vous manuellement une fois "
                    "ou configurez SCRAPER_WEB_GOOGLE_API_KEY + SCRAPER_WEB_GOOGLE_CX."
                )
                return []
            for anchor in page.locator('a[href*="http"]').all():
                href = anchor.get_attribute("href") or ""
                if href:
                    raw.append(href)
            browser.close()
    except Exception as exc:
        log.warning("Google Playwright échec : %s", exc)
        return []
    return _dedupe_urls(raw, max_results=max_results)


def _bing_cite_to_url(cite: str) -> str:
    """Convertit l'affichage Bing <cite> en URL cliquable."""
    text = html_module.unescape((cite or "").strip())
    if not text:
        return ""
    text = re.sub(r"\s*›\s*", "/", text)
    text = text.replace(" ", "")
    if not text.startswith("http"):
        text = "https://" + text.lstrip("/")
    return _clean_result_url(text)


def _search_bing_playwright(query: str, *, max_results: int) -> list[str]:
    """Bing dans Chromium — extraction des <cite> (URLs affichées)."""
    from playwright.sync_api import sync_playwright

    pause_between_web_requests()
    raw: list[str] = []
    headless = bool(getattr(settings, "scraper_headless", True))
    url = (
        f"https://www.bing.com/search?q={quote_plus(query)}"
        f"&count={min(max_results, 30)}&cc=FR&setlang=fr-FR"
    )
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page(user_agent=_USER_AGENT, locale="fr-FR")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2500)
            for cite in page.locator("cite").all_inner_texts():
                u = _bing_cite_to_url(cite)
                if u:
                    raw.append(u)
            browser.close()
    except Exception as exc:
        log.warning("Bing Playwright échec : %s", exc)
        return []
    return _dedupe_urls(raw, max_results=max_results)


def _search_bing_html(query: str, *, max_results: int) -> list[str]:
    pause_between_web_requests()
    url = (
        f"https://www.bing.com/search?q={quote_plus(query)}"
        f"&count={min(max_results, 30)}&cc=FR&setlang=fr"
    )
    try:
        with _http_client() as client:
            response = client.get(url)
            response.raise_for_status()
            body = response.text
    except Exception as exc:
        log.warning("Bing HTML échec : %s", exc)
        return []
    raw: list[str] = []
    for cite in _BING_CITE_RE.findall(body):
        u = _bing_cite_to_url(cite)
        if u:
            raw.append(u)
    for m in _BING_RESULT_RE.finditer(body):
        raw.append(m.group(1))
    return _dedupe_urls(raw, max_results=max_results)


def _search_duckduckgo_html(query: str, *, max_results: int) -> list[str]:
    pause_between_web_requests()
    try:
        with _http_client() as client:
            response = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "wt-wt"},
            )
            response.raise_for_status()
            body = response.text
    except Exception as exc:
        log.warning("DuckDuckGo échec : %s", exc)
        return []
    raw = [m.group(1) for m in _DDG_RESULT_RE.finditer(body)]
    return _dedupe_urls(raw, max_results=max_results)
