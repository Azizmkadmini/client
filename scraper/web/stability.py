"""Pauses et limites pour les requêtes web (hors Playwright)."""

from __future__ import annotations

import random
import time

from config import settings


def pause_between_web_requests() -> None:
    base = float(getattr(settings, "scraper_web_pause_between_requests_seconds", 2.0) or 2.0)
    base = max(1.0, min(base, 15.0))
    time.sleep(base * random.uniform(0.9, 1.15))


def max_discovery_results_per_query() -> int:
    configured = int(getattr(settings, "scraper_web_max_results_per_query", 15) or 15)
    return max(5, min(configured, 40))


def max_queries_per_run() -> int:
    configured = int(getattr(settings, "scraper_web_max_queries_per_run", 4) or 4)
    return max(1, min(configured, 12))
