from __future__ import annotations

import re
from collections.abc import Callable

from config import settings
from scraper.extractors import parse_domain, parse_email, parse_linkedin_company_card
from scraper.linkedin_contacts import (
    collect_company_about_summary,
    collect_company_surface_hrefs,
    collect_company_surface_text,
    expand_hidden_contact_details,
    extract_contacts_from_company_page,
    extract_contacts_from_sources,
    extract_website_from_linkedin_contact_panel,
    open_contact_via_linkedin_three_dots_menu,
    wait_for_contact_modal_email_hints,
    wait_for_linkedin_contact_shell,
)
from scraper.contact_recovery import merge_contact_layers
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value
from scraper.site_contact_fetch import supplement_contacts_from_website
from scraper import timing as scrape_timing

COMPANY_NAME_SELECTORS = (
    "h1.org-top-card-summary__title",
    "h1.top-card-layout__title",
    "div[data-view-name='org-name'] h1",
    "main h1",
)

COMPANY_DETAIL_SELECTORS = (
    "div.org-top-card-summary-info-list__info-item",
    "div.org-top-card-summary__info-item",
    "div[data-view-name='org-top-card'] div.text-body-small",
    "div.org-top-card-summary__tagline",
)


def _ensure_linkedin_session(page) -> None:
    url = page.url.lower()
    if any(token in url for token in ("login", "signup", "checkpoint", "uas/login")):
        raise RuntimeError(
            "Session LinkedIn expirée ou invalide pendant l'ouverture d'une entreprise. "
            "Relancez `python outreach.py login linkedin`."
        )


def _first_visible_text(page, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        try:
            text = (locator.inner_text() or "").strip()
        except Exception:
            continue
        if text:
            return text
    return ""


def _merge_field(current: str, candidate: str) -> str:
    if current and current != EMPTY_VALUE:
        return current
    if candidate and candidate != EMPTY_VALUE:
        return candidate
    return EMPTY_VALUE


def _merge_about_snippets(*parts: str) -> str:
    pieces: list[str] = []
    for raw in parts:
        p = (raw or "").strip()
        if not p or p == EMPTY_VALUE:
            continue
        if p not in pieces:
            pieces.append(p)
    merged = " ".join(pieces)
    merged = re.sub(r"\s+", " ", merged).strip()
    return merged[:8000] if merged else EMPTY_VALUE


def _pause_between_companies(page) -> None:
    page.wait_for_timeout(scrape_timing.linkedin_inter_profile_pause_ms())


def _scroll_company_page(page) -> None:
    for _ in range(scrape_timing.linkedin_scroll_passes()):
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900))")
        page.wait_for_timeout(scrape_timing.linkedin_scroll_step_ms())


def _open_company_contact_overlay(page, company_url: str) -> None:
    """Même schéma que les profils : menu ⋯, panneau Coordonnées ou URL /overlay/contact-info/."""
    overlay_url = f"{company_url.rstrip('/')}/overlay/contact-info/"
    on_company = "/company/" in (page.url or "").lower() and "/overlay/" not in (page.url or "").lower()
    if on_company and open_contact_via_linkedin_three_dots_menu(page, kind="companies"):
        page.wait_for_timeout(scrape_timing.linkedin_after_contact_click_ms())
        try:
            wait_for_linkedin_contact_shell(page)
            expand_hidden_contact_details(page)
            return
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    for selector in (
        "a[href*='/overlay/contact-info/']",
        "button:has-text('Coordonnées')",
        "button:has-text('Contact info')",
        "a:has-text('Coordonnées')",
        "a:has-text('Contact info')",
        "button:has-text('Voir les coordonnées')",
        "a:has-text('Voir les coordonnées')",
    ):
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        try:
            locator.click(timeout=5000)
            page.wait_for_timeout(scrape_timing.linkedin_after_contact_click_ms())
            wait_for_linkedin_contact_shell(page)
            expand_hidden_contact_details(page)
            return
        except Exception:
            continue
    page.goto(overlay_url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(scrape_timing.linkedin_after_overlay_goto_ms())
    wait_for_linkedin_contact_shell(page)
    expand_hidden_contact_details(page)


def _record_needs_email_hunt(record: ScraperRecord) -> bool:
    if is_empty_value(record.email):
        return True
    if not getattr(settings, "scraper_linkedin_prioritize_email", True):
        return is_empty_value(record.whatsapp)
    return False


def enrich_linkedin_company_quick(page, record: ScraperRecord) -> ScraperRecord:
    """Page entreprise + coordonnées seulement (pas de page À propos)."""
    company_url = (record.link or "").rstrip("/")
    if not company_url or "/company/" not in company_url.lower():
        return record

    page.goto(company_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(scrape_timing.linkedin_quick_company_page_load_ms())
    _ensure_linkedin_session(page)
    _scroll_company_page(page)
    surface_text = collect_company_surface_text(page)
    surface_hrefs = collect_company_surface_hrefs(page)
    surface = extract_contacts_from_sources(text=surface_text, hrefs=surface_hrefs)
    about_snip = collect_company_about_summary(page)
    if about_snip:
        about_mail = parse_email(about_snip)
        if about_mail != EMPTY_VALUE:
            surface = merge_contact_layers(surface, {"email": about_mail, "whatsapp": EMPTY_VALUE, "site_web": EMPTY_VALUE, "domaine": EMPTY_VALUE, "entreprise": EMPTY_VALUE})

    _open_company_contact_overlay(page, company_url)
    page.wait_for_timeout(scrape_timing.linkedin_quick_after_modal_open_ms())
    wait_for_linkedin_contact_shell(page, timeout_ms=scrape_timing.linkedin_quick_contact_shell_timeout_ms())
    expand_hidden_contact_details(page)
    wait_for_contact_modal_email_hints(
        page,
        max_ms=scrape_timing.linkedin_quick_email_paint_max_ms(),
    )
    expand_hidden_contact_details(page)
    modal = extract_contacts_from_company_page(page)
    contacts = merge_contact_layers(modal, surface)
    name = _first_visible_text(page, COMPANY_NAME_SELECTORS)
    detail = _first_visible_text(page, COMPANY_DETAIL_SELECTORS)
    parsed = parse_linkedin_company_card("\n".join(part for part in (name, detail) if part))
    company_name = _merge_field(record.nom, parsed["nom"] or name)

    return ScraperRecord(
        nom=company_name,
        email=contacts["email"],
        whatsapp=contacts["whatsapp"],
        pays=_merge_field(record.pays, parsed["pays"]),
        entreprise=company_name,
        poste=_merge_field(record.poste, parsed["poste"] or detail),
        domaine=contacts["domaine"],
        site_web=contacts["site_web"],
        about=record.about,
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_company_supplement(page, record: ScraperRecord) -> ScraperRecord:
    company_url = (record.link or "").rstrip("/")
    if not company_url:
        return record
    email = record.email
    whatsapp = record.whatsapp
    site_web = record.site_web
    domaine = record.domaine

    if is_empty_value(site_web):
        try:
            _open_company_contact_overlay(page, company_url)
            page.wait_for_timeout(scrape_timing.linkedin_quick_after_modal_open_ms())
            expand_hidden_contact_details(page)
            revealed = extract_website_from_linkedin_contact_panel(page)
            if not is_empty_value(revealed):
                site_web = revealed
                if is_empty_value(domaine):
                    domaine = parse_domain(site_web)
        except Exception:
            pass

    if is_empty_value(email):
        try:
            about_snip = collect_company_about_summary(page)
            guessed = parse_email(about_snip) if about_snip else EMPTY_VALUE
            email = _merge_field(email, guessed)
        except Exception:
            pass

    if settings.scraper_fetch_contacts_from_website and not is_empty_value(site_web):
        need_site = is_empty_value(email)
        if not getattr(settings, "scraper_linkedin_prioritize_email", True):
            need_site = need_site or is_empty_value(whatsapp)
        if need_site:
            web_email, web_phone = supplement_contacts_from_website(site_web)
            email = _merge_field(email, web_email)
            whatsapp = _merge_field(whatsapp, web_phone)
        if is_empty_value(domaine):
            d = parse_domain(site_web)
            if d != EMPTY_VALUE:
                domaine = d
    return ScraperRecord(
        nom=record.nom,
        email=email,
        whatsapp=whatsapp,
        pays=record.pays,
        entreprise=record.entreprise,
        poste=record.poste,
        domaine=domaine,
        site_web=site_web,
        about=record.about,
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_company_fast_email(page, record: ScraperRecord) -> ScraperRecord:
    """LinkedIn entreprise (page + coordonnées) puis site web rapide si pas d'e-mail."""
    record = enrich_linkedin_company_quick(page, record)
    if not _record_needs_email_hunt(record):
        return record
    return enrich_linkedin_company_supplement(page, record)


def enrich_linkedin_company_page(page, record: ScraperRecord) -> ScraperRecord:
    company_url = (record.link or "").rstrip("/")
    if not company_url or "/company/" not in company_url.lower():
        return record

    page.goto(company_url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(scrape_timing.linkedin_company_page_load_ms())
    _ensure_linkedin_session(page)
    _scroll_company_page(page)
    _open_company_contact_overlay(page, company_url)
    page.wait_for_timeout(scrape_timing.linkedin_company_modal_between_ms())
    wait_for_linkedin_contact_shell(page)
    main_contacts = extract_contacts_from_company_page(page)
    about_main = collect_company_about_summary(page)
    name = _first_visible_text(page, COMPANY_NAME_SELECTORS)
    detail = _first_visible_text(page, COMPANY_DETAIL_SELECTORS)

    email = main_contacts["email"]
    whatsapp = main_contacts["whatsapp"]
    site_web = main_contacts["site_web"]
    domaine = main_contacts["domaine"]
    about_text = about_main

    skip_about = bool(getattr(settings, "scraper_linkedin_skip_company_about_when_contacted", True))
    prioritize_email = bool(getattr(settings, "scraper_linkedin_prioritize_email", True))
    has_email = not is_empty_value(email)
    has_both = has_email and not is_empty_value(whatsapp)
    skip_about_page = skip_about and (has_email if prioritize_email else has_both)
    if not skip_about_page:
        about_url = f"{company_url}/about/"
        page.goto(about_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(scrape_timing.linkedin_company_about_nav_ms())
        _ensure_linkedin_session(page)
        _scroll_company_page(page)
        _open_company_contact_overlay(page, company_url)
        page.wait_for_timeout(scrape_timing.linkedin_company_modal_between_ms())
        wait_for_linkedin_contact_shell(page)
        about_contacts = extract_contacts_from_company_page(page)
        about_detail = collect_company_about_summary(page)
        email = _merge_field(email, about_contacts["email"])
        whatsapp = _merge_field(whatsapp, about_contacts["whatsapp"])
        site_web = _merge_field(site_web, about_contacts["site_web"])
        domaine = _merge_field(domaine, about_contacts["domaine"])
        about_text = _merge_about_snippets(about_main, about_detail)
        page.goto(company_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(scrape_timing.linkedin_company_final_return_ms())
        name = _first_visible_text(page, COMPANY_NAME_SELECTORS) or name
        detail = _first_visible_text(page, COMPANY_DETAIL_SELECTORS) or detail
    parsed = parse_linkedin_company_card("\n".join(part for part in (name, detail) if part))
    company_name = _merge_field(record.nom, parsed["nom"] or name)

    if settings.scraper_fetch_contacts_from_website and site_web != EMPTY_VALUE:
        need_site = email == EMPTY_VALUE
        if not prioritize_email:
            need_site = need_site or whatsapp == EMPTY_VALUE
        if need_site:
            web_email, web_phone = supplement_contacts_from_website(site_web)
            email = _merge_field(email, web_email)
            whatsapp = _merge_field(whatsapp, web_phone)
        if domaine == EMPTY_VALUE:
            d = parse_domain(site_web)
            if d != EMPTY_VALUE:
                domaine = d

    return ScraperRecord(
        nom=company_name,
        email=email,
        whatsapp=whatsapp,
        pays=_merge_field(record.pays, parsed["pays"]),
        entreprise=company_name,
        poste=_merge_field(record.poste, parsed["poste"] or detail),
        domaine=domaine,
        site_web=site_web,
        about=_merge_field(record.about, about_text),
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_company_records(
    context,
    records: list[ScraperRecord],
    *,
    page=None,
    on_step: Callable[[int, int], None] | None = None,
) -> list[ScraperRecord]:
    work_page = page
    owns_page = work_page is None
    if owns_page:
        work_page = context.new_page()
    assert work_page is not None

    enrichable = sum(1 for r in records if "/company/" in (r.link or "").lower())
    done_companies = 0
    enriched: list[ScraperRecord] = []
    try:
        for index, record in enumerate(records):
            if "/company/" not in (record.link or "").lower():
                enriched.append(record)
                continue
            if index:
                _pause_between_companies(work_page)
            done_companies += 1
            if on_step and enrichable:
                on_step(done_companies, enrichable)
            enriched.append(enrich_linkedin_company_page(work_page, record))
    finally:
        if owns_page:
            work_page.close()
    return enriched
