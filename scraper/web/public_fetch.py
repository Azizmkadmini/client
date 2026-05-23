"""Fetch HTTP public (sans Playwright) pour extraire texte / meta."""

from __future__ import annotations

import re
from html import unescape

import httpx

from config import settings
from scraper.extractors import (
    guess_company,
    guess_role,
    parse_domain,
    parse_email,
    parse_website,
    parse_whatsapp,
)
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_META_CONTENT_RE = re.compile(
    r'<meta[^>]+(?:property|name)\s*=\s*["\'](?:og:description|description)["\'][^>]*'
    r'content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_META_ALT_RE = re.compile(
    r'content\s*=\s*["\']([^"\']+)["\'][^>]*(?:property|name)\s*=\s*["\'](?:og:description|description)["\']',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE | re.DOTALL)


def fetch_public_html(url: str) -> str:
    timeout = float(getattr(settings, "scraper_web_http_timeout_seconds", 25.0) or 25.0)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _meta_description(html: str) -> str:
    for pattern in (_META_CONTENT_RE, _META_ALT_RE):
        match = pattern.search(html)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _title_text(html: str) -> str:
    match = _TITLE_RE.search(html)
    if match:
        return unescape(match.group(1)).strip()
    return ""


def instagram_record_from_public_page(handle: str, app: str) -> ScraperRecord | None:
    """
    Tente une lecture publique de instagram.com/{handle} (souvent limitée sans session).
    Retourne None si page vide / mur de connexion.
    """
    url = f"https://www.instagram.com/{handle}/"
    try:
        html = fetch_public_html(url)
    except Exception:
        return None
    low = html.lower()
    if "login" in low and "instagram" in low and len(html) < 80_000:
        if 'content="Instagram"' in low or "/accounts/login" in low:
            return None
    bio = _meta_description(html)
    title = _title_text(html)
    text = f"{title}\n{bio}".strip()
    if not text or handle.lower() not in text.casefold():
        return None
    name = title.split("•")[0].split("(")[0].strip() or handle
    if name.lower().endswith("instagram"):
        name = handle
    record = ScraperRecord(
        nom=name,
        email=parse_email(text),
        whatsapp=parse_whatsapp(text),
        pays=EMPTY_VALUE,
        entreprise=guess_company(text),
        poste=guess_role(text),
        domaine=parse_domain(text),
        site_web=parse_website(text),
        about=bio[:800] if bio else EMPTY_VALUE,
        app=app,
        link=url,
    )
    if (
        is_empty_value(record.nom)
        and is_empty_value(record.email)
        and is_empty_value(record.whatsapp)
    ):
        return None
    return record
