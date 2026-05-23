"""Pauses et budgets effectifs du scraper (mode rapide vs stable LinkedIn)."""

from __future__ import annotations

from config import settings

try:
    from scraper.linkedin_stability import (
        effective_search_scroll_rounds,
        inter_profile_pause_jitter_ms,
        linkedin_fast_timing_allowed,
    )
except ImportError:
    effective_search_scroll_rounds = None  # type: ignore[assignment]
    inter_profile_pause_jitter_ms = None  # type: ignore[assignment]
    linkedin_fast_timing_allowed = None  # type: ignore[assignment]


def scraper_fast_mode() -> bool:
    if linkedin_fast_timing_allowed is not None:
        return linkedin_fast_timing_allowed()
    return bool(getattr(settings, "scraper_fast_mode", False))


def _scale_ms(ms: int, *, floor: int = 200) -> int:
    if not scraper_fast_mode():
        return ms
    return max(floor, int(ms * 0.32))


def linkedin_inter_profile_pause_ms() -> int:
    if inter_profile_pause_jitter_ms is not None:
        return inter_profile_pause_jitter_ms()
    pause_s = float(getattr(settings, "scraper_inter_profile_pause_seconds", 1.8) or 1.8)
    pause_s = max(0.25, min(pause_s, 6.0))
    ms = int(pause_s * 1000)
    if scraper_fast_mode():
        return max(280, int(ms * 0.5))
    return ms


def linkedin_quick_inter_profile_pause_ms() -> int:
    if scraper_fast_mode():
        return 260
    return 450


def linkedin_scroll_passes() -> int:
    return 2 if scraper_fast_mode() else 3


def linkedin_search_scroll_passes() -> int:
    if effective_search_scroll_rounds is not None:
        return effective_search_scroll_rounds()
    return 1 if scraper_fast_mode() else 3


def linkedin_scroll_step_ms() -> int:
    return _scale_ms(650, floor=400)


def linkedin_quick_profile_load_ms() -> int:
    return _scale_ms(1200, floor=500)


def linkedin_after_profile_load_ms() -> int:
    return _scale_ms(2800, floor=900)


def linkedin_after_contact_click_ms() -> int:
    return _scale_ms(1800, floor=700)


def linkedin_quick_after_contact_click_ms() -> int:
    return _scale_ms(1000, floor=450)


def linkedin_after_overlay_goto_ms() -> int:
    return _scale_ms(2200, floor=750)


def linkedin_quick_after_overlay_goto_ms() -> int:
    return _scale_ms(1100, floor=450)


def linkedin_after_modal_open_ms() -> int:
    return _scale_ms(2000, floor=700)


def linkedin_quick_after_modal_open_ms() -> int:
    return _scale_ms(800, floor=350)


def linkedin_after_profile_revisit_ms() -> int:
    return _scale_ms(1500, floor=600)


def linkedin_company_overlay_wait_ms() -> int:
    return _scale_ms(2000, floor=750)


def linkedin_company_return_wait_ms() -> int:
    return _scale_ms(1100, floor=500)


def linkedin_email_paint_max_ms() -> int:
    base = max(0, int(getattr(settings, "scraper_linkedin_contact_email_paint_max_ms", 4000)))
    if scraper_fast_mode():
        return max(800, min(2200, base // 2 + 120))
    return base if base > 0 else 4500


def linkedin_quick_email_paint_max_ms() -> int:
    if scraper_fast_mode():
        return 900
    return 1500


def linkedin_contact_shell_timeout_ms() -> int:
    return 7000 if scraper_fast_mode() else 12000


def linkedin_quick_contact_shell_timeout_ms() -> int:
    return 5000 if scraper_fast_mode() else 9000


def modal_email_hint_poll_step_ms() -> int:
    return 180 if scraper_fast_mode() else 320


def site_crawl_max_pages_effective() -> int:
    p = max(5, int(settings.scraper_site_crawl_max_pages))
    if scraper_fast_mode():
        return max(5, min(18, int(p * 0.45)))
    return p


def site_crawl_total_seconds_effective() -> float:
    t = max(15.0, float(settings.scraper_site_crawl_total_seconds))
    if scraper_fast_mode():
        return max(15.0, min(42.0, t * 0.38))
    return t


def website_triple_probe_per_request_seconds() -> float:
    base = max(15.0, float(settings.scraper_site_crawl_total_seconds))
    if scraper_fast_mode():
        return min(9.0, max(5.0, base / 6))
    return min(14.0, max(6.0, base / 4))


def site_crawl_bfs_enabled() -> bool:
    if not scraper_fast_mode():
        return True
    return bool(getattr(settings, "scraper_site_crawl_bfs_in_fast_mode", False))


def collectors_instagram_first_wait_ms() -> int:
    return _scale_ms(3200, floor=1200)


def collectors_instagram_profile_wait_ms() -> int:
    return _scale_ms(1800, floor=750)


def collectors_linkedin_search_wait_ms() -> int:
    return _scale_ms(2800, floor=900)


def collectors_scroll_results_step_ms() -> int:
    return _scale_ms(900, floor=500)


def linkedin_company_page_load_ms() -> int:
    return _scale_ms(2800, floor=900)


def linkedin_quick_company_page_load_ms() -> int:
    return _scale_ms(1200, floor=500)


def linkedin_company_modal_between_ms() -> int:
    return _scale_ms(1600, floor=650)


def linkedin_company_about_nav_ms() -> int:
    return _scale_ms(2000, floor=750)


def linkedin_company_final_return_ms() -> int:
    return _scale_ms(1400, floor=600)
