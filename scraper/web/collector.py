"""Point d'entrée collecte web LinkedIn / Instagram."""

from __future__ import annotations

from config import settings
from scraper.models import SearchRequest, ScraperRecord
from scraper.site_contact_fetch import clear_site_email_cache
from scraper.web.sites import collect_web_sites


def collect_web(request: SearchRequest) -> list[ScraperRecord]:
    """Google → sites web → contacts. Commande CLI : ``web-run`` (pas LinkedIn)."""
    if not getattr(settings, "scraper_web_discovery_enabled", True):
        raise RuntimeError(
            "Collecte web désactivée (SCRAPER_WEB_DISCOVERY_ENABLED=false)."
        )
    clear_site_email_cache()
    return collect_web_sites(request)
