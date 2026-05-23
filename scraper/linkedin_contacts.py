from __future__ import annotations

import re
import time
from urllib.parse import unquote

from scraper.extractors import (
    extract_company_from_headline,
    normalize_email,
    normalize_whatsapp_number,
    parse_domain,
    parse_email,
    normalize_website_url,
    parse_website,
    parse_whatsapp,
    parse_whatsapp_from_links,
    unwrap_linkedin_redirect,
    website_from_href,
)
from config import settings
from scraper.models import EMPTY_VALUE
from scraper.timing import linkedin_contact_shell_timeout_ms, modal_email_hint_poll_step_ms

MAILTO_PATTERN = re.compile(r"mailto:([^\"'\s>?#]+)", re.IGNORECASE)
TEL_PATTERN = re.compile(r"tel:([^\"'\s>?#]+)", re.IGNORECASE)
WHATSAPP_HOST_PATTERN = re.compile(
    r"(wa\.me/|api\.whatsapp\.com/send|web\.whatsapp\.com/send|whatsapp\.com/send)",
    re.IGNORECASE,
)

CONTACT_SECTION_SELECTORS = (
    "div.artdeco-modal__content",
    "div.artdeco-modal[role='dialog']",
    "[role='dialog']",
    "div[role='dialog']",
    "section.pv-contact-info",
    "div.pv-contact-info",
    "div.pv-contact-info__ci-container",
    "section[data-view-name='profile-card-contact-info']",
    "div[data-view-name='contact-info']",
    "div[data-view-name='org-contact-info']",
)


def _contact_root_selectors(page) -> tuple[str, ...]:
    """Sur la page dédiée /overlay/contact-info/, le contenu utile est souvent dans `main`."""
    try:
        current = (page.url or "").lower()
    except Exception:
        current = ""
    if "/overlay/contact-info" in current:
        return (*CONTACT_SECTION_SELECTORS, "main")
    return CONTACT_SECTION_SELECTORS


def wait_for_linkedin_contact_shell(page, timeout_ms: int | None = None) -> None:
    """Attendre le panneau coordonnées (modal ou page overlay)."""
    effective = linkedin_contact_shell_timeout_ms() if timeout_ms is None else timeout_ms
    try:
        page.wait_for_selector(
            "div.artdeco-modal__content, section.pv-contact-info, "
            "div.pv-contact-info, div.pv-contact-info__ci-container, main",
            timeout=effective,
        )
    except Exception:
        return

CONTACT_LABELS: dict[str, tuple[str, ...]] = {
    "email": (
        "email",
        "e-mail",
        "courriel",
        "courrier électronique",
        "courrier electronique",
        "adresse e-mail",
        "adresse email",
        "adresse courriel",
        "adresse mail",
    ),
    "phone": (
        "téléphone",
        "telephone",
        "phone",
        "mobile",
        "numéro de téléphone",
        "numero de telephone",
        "tel",
    ),
    "website": (
        "site web",
        "website",
        "portfolio",
        "blog",
        "personal website",
        "site internet",
        "lien du site web",
        "bouton du site web",
        "lien externe",
        "external link",
        "company website",
        "consulter le site web",
        "consulter le site internet",
        "visit website",
        "view website",
    ),
    "company": (
        "entreprise",
        "company",
        "current company",
        "entreprise actuelle",
        "société",
        "societe",
    ),
}

COMPANY_LINK_NOISE = re.compile(
    r"^(?:voir plus|see more|voir la page entreprise|company page|logo|image)$",
    re.IGNORECASE,
)

COMPANY_LINK_SELECTORS = (
    "section#experience a[href*='/company/']",
    "section[data-view-name='profile-card-experience'] a[href*='/company/']",
    "div[data-view-name='profile-top-card'] a[href*='/company/']",
    "a[href*='/company/']",
)


def _normalize_contact_text_hyphens(blob: str) -> str:
    """Uniformise tirets / espaces insécables (titres « E‑mail » LinkedIn)."""
    if not blob:
        return blob
    out = blob
    for ch in ("\u2011", "\u2010", "\u2013", "\u2014", "\u2212"):
        out = out.replace(ch, "-")
    return out.replace("\u00a0", " ").replace("\u202f", " ")


def _linkedin_coordonees_email(text: str) -> str:
    """
    Cas fréquent LinkedIn FR / overlay : libellé « E-mail » / « Courriel » puis adresse à la ligne
    suivante ou sur la même ligne (ex. profil Ilyes / Rihab).
    """
    raw = _normalize_contact_text_hyphens((text or "").strip())
    if not raw:
        return EMPTY_VALUE
    try:
        import unicodedata

        raw = unicodedata.normalize("NFKC", raw)
    except Exception:
        pass

    # E-mail / Courriel sur une ligne, adresse sur la suivante
    block_pat = re.compile(
        r"(?im)^\s*(?:e[-\s]?mail|courriel|courrier\s+électronique|courrier\s+electronique|"
        r"adresse\s+courriel|adresse\s+e-?mail)\s*:?\s*$"
        r"\s*(?:\n\s*)+"
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    )
    m = block_pat.search(raw)
    if m:
        e = normalize_email(m.group(1).strip().rstrip(".,);"))
        if e != EMPTY_VALUE:
            return e

    # Même ligne : E-mail : user@…
    same_pat = re.compile(
        r"(?im)^\s*(?:e[-\s]?mail|courriel)\s*:\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\s*$",
    )
    for sm in same_pat.finditer(raw):
        e = normalize_email(sm.group(1).strip().rstrip(".,);"))
        if e != EMPTY_VALUE:
            return e

    return EMPTY_VALUE


def _pick_first(*values: str) -> str:
    for value in values:
        if value and value != EMPTY_VALUE:
            return value
    return EMPTY_VALUE


def _contact_from_labeled_text(text: str, field: str) -> str:
    labels = CONTACT_LABELS.get(field, ())
    text = _normalize_contact_text_hyphens((text or "").strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # LinkedIn often renders "Email: user@domain.com" on one line; older logic only
    # looked at following lines after a standalone label.
    sorted_labels = sorted(labels, key=len, reverse=True)
    label_alt = "|".join(re.escape(lab) for lab in sorted_labels)
    same_line = re.compile(rf"^(?:{label_alt})\s*[:\s\-–—]+\s*(.+)$", re.IGNORECASE)
    for line in lines:
        match_sl = same_line.match(line)
        if not match_sl:
            continue
        rest = match_sl.group(1).strip()
        if field == "email":
            value = parse_email(rest)
        elif field == "phone":
            value = parse_whatsapp(rest)
        else:
            value = parse_website(rest)
        if value != EMPTY_VALUE:
            return value

    for index, line in enumerate(lines):
        label = line.lower().rstrip(":")
        if label not in labels:
            continue
        for candidate in lines[index + 1 : index + 5]:
            if field == "email":
                value = parse_email(candidate)
            elif field == "phone":
                value = parse_whatsapp(candidate)
            else:
                value = parse_website(candidate)
            if value != EMPTY_VALUE:
                return value
    return EMPTY_VALUE


def _email_from_href(href: str) -> str:
    if not href:
        return EMPTY_VALUE
    href = unwrap_linkedin_redirect(href.strip())
    lowered = href.lower()
    if lowered.startswith("mailto:"):
        candidate = href.split(":", 1)[1].split("?")[0].strip()
        candidate = unquote(candidate)
        return normalize_email(candidate)
    match = MAILTO_PATTERN.search(href)
    if match:
        return normalize_email(unquote(match.group(1)))
    return EMPTY_VALUE


def _phone_from_href(href: str) -> str:
    if not href:
        return EMPTY_VALUE
    href = unwrap_linkedin_redirect(href.strip())
    lowered = href.lower()
    if WHATSAPP_HOST_PATTERN.search(lowered):
        w = parse_whatsapp_from_links(href)
        if w != EMPTY_VALUE:
            return w
        digits = re.sub(r"\D", "", href)
        return normalize_whatsapp_number(digits)
    if lowered.startswith("tel:"):
        return normalize_whatsapp_number(href.split(":", 1)[1])
    match = TEL_PATTERN.search(href)
    if match:
        return normalize_whatsapp_number(match.group(1))
    return EMPTY_VALUE


def _website_from_href(href: str) -> str:
    if not href:
        return EMPTY_VALUE
    lowered = href.lower()
    if lowered.startswith(("javascript:", "#", "mailto:", "tel:")):
        return EMPTY_VALUE
    if "linkedin.com" in lowered and "redirect" not in lowered and "redir" not in lowered:
        return EMPTY_VALUE
    return website_from_href(href)


def _company_from_link_href(href: str) -> str:
    if not href or "/company/" not in href:
        return EMPTY_VALUE
    slug = href.split("/company/", 1)[1].split("?")[0].strip("/")
    if not slug or slug.lower() in {"company", "universal-name"}:
        return EMPTY_VALUE
    return slug.replace("-", " ").strip().title()


def _clean_company_name(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate or COMPANY_LINK_NOISE.search(candidate):
        return EMPTY_VALUE
    if candidate.lower() in {"vide", "personnes", "posts", "emplois"}:
        return EMPTY_VALUE
    return candidate


def _company_from_labeled_text(text: str) -> str:
    labels = CONTACT_LABELS.get("company", ())
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        label = line.lower().rstrip(":")
        if label not in labels:
            continue
        for candidate in lines[index + 1 : index + 4]:
            cleaned = _clean_company_name(candidate)
            if cleaned != EMPTY_VALUE:
                return cleaned
    return EMPTY_VALUE


def _company_from_hrefs(hrefs: list[str]) -> str:
    for href in hrefs:
        company = _clean_company_name(_company_from_link_href(href))
        if company != EMPTY_VALUE:
            return company
    return EMPTY_VALUE


def extract_company_from_sources(*, text: str = "", hrefs: list[str] | None = None, headline: str = "") -> str:
    hrefs = hrefs or []
    return _pick_first(
        extract_company_from_headline(headline),
        _company_from_labeled_text(text),
        _company_from_hrefs(hrefs),
        extract_company_from_headline(text),
    )


def _whatsapp_href_priority(href: str) -> int:
    low = (href or "").lower()
    if "wa.me" in low:
        return 0
    if "whatsapp.com" in low and ("send" in low or "phone=" in low):
        return 0
    return 1


def extract_contacts_from_sources(*, text: str = "", hrefs: list[str] | None = None) -> dict[str, str]:
    hrefs = hrefs or []
    hrefs_ordered = sorted(hrefs, key=_whatsapp_href_priority)
    email = _pick_first(
        _linkedin_coordonees_email(text),
        _contact_from_labeled_text(text, "email"),
        *(_email_from_href(href) for href in hrefs_ordered),
        parse_email(text),
    )
    phone = _pick_first(
        *(_phone_from_href(href) for href in hrefs_ordered),
        parse_whatsapp_from_links("\n".join([text, *hrefs_ordered])),
        _contact_from_labeled_text(text, "phone"),
        parse_whatsapp(text),
    )
    site_web = _pick_first(
        *(_website_from_href(href) for href in hrefs_ordered),
        _contact_from_labeled_text(text, "website"),
        parse_website(text),
    )
    domaine = parse_domain(site_web) if site_web != EMPTY_VALUE else EMPTY_VALUE
    return {
        "email": email,
        "whatsapp": phone,
        "site_web": site_web,
        "domaine": domaine,
        "entreprise": extract_company_from_sources(text=text, hrefs=hrefs, headline=""),
        "text": text,
    }


def collect_whatsapp_click_hrefs(page) -> list[str]:
    """Liens <a> explicites vers WhatsApp (hors seul bloc contact LinkedIn)."""
    selectors = (
        "a[href*='wa.me']",
        "a[href*='api.whatsapp.com']",
        "a[href*='web.whatsapp.com/send']",
        "a[href*='whatsapp.com/send']",
    )
    hrefs: list[str] = []
    seen: set[str] = set()
    for sel in selectors:
        try:
            count = min(page.locator(sel).count(), 80)
        except Exception:
            continue
        for i in range(count):
            try:
                raw = page.locator(sel).nth(i).get_attribute("href") or ""
            except Exception:
                continue
            h = unwrap_linkedin_redirect(raw.strip())
            if not h or h in seen:
                continue
            low = h.lower()
            if "wa.me" in low or ("whatsapp.com" in low and ("send" in low or "phone=" in low)):
                seen.add(h)
                hrefs.append(h)
    return hrefs


PROFILE_WIDE_SECTION_SELECTORS = (
    "div[data-view-name='profile-top-card']",
    "section.artdeco-card[data-view-name='profile-card']",
    "section[data-view-name='profile-card-about']",
    "section#about",
    "div[data-view-name='profile-about']",
    "section[data-view-name='profile-card-experience']",
    "section#experience",
    "section[data-view-name='profile-card-recommendations']",
    "section[data-view-name='profile-card-volunteering-experience']",
    "section[data-view-name='profile-card-publications']",
    "section[data-view-name='profile-card-projects']",
    "section[data-view-name='profile-card-education']",
    "section[data-view-name='profile-card-activity']",
    "div[data-view-name='profile-feed']",
)


def collect_profile_wide_text(page, *, max_chars: int = 120_000) -> str:
    """Texte visible About, Expérience, activité, etc. (hors seul bloc coordonnées)."""
    parts: list[str] = []
    seen_hashes: set[int] = set()
    for sel in PROFILE_WIDE_SECTION_SELECTORS:
        loc = page.locator(sel)
        try:
            n = min(loc.count(), 4)
        except Exception:
            continue
        for i in range(n):
            try:
                t = (loc.nth(i).inner_text() or "").strip()
            except Exception:
                continue
            if len(t) < 4:
                continue
            h = hash(t[:2000])
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            parts.append(t)
            if sum(len(p) for p in parts) > max_chars:
                return "\n\n".join(parts)[:max_chars]
    joined = "\n\n".join(parts)
    return joined[:max_chars]


def collect_profile_wide_hrefs(page, *, max_anchors: int = 280) -> list[str]:
    """mailto:, tel:, WhatsApp et liens externes visibles sous ``main``."""
    out: list[str] = []
    seen: set[str] = set()
    try:
        loc = page.locator("main a[href]")
        n = min(loc.count(), max_anchors)
    except Exception:
        return []
    for i in range(n):
        try:
            raw = (loc.nth(i).get_attribute("href") or "").strip()
        except Exception:
            continue
        href = unwrap_linkedin_redirect(raw)
        if not href or href in seen:
            continue
        low = href.lower()
        if low.startswith(("javascript:", "#")):
            continue
        if low.startswith(("mailto:", "tel:")):
            seen.add(href)
            out.append(href)
            continue
        if WHATSAPP_HOST_PATTERN.search(low):
            seen.add(href)
            out.append(href)
    return out


def extract_contacts_from_profile_surfaces(page) -> dict[str, str]:
    """About / expérience / HTML profil (mailto dans le source) pour e-mails et numéros cachés dans le DOM."""
    wide_text = collect_profile_wide_text(page)
    hrefs = collect_profile_wide_hrefs(page)
    hrefs.extend(collect_whatsapp_click_hrefs(page))
    html_mailtos: list[str] = []
    try:
        raw_html = (page.content() or "")[:450_000]
    except Exception:
        raw_html = ""
    for m in MAILTO_PATTERN.finditer(raw_html):
        addr = unquote(m.group(1).split("?", 1)[0].strip())
        if addr:
            html_mailtos.append(f"mailto:{addr}")
    hrefs = list(dict.fromkeys([*hrefs, *html_mailtos]))
    return extract_contacts_from_sources(text=wide_text, hrefs=hrefs)


def first_experience_company_href(page) -> str:
    from scraper.linkedin_search import normalize_linkedin_result_url

    try:
        loc = page.locator(
            "section[data-view-name='profile-card-experience'] a[href*='/company/'], "
            "section#experience a[href*='/company/']"
        ).first
        if loc.count() == 0:
            return ""
        href = (loc.get_attribute("href") or "").strip()
    except Exception:
        return ""
    url = normalize_linkedin_result_url(href, "companies")
    if "/company/" in url.lower():
        return url.rstrip("/")
    return ""


def collect_contact_text(page) -> str:
    chunks: list[str] = []
    for selector in _contact_root_selectors(page):
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        try:
            text = (locator.first.inner_text() or "").strip()
        except Exception:
            continue
        if text:
            chunks.append(text)
    joined = "\n".join(chunks)
    if "@" not in joined:
        fb = _collect_contact_fallback_visible_text(page)
        if fb:
            chunks.append(fb)
    return "\n".join(chunks)


def _collect_contact_fallback_visible_text(page) -> str:
    """Si les sélecteurs classiques sont vides : dialogue modal, puis page overlay Coordonnées."""
    parts: list[str] = []
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    overlay = "/overlay/contact-info" in url
    for sel in (
        "div[role='dialog']",
        "div.artdeco-modal",
        "div.artdeco-modal__content",
        "main",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            t = (loc.inner_text() or "").strip()
        except Exception:
            continue
        if len(t) > 12 and ("@" in t or "mail" in t.lower() or "e-mail" in t.lower() or "courriel" in t.lower()):
            parts.append(t[:35_000])
            break
    if not parts and overlay:
        try:
            t = (page.locator("body").first.inner_text() or "").strip()
            if t and "@" in t:
                parts.append(t[:45_000])
        except Exception:
            pass
    return "\n".join(parts)


def _linkedin_three_dots_menu_enabled() -> bool:
    return bool(getattr(settings, "scraper_linkedin_use_three_dots_menu", True))


def _click_locator_if_visible(page, selector: str, *, timeout: int = 2500) -> bool:
    try:
        loc = page.locator(selector).first
        if loc.count() == 0 or not loc.is_visible():
            return False
        loc.click(timeout=timeout)
        return True
    except Exception:
        return False


def open_contact_via_linkedin_three_dots_menu(page, *, kind: str = "people") -> bool:
    """
    Menu ⋯ (trois points) sur une fiche LinkedIn → entrée « Coordonnées » / Contact info.
    """
    if not _linkedin_three_dots_menu_enabled():
        return False

    if kind == "companies":
        menu_triggers = (
            "div.org-top-card-primary-actions button.artdeco-dropdown__trigger",
            "div.org-top-card-actions button.artdeco-dropdown__trigger",
            "div[data-view-name='organization-top-card'] button.artdeco-dropdown__trigger",
            "main button.artdeco-dropdown__trigger",
        )
    else:
        menu_triggers = (
            "div.pvs-profile-actions button.artdeco-dropdown__trigger",
            "div[data-view-name='profile-actions'] button.artdeco-dropdown__trigger",
            "section.artdeco-card button.artdeco-dropdown__trigger",
            "main button.artdeco-dropdown__trigger",
        )

    common_triggers = (
        "button[aria-label*='actions']",
        "button[aria-label*='Actions']",
        "button[aria-label*='Autres']",
        "button[aria-label*='More']",
    )
    opened_menu = False
    for selector in (*menu_triggers, *common_triggers):
        if _click_locator_if_visible(page, selector):
            page.wait_for_timeout(450)
            opened_menu = True
            break

    if not opened_menu:
        return False

    menu_items = (
        "div.artdeco-dropdown__content a[href*='/overlay/contact-info/']",
        "div.artdeco-dropdown__content-inner a[href*='/overlay/contact-info/']",
        "div.artdeco-dropdown__content a:has-text('Coordonnées')",
        "div.artdeco-dropdown__content a:has-text('Contact info')",
        "div[role='menu'] a[href*='/overlay/contact-info/']",
        "div[role='menuitem']:has-text('Coordonnées')",
        "div[role='menuitem']:has-text('Contact info')",
        "li.artdeco-dropdown__item:has-text('Coordonnées')",
        "li.artdeco-dropdown__item:has-text('Contact info')",
        "button:has-text('Coordonnées')",
        "button:has-text('Contact info')",
        "span:has-text('Coordonnées')",
        "span:has-text('Contact info')",
    )
    for selector in menu_items:
        if _click_locator_if_visible(page, selector):
            page.wait_for_timeout(500)
            return True

    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


_LINKEDIN_WEBSITE_LINK_TEXT_SELECTORS: tuple[str, ...] = (
    "a:has-text('Consulter le site web')",
    "a:has-text('Consulter le site Internet')",
    "a:has-text('Visit website')",
    "a:has-text('View website')",
    "a:has-text('Voir le site web')",
    "section.pv-contact-info a[href*='redir/redirect']",
    "section.pv-contact-info a[href*='linkedin.com/redir']",
    "div.pv-contact-info a[href*='redir/redirect']",
    "motion.div[role='dialog'] a[href*='redir/redirect']",
    "motion.div[role='dialog'] a:has-text('Consulter le site web')",
    "motion.div[role='dialog'] a:has-text('Visit website')",
)


def _website_from_contact_href_raw(href: str) -> str:
    if not href:
        return EMPTY_VALUE
    return website_from_href(unwrap_linkedin_redirect(href.strip()))


def _scoped_website_link_locators(page):
    """Liens site web dans le panneau Coordonnées uniquement."""
    for root in _contact_root_selectors(page):
        for sel in _LINKEDIN_WEBSITE_LINK_TEXT_SELECTORS:
            scoped = sel if root == "main" else f"{root} {sel}"
            try:
                loc = page.locator(scoped).first
                if loc.count() > 0 and loc.is_visible():
                    yield loc
            except Exception:
                continue


def extract_website_from_linkedin_contact_panel(page) -> str:
    """
    Récupère l'URL du site depuis le panneau Coordonnées LinkedIn.
    Lit d'abord les href (redir LinkedIn), puis clique « Consulter le site web » si besoin.
    """
    for loc in _scoped_website_link_locators(page):
        try:
            href = (loc.get_attribute("href") or "").strip()
        except Exception:
            href = ""
        site = _website_from_contact_href_raw(href)
        if site != EMPTY_VALUE:
            return site

    try:
        raw_href = page.evaluate(
            """() => {
                const roots = [
                    "motion.div[role='dialog']",
                    "motion.div[role='dialog'] div.artdeco-modal__content",
                    "div.artdeco-modal__content",
                    "div[role='dialog']",
                    "section.pv-contact-info",
                    "motion.div[role='dialog'] section.pv-contact-info",
                    "div.pv-contact-info",
                    "main",
                ];
                let root = null;
                for (const sel of roots) {
                    root = document.querySelector(sel);
                    if (root) break;
                }
                if (!root) root = document.body;
                const labelRe = /site\\s*web|website|portfolio|visit website|view website/i;
                const clickRe = /consulter le site|visit website|view website|voir le site/i;
                for (const a of root.querySelectorAll("a[href]")) {
                    const href = (a.getAttribute("href") || "").trim();
                    if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) continue;
                    const low = href.toLowerCase();
                    const text = (a.innerText || a.textContent || "").trim();
                    if (low.includes("redir") || low.includes("redirect") || clickRe.test(text) || labelRe.test(text)) {
                        if (low.includes("linkedin.com") && !low.includes("redir") && !low.includes("redirect")) continue;
                        if (!low.includes("linkedin.com") || low.includes("redir") || low.includes("redirect")) {
                            return href;
                        }
                    }
                }
                for (const block of root.querySelectorAll("section, li, div")) {
                    const t = (block.innerText || "").slice(0, 120);
                    if (!labelRe.test(t)) continue;
                    const a = block.querySelector("a[href]");
                    if (a) return (a.getAttribute("href") || "").trim();
                }
                return "";
            }""",
        )
    except Exception:
        raw_href = ""
    site = _website_from_contact_href_raw(str(raw_href or ""))
    if site != EMPTY_VALUE:
        return site

    click_timeout = 2200 if getattr(settings, "scraper_fast_mode", False) else 3500
    for loc in _scoped_website_link_locators(page):
        try:
            href = (loc.get_attribute("href") or "").strip()
            site = _website_from_contact_href_raw(href)
            if site != EMPTY_VALUE:
                return site
        except Exception:
            pass
        try:
            with page.context.expect_page(timeout=click_timeout) as popup_info:
                loc.click(timeout=click_timeout)
            new_tab = popup_info.value
            try:
                new_tab.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            opened = (new_tab.url or "").strip()
            site = normalize_website_url(opened) if opened else EMPTY_VALUE
            try:
                new_tab.close()
            except Exception:
                pass
            if site != EMPTY_VALUE:
                return site
        except Exception:
            try:
                loc.click(timeout=click_timeout, modifiers=["Control"])
            except Exception:
                try:
                    loc.click(timeout=click_timeout)
                except Exception:
                    continue
            try:
                href = (loc.get_attribute("href") or "").strip()
            except Exception:
                href = ""
            site = _website_from_contact_href_raw(href)
            if site != EMPTY_VALUE:
                return site
    return EMPTY_VALUE


def expand_hidden_contact_details(page) -> None:
    """Clique « Voir plus » / See more dans le panneau coordonnées (e-mail parfois masqué derrière « … »)."""
    selectors = (
        "div.artdeco-modal button:has-text('Voir plus')",
        "div[role='dialog'] button:has-text('Voir plus')",
        "button:has-text('Voir plus')",
        "button:has-text('See more')",
        "button:has-text('Show more')",
        "a:has-text('Voir plus')",
        "a:has-text('See more')",
        "section.pv-contact-info button.artdeco-button--muted",
    )
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.click(timeout=2500)
            page.wait_for_timeout(350)
        except Exception:
            continue


def wait_for_contact_modal_email_hints(page, *, max_ms: int) -> None:
    """
    LinkedIn hydrate parfois l'e-mail / mailto quelques centaines de ms après l'ouverture du modal.
    Boucle courte jusqu'à voir ``@`` ou ``mailto`` dans le texte du panneau contact, ou timeout.
    """
    if max_ms <= 0:
        return
    deadline = time.monotonic() + max_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            blob = collect_contact_text(page)
        except Exception:
            blob = ""
        low = blob.lower()
        if "@" in blob or "mailto:" in low:
            return
        try:
            page.wait_for_timeout(modal_email_hint_poll_step_ms())
        except Exception:
            return


def collect_contact_hrefs(page) -> list[str]:
    hrefs: list[str] = []
    for selector in _contact_root_selectors(page):
        try:
            anchors = page.locator(f"{selector} a[href]").all()
        except Exception:
            continue
        for anchor in anchors:
            try:
                href = anchor.get_attribute("href") or ""
            except Exception:
                continue
            if href:
                hrefs.append(href)
    hrefs.extend(_collect_dom_mailto_hrefs_scoped(page))
    return hrefs


def _collect_dom_mailto_hrefs_scoped(page) -> list[str]:
    """mailto: dans le dialogue Coordonnées (évite le bruit du fil d'actualité sur /in/…)."""
    try:
        raw = page.evaluate(
            """() => {
                let root = document.querySelector("div[role='dialog']");
                if (!root) root = document.querySelector("div.artdeco-modal");
                if (!root) root = document.querySelector("main");
                if (!root) root = document.body;
                const out = [];
                root.querySelectorAll("a[href]").forEach((a) => {
                    const v = (a.getAttribute("href") || "").trim();
                    if (v.toLowerCase().startsWith("mailto:")) out.push(v);
                });
                return [...new Set(out)];
            }""",
        )
    except Exception:
        return []
    if not raw:
        return []
    return [str(h) for h in raw if h]


def collect_contact_inner_html(page, *, max_total: int = 140_000) -> str:
    """HTML du panneau Coordonnées (souvent l'e-mail est dans le DOM même si le texte plat est coupé)."""
    parts: list[str] = []
    total = 0
    for selector in _contact_root_selectors(page):
        try:
            loc = page.locator(selector).first
            if loc.count() == 0:
                continue
            html = loc.evaluate("el => (el && el.outerHTML) ? el.outerHTML : ''") or ""
        except Exception:
            continue
        if not html:
            continue
        parts.append(html)
        total += len(html)
        if total >= max_total:
            break
    joined = "\n".join(parts)
    return joined[:max_total]


def extract_contacts_from_page(page) -> dict[str, str]:
    text = collect_contact_text(page)
    html_blob = collect_contact_inner_html(page)
    combined_text = "\n\n".join(part for part in (text, html_blob) if part)
    hrefs = collect_contact_hrefs(page)
    hrefs.extend(collect_whatsapp_click_hrefs(page))
    hrefs = list(dict.fromkeys(hrefs))
    contacts = extract_contacts_from_sources(text=combined_text, hrefs=hrefs)
    panel_site = extract_website_from_linkedin_contact_panel(page)
    if panel_site != EMPTY_VALUE:
        contacts["site_web"] = _pick_first(panel_site, contacts.get("site_web", EMPTY_VALUE))
        contacts["domaine"] = parse_domain(contacts["site_web"])
    return contacts


COMPANY_SURFACE_TEXT_SELECTORS = (
    "main",
    "div[data-view-name='org-about-module']",
    "section.org-layout-about",
    "div.org-about-module",
    "div.artdeco-card.org-about-module",
    "div[data-view-name='org-top-card']",
    "div[data-view-name='org-sticky-top-card']",
)


def collect_company_surface_text(page) -> str:
    """Aggregate visible copy from company home / about (not profile contact modals)."""
    chunks: list[str] = []
    seen_hashes: set[int] = set()
    for selector in COMPANY_SURFACE_TEXT_SELECTORS:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 8)
        except Exception:
            continue
        for i in range(count):
            try:
                text = (locator.nth(i).inner_text() or "").strip()
            except Exception:
                continue
            if len(text) < 20:
                continue
            key = hash(text[:500])
            if key in seen_hashes:
                continue
            seen_hashes.add(key)
            chunks.append(text)
    joined = "\n\n".join(chunks)
    return joined[:100_000]


def collect_company_surface_hrefs(page) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    roots = (
        "main",
        "div[data-view-name='org-top-card']",
        "div[data-view-name='org-sticky-top-card']",
        "footer",
    )
    for root in roots:
        loc = page.locator(f"{root} a[href]")
        try:
            n = min(loc.count(), 320)
        except Exception:
            continue
        for i in range(n):
            try:
                raw = (loc.nth(i).get_attribute("href") or "").strip()
            except Exception:
                continue
            if not raw or raw in seen:
                continue
            href = unwrap_linkedin_redirect(raw)
            lowered = href.lower()
            if lowered.startswith(("javascript:", "#")):
                continue
            if lowered.startswith(("mailto:", "tel:")):
                collected.append(href)
                seen.add(raw)
                continue
            if WHATSAPP_HOST_PATTERN.search(lowered):
                collected.append(href)
                seen.add(raw)
                continue
            if not lowered.startswith("http"):
                continue
            if "linkedin.com" in lowered:
                if "redir" in lowered or "redirect" in lowered:
                    collected.append(href)
                    seen.add(raw)
                continue
            collected.append(href)
            seen.add(raw)
    return collected


def extract_contacts_from_company_page(page) -> dict[str, str]:
    modal_text = collect_contact_text(page)
    modal_hrefs = collect_contact_hrefs(page)
    surface_text = collect_company_surface_text(page)
    surface_hrefs = collect_company_surface_hrefs(page)
    text = "\n\n".join(part for part in (modal_text, surface_text) if part)
    hrefs = list(
        dict.fromkeys([*modal_hrefs, *surface_hrefs, *collect_whatsapp_click_hrefs(page)]),
    )
    contacts = extract_contacts_from_sources(text=text, hrefs=hrefs)
    panel_site = extract_website_from_linkedin_contact_panel(page)
    if panel_site != EMPTY_VALUE:
        contacts["site_web"] = _pick_first(panel_site, contacts.get("site_web", EMPTY_VALUE))
        contacts["domaine"] = parse_domain(contacts["site_web"])
    return contacts


def collect_company_about_summary(page) -> str:
    """Plain-text snippet from company About / Info blocks."""
    prefer_selectors = (
        "div[data-view-name='org-about-module']",
        "section.org-layout-about",
        "div.org-about-module",
        "div.artdeco-card.org-about-module",
    )
    chunks: list[str] = []
    for sel in prefer_selectors:
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            t = (loc.inner_text() or "").strip()
        except Exception:
            continue
        if len(t) > 40:
            chunks.append(t)
    if not chunks:
        loc = page.locator("main").first
        if loc.count():
            try:
                t = (loc.inner_text() or "").strip()
            except Exception:
                t = ""
            if len(t) > 80:
                chunks.append(t[:12_000])
    blob = "\n\n".join(chunks)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:8000] if blob else ""


def collect_profile_text(page) -> str:
    chunks: list[str] = []
    for selector in (
        "main",
        "section#about",
        "section#experience",
        "section[data-view-name='profile-card-about']",
        "section[data-view-name='profile-card-experience']",
    ):
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        try:
            text = (locator.first.inner_text() or "").strip()
        except Exception:
            continue
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def extract_company_from_page(page, *, headline: str = "") -> str:
    hrefs: list[str] = []
    for selector in COMPANY_LINK_SELECTORS:
        try:
            anchors = page.locator(selector).all()
        except Exception:
            continue
        for anchor in anchors:
            href = anchor.get_attribute("href") or ""
            visible = _clean_company_name((anchor.inner_text() or "").strip())
            company = _pick_first(visible, _company_from_link_href(href))
            if company != EMPTY_VALUE:
                return company
            if href:
                hrefs.append(href)
    text = collect_profile_text(page)
    return extract_company_from_sources(text=text, hrefs=hrefs, headline=headline)
