from __future__ import annotations

import logging
from collections.abc import Callable

from config import settings
from scraper.contact_recovery import (
    contact_trace,
    guess_emails_from_name_and_domain,
    merge_contact_layers,
    pick_guessed_email,
    split_display_name_for_guess,
)
from scraper.extractors import parse_domain, parse_linkedin_card
from scraper.linkedin_contacts import (
    expand_hidden_contact_details,
    open_contact_via_linkedin_three_dots_menu,
    extract_company_from_page,
    extract_contacts_from_company_page,
    extract_contacts_from_page,
    extract_contacts_from_profile_surfaces,
    extract_website_from_linkedin_contact_panel,
    first_experience_company_href,
    wait_for_contact_modal_email_hints,
    wait_for_linkedin_contact_shell,
)
from scraper.models import EMPTY_VALUE, ScraperRecord, is_empty_value
from scraper.site_contact_fetch import supplement_contacts_from_website
from scraper import timing as scrape_timing

log = logging.getLogger(__name__)

_HEADLINE_SELECTORS = (
    "div.ph5 div.text-body-medium",
    "div.mt2 div.text-body-medium",
    "div[data-view-name='profile-top-card'] div.text-body-medium",
)
_LOCATION_SELECTORS = (
    "div.ph5 span.text-body-small.inline",
    "div.mt2 span.text-body-small",
    "div[data-view-name='profile-top-card'] span.text-body-small",
)


def _ensure_linkedin_session(page) -> None:
    url = page.url.lower()
    if any(token in url for token in ("login", "signup", "checkpoint", "uas/login")):
        raise RuntimeError(
            "Session LinkedIn expirée ou invalide pendant l'ouverture d'un profil. "
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


def _has_email_and_whatsapp(email: str, whatsapp: str) -> bool:
    return not is_empty_value(email) and not is_empty_value(whatsapp)


def _merge_field(current: str, candidate: str) -> str:
    if current and current != EMPTY_VALUE:
        return current
    if candidate and candidate != EMPTY_VALUE:
        return candidate
    return EMPTY_VALUE


def _pause_between_profiles(page) -> None:
    page.wait_for_timeout(scrape_timing.linkedin_inter_profile_pause_ms())


def _scroll_profile(page) -> None:
    for _ in range(scrape_timing.linkedin_scroll_passes()):
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900))")
        page.wait_for_timeout(scrape_timing.linkedin_scroll_step_ms())


def _open_contact_overlay(page, profile_url: str, *, quick: bool = False) -> None:
    overlay_url = f"{profile_url.rstrip('/')}/overlay/contact-info/"
    current_url = (page.url or "").lower()

    # Déjà sur l'overlay : juste expand + retour immédiat — pas de navigation inutile.
    if "/overlay/contact-info" in current_url:
        expand_hidden_contact_details(page)
        return

    click_wait = (
        scrape_timing.linkedin_quick_after_contact_click_ms()
        if quick
        else scrape_timing.linkedin_after_contact_click_ms()
    )
    goto_wait = (
        scrape_timing.linkedin_quick_after_overlay_goto_ms()
        if quick
        else scrape_timing.linkedin_after_overlay_goto_ms()
    )
    shell_timeout = (
        scrape_timing.linkedin_quick_contact_shell_timeout_ms()
        if quick
        else None
    )
    on_profile = "/in/" in current_url and "/overlay/" not in current_url
    if on_profile and open_contact_via_linkedin_three_dots_menu(page, kind="people"):
        page.wait_for_timeout(click_wait)
        try:
            wait_for_linkedin_contact_shell(page, timeout_ms=shell_timeout)
            expand_hidden_contact_details(page)
            return
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    for selector in (
        "a[href*='/overlay/contact-info/']",
        "a#top-card-text-details-contact-info",
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
            locator.click(timeout=3000 if quick else 4000)
            page.wait_for_timeout(click_wait)
            wait_for_linkedin_contact_shell(page, timeout_ms=shell_timeout)
            expand_hidden_contact_details(page)
            return
        except Exception:
            continue
    page.goto(overlay_url, wait_until="domcontentloaded", timeout=60000 if quick else 90000)
    page.wait_for_timeout(goto_wait)
    wait_for_linkedin_contact_shell(page, timeout_ms=shell_timeout)
    expand_hidden_contact_details(page)


def _goto_profile_if_needed(page, profile_url: str) -> None:
    if "/in/" in (page.url or "").lower() and "/overlay/" not in (page.url or "").lower():
        return
    page.goto(profile_url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(scrape_timing.linkedin_after_profile_revisit_ms())


def _trace(profile_url: str, event: str, **kw: object) -> None:
    if settings.scraper_contact_trace_logs:
        contact_trace(log, profile_url, event, **kw)


def _record_needs_email_hunt(record: ScraperRecord) -> bool:
    """True tant qu'il manque l'e-mail (ou WhatsApp si priorité e-mail désactivée)."""
    if is_empty_value(record.email):
        return True
    if not getattr(settings, "scraper_linkedin_prioritize_email", True):
        return is_empty_value(record.whatsapp)
    return False


def _linkedin_surface_contacts(page) -> dict[str, str]:
    if not settings.scraper_profile_wide_contact_scan:
        return {}
    try:
        return extract_contacts_from_profile_surfaces(page)
    except Exception:
        return {}


def _close_contact_overlay(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(180 if scrape_timing.scraper_fast_mode() else 320)
    except Exception:
        pass


def _guess_email_require_mx() -> bool:
    require_mx = bool(settings.scraper_guess_email_require_mx)
    if scrape_timing.scraper_fast_mode() and getattr(
        settings, "scraper_guess_email_relaxed_mx_in_fast_mode", True
    ):
        return False
    return require_mx


def _apply_website_email_guess(
    record: ScraperRecord,
    *,
    email: str,
    whatsapp: str,
    site_web: str,
    domaine: str,
) -> tuple[str, str, str, str]:
    """Site web (3 pages rapides) puis e-mails probables prenom.nom@domaine."""
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

    if settings.scraper_guess_contact_emails and is_empty_value(email):
        dom = (domaine or "").strip().lower()
        if dom in ("", EMPTY_VALUE):
            dom = parse_domain(site_web)
        if dom and dom != EMPTY_VALUE:
            first, last = split_display_name_for_guess(record.nom)
            candidates = guess_emails_from_name_and_domain(first, last, dom)
            guessed = pick_guessed_email(candidates, require_mx=_guess_email_require_mx())
            email = _merge_field(email, guessed)
    return email, whatsapp, site_web, domaine


def enrich_linkedin_profile_quick(page, record: ScraperRecord) -> ScraperRecord:
    """Ouverture profil + panneau coordonnées (sans crawl site complet)."""
    profile_url = (record.link or "").rstrip("/")
    if not profile_url:
        return record

    page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(scrape_timing.linkedin_quick_profile_load_ms())
    _ensure_linkedin_session(page)
    _scroll_profile(page)
    headline = _first_visible_text(page, _HEADLINE_SELECTORS)
    location = _first_visible_text(page, _LOCATION_SELECTORS)
    surface = _linkedin_surface_contacts(page)

    _open_contact_overlay(page, profile_url, quick=True)
    page.wait_for_timeout(scrape_timing.linkedin_quick_after_modal_open_ms())
    wait_for_linkedin_contact_shell(page, timeout_ms=scrape_timing.linkedin_quick_contact_shell_timeout_ms())
    expand_hidden_contact_details(page)
    wait_for_contact_modal_email_hints(
        page,
        max_ms=scrape_timing.linkedin_quick_email_paint_max_ms(),
    )
    expand_hidden_contact_details(page)
    modal_contacts = extract_contacts_from_page(page)
    merged = merge_contact_layers(modal_contacts, surface)
    parsed = parse_linkedin_card("\n".join(part for part in (headline, location) if part))

    return ScraperRecord(
        nom=_merge_field(record.nom, parsed["nom"]),
        email=merged.get("email", EMPTY_VALUE),
        whatsapp=merged.get("whatsapp", EMPTY_VALUE),
        pays=_merge_field(record.pays, parsed["pays"] or location),
        entreprise=_merge_field(
            record.entreprise,
            _merge_field(parsed["entreprise"], merged.get("entreprise", EMPTY_VALUE)),
        ),
        poste=_merge_field(record.poste, parsed["poste"] or headline),
        domaine=_merge_field(
            merged.get("domaine", EMPTY_VALUE),
            parse_domain(merged.get("site_web", EMPTY_VALUE)),
        ),
        site_web=merged.get("site_web", EMPTY_VALUE),
        about=record.about,
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_profile_fast_email(page, record: ScraperRecord) -> ScraperRecord:
    """
    Recherche rapide d'e-mail : LinkedIn (profil + coordonnées) puis site / entreprise / guess.
    """
    record = enrich_linkedin_profile_quick(page, record)
    if not _record_needs_email_hunt(record):
        return record
    return enrich_linkedin_profile_supplement(page, record)


def enrich_linkedin_profile_supplement(page, record: ScraperRecord) -> ScraperRecord:
    """Complète un profil déjà validé (site web, guess e-mail, fallback entreprise)."""
    profile_url = (record.link or "").rstrip("/")
    if not profile_url:
        return record

    email = record.email
    whatsapp = record.whatsapp
    site_web = record.site_web
    domaine = record.domaine
    entreprise = record.entreprise

    if is_empty_value(site_web):
        try:
            # Essayer d'abord le panneau déjà ouvert sans re-navigation
            revealed_no_goto = extract_website_from_linkedin_contact_panel(page)
            if not is_empty_value(revealed_no_goto):
                site_web = revealed_no_goto
                if is_empty_value(domaine):
                    domaine = parse_domain(site_web)
                _trace(profile_url, "website_from_open_panel", site_web=site_web)
            else:
                _goto_profile_if_needed(page, profile_url)
                _open_contact_overlay(page, profile_url, quick=True)
                page.wait_for_timeout(scrape_timing.linkedin_quick_after_modal_open_ms())
                wait_for_linkedin_contact_shell(
                    page,
                    timeout_ms=scrape_timing.linkedin_quick_contact_shell_timeout_ms(),
                )
                expand_hidden_contact_details(page)
                revealed = extract_website_from_linkedin_contact_panel(page)
                if not is_empty_value(revealed):
                    site_web = revealed
                    if is_empty_value(domaine):
                        domaine = parse_domain(site_web)
                    _trace(profile_url, "website_from_contact_panel", site_web=site_web)
        except Exception as exc:
            _trace(profile_url, "website_panel_failed", error=str(exc))

    if is_empty_value(email) and settings.scraper_profile_wide_contact_scan:
        try:
            _goto_profile_if_needed(page, profile_url)
            _close_contact_overlay(page)
            _scroll_profile(page)
            surf = _linkedin_surface_contacts(page)
            email = _merge_field(email, surf.get("email", EMPTY_VALUE))
            whatsapp = _merge_field(whatsapp, surf.get("whatsapp", EMPTY_VALUE))
            site_web = _merge_field(site_web, surf.get("site_web", EMPTY_VALUE))
            domaine = _merge_field(domaine, surf.get("domaine", EMPTY_VALUE))
            if not is_empty_value(surf.get("email", EMPTY_VALUE)):
                _trace(profile_url, "email_from_profile_rescan")
        except Exception as exc:
            _trace(profile_url, "profile_rescan_failed", error=str(exc))

    if settings.scraper_linkedin_company_contact_fallback and is_empty_value(email):
        _goto_profile_if_needed(page, profile_url)
        company_url = first_experience_company_href(page)
        if company_url:
            overlay = f"{company_url.rstrip('/')}/overlay/contact-info/"
            try:
                page.goto(overlay, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(scrape_timing.linkedin_company_overlay_wait_ms())
                wait_for_linkedin_contact_shell(page)
                company_contacts = extract_contacts_from_company_page(page)
                email = _merge_field(email, company_contacts["email"])
                whatsapp = _merge_field(whatsapp, company_contacts["whatsapp"])
                site_web = _merge_field(site_web, company_contacts["site_web"])
                domaine = _merge_field(domaine, company_contacts["domaine"])
            except Exception as exc:
                _trace(profile_url, "company_overlay_failed", error=str(exc), company=company_url)

    email, whatsapp, site_web, domaine = _apply_website_email_guess(
        record,
        email=email,
        whatsapp=whatsapp,
        site_web=site_web,
        domaine=domaine,
    )

    return ScraperRecord(
        nom=record.nom,
        email=email,
        whatsapp=whatsapp,
        pays=record.pays,
        entreprise=entreprise,
        poste=record.poste,
        domaine=domaine,
        site_web=site_web,
        about=record.about,
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_profile_page(page, record: ScraperRecord) -> ScraperRecord:
    profile_url = (record.link or "").rstrip("/")
    if not profile_url:
        return record

    skip_revisit = bool(getattr(settings, "scraper_skip_profile_revisit", True))

    page.goto(profile_url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(scrape_timing.linkedin_after_profile_load_ms())
    _ensure_linkedin_session(page)
    _scroll_profile(page)
    headline = _first_visible_text(page, _HEADLINE_SELECTORS)
    location = _first_visible_text(page, _LOCATION_SELECTORS)
    profile_company = extract_company_from_page(page, headline=headline)

    surface_pre: dict[str, str] = {}
    if settings.scraper_profile_wide_contact_scan:
        try:
            surface_pre = extract_contacts_from_profile_surfaces(page)
        except Exception as exc:
            _trace(profile_url, "surface_pre_failed", error=str(exc))

    _open_contact_overlay(page, profile_url)
    page.wait_for_timeout(scrape_timing.linkedin_after_modal_open_ms())
    wait_for_linkedin_contact_shell(page)
    expand_hidden_contact_details(page)
    wait_for_contact_modal_email_hints(
        page,
        max_ms=scrape_timing.linkedin_email_paint_max_ms(),
    )
    expand_hidden_contact_details(page)
    _ensure_linkedin_session(page)
    modal_contacts = extract_contacts_from_page(page)

    if not skip_revisit:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(scrape_timing.linkedin_after_profile_revisit_ms())
        headline = _first_visible_text(page, _HEADLINE_SELECTORS) or headline
        location = _first_visible_text(page, _LOCATION_SELECTORS) or location

    parsed = parse_linkedin_card("\n".join(part for part in (headline, location) if part))
    entreprise = profile_company
    if entreprise == EMPTY_VALUE:
        entreprise = parsed["entreprise"]
    if entreprise == EMPTY_VALUE:
        entreprise = modal_contacts["entreprise"]
    if entreprise == EMPTY_VALUE:
        entreprise = record.entreprise

    surface_post: dict[str, str] = {}
    pre_email = surface_pre.get("email", EMPTY_VALUE)
    pre_wa = surface_pre.get("whatsapp", EMPTY_VALUE)
    need_surface_post = settings.scraper_profile_wide_contact_scan and not _has_email_and_whatsapp(
        _merge_field(modal_contacts.get("email", EMPTY_VALUE), pre_email),
        _merge_field(modal_contacts.get("whatsapp", EMPTY_VALUE), pre_wa),
    )
    if need_surface_post:
        try:
            _goto_profile_if_needed(page, profile_url)
            surface_post = extract_contacts_from_profile_surfaces(page)
        except Exception as exc:
            _trace(profile_url, "surface_post_failed", error=str(exc))

    merged = merge_contact_layers(modal_contacts, surface_post, surface_pre)
    email = merged["email"]
    whatsapp = merged["whatsapp"]
    site_web = merged["site_web"]
    domaine = merged["domaine"]
    if merged.get("entreprise") and merged["entreprise"] != EMPTY_VALUE:
        entreprise = _merge_field(entreprise, merged["entreprise"])

    if settings.scraper_linkedin_company_contact_fallback and email == EMPTY_VALUE:
        _goto_profile_if_needed(page, profile_url)
        company_url = first_experience_company_href(page)
        if company_url:
            overlay = f"{company_url.rstrip('/')}/overlay/contact-info/"
            try:
                page.goto(overlay, wait_until="domcontentloaded", timeout=75000)
                page.wait_for_timeout(scrape_timing.linkedin_company_overlay_wait_ms())
                wait_for_linkedin_contact_shell(page)
                company_contacts = extract_contacts_from_company_page(page)
                merged_co = merge_contact_layers(merged, company_contacts)
                email = merged_co["email"]
                whatsapp = merged_co["whatsapp"]
                site_web = _merge_field(site_web, merged_co["site_web"])
                domaine = _merge_field(domaine, merged_co["domaine"])
                _trace(
                    profile_url,
                    "company_overlay_merged",
                    company=company_url,
                    email=email,
                    whatsapp=whatsapp,
                )
            except Exception as exc:
                _trace(profile_url, "company_overlay_failed", error=str(exc), company=company_url)

    if settings.scraper_fetch_contacts_from_website and site_web != EMPTY_VALUE:
        need_site = email == EMPTY_VALUE
        if not getattr(settings, "scraper_linkedin_prioritize_email", True):
            need_site = need_site or whatsapp == EMPTY_VALUE
        if need_site:
            web_email, web_phone = supplement_contacts_from_website(site_web)
            email = _merge_field(email, web_email)
            whatsapp = _merge_field(whatsapp, web_phone)
            _trace(profile_url, "website_supplement", web_email=web_email, web_phone=web_phone)
        if domaine == EMPTY_VALUE:
            d = parse_domain(site_web)
            if d != EMPTY_VALUE:
                domaine = d

    if settings.scraper_guess_contact_emails and email == EMPTY_VALUE:
        dom = (domaine or "").strip().lower()
        if dom in ("", EMPTY_VALUE):
            dom = parse_domain(site_web)
        if dom and dom != EMPTY_VALUE:
            first, last = split_display_name_for_guess(_merge_field(record.nom, parsed["nom"]))
            candidates = guess_emails_from_name_and_domain(first, last, dom)
            guessed = pick_guessed_email(candidates, require_mx=_guess_email_require_mx())
            email = _merge_field(email, guessed)
            if guessed != EMPTY_VALUE:
                _trace(profile_url, "email_guessed", email=guessed, domain=dom)

    if email == EMPTY_VALUE:
        _trace(
            profile_url,
            "email_still_empty",
            had_modal=bool((modal_contacts.get("text") or "").strip()),
            wide_scan=settings.scraper_profile_wide_contact_scan,
            site_web=site_web,
            website_fetch=settings.scraper_fetch_contacts_from_website,
            guess_emails=settings.scraper_guess_contact_emails,
            domaine=domaine,
        )

    return ScraperRecord(
        nom=_merge_field(record.nom, parsed["nom"]),
        email=email,
        whatsapp=whatsapp,
        pays=_merge_field(record.pays, parsed["pays"] or location),
        entreprise=entreprise,
        poste=_merge_field(record.poste, parsed["poste"] or headline),
        domaine=domaine,
        site_web=site_web,
        about=record.about,
        app=record.app,
        link=record.link,
    )


def enrich_linkedin_people_records(
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

    enrichable = sum(1 for r in records if "/in/" in (r.link or "").lower())
    done_profiles = 0
    enriched: list[ScraperRecord] = []
    try:
        for index, record in enumerate(records):
            if "/in/" not in (record.link or "").lower():
                enriched.append(record)
                continue
            if index:
                _pause_between_profiles(work_page)
            done_profiles += 1
            if on_step and enrichable:
                on_step(done_profiles, enrichable)
            enriched.append(enrich_linkedin_profile_page(work_page, record))
    finally:
        if owns_page:
            work_page.close()
    return enriched
