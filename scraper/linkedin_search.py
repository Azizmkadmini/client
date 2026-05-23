from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from scraper.extractors import parse_linkedin_card, parse_linkedin_company_card
from scraper.models import EMPTY_VALUE, ScraperRecord

# Catégories proposées par le dashboard (recherche ciblée).
DASHBOARD_LINKEDIN_SCOPE_KEYS: tuple[str, ...] = ("people", "companies")

LINKEDIN_SCOPE_LABELS: dict[str, str] = {
    "people": "Personnes",
    "posts": "Posts",
    "jobs": "Emplois",
    "companies": "Entreprises",
    "groups": "Groupes",
    "products": "Produits",
    "events": "Événements",
    "schools": "Écoles",
    "services": "Services",
    "courses": "Cours",
}

LINKEDIN_SCOPE_PATHS: dict[str, str] = {
    "people": "people",
    "posts": "content",
    "jobs": "jobs",
    "companies": "companies",
    "groups": "groups",
    "products": "products",
    "events": "events",
    "schools": "schools",
    "services": "services",
    "courses": "learning",
}

LINKEDIN_SCOPE_SELECTORS: dict[str, list[str]] = {
    "people": [
        "div[data-view-name='search-result-lockup'] a[href*='/in/']",
        "li.reusable-search__result-container a[href*='/in/']",
        "a[href*='/in/']",
    ],
    "posts": [
        "a[href*='/feed/update/']",
        "a[href*='/posts/']",
        "a[href*='activity-']",
    ],
    "jobs": [
        "a[href*='/jobs/view/']",
        "a[href*='/jobs/search/']",
    ],
    "companies": [
        "a[href*='/company/']",
    ],
    "groups": [
        "a[href*='/groups/']",
    ],
    "products": [
        "a[href*='/products/']",
    ],
    "events": [
        "a[href*='/events/']",
    ],
    "schools": [
        "a[href*='/school/']",
    ],
    "services": [
        "a[href*='/services/']",
    ],
    "courses": [
        "a[href*='/learning/']",
    ],
}

LINKEDIN_SCOPE_WAIT_SELECTORS: dict[str, str] = {
    "people": "a[href*='/in/']",
    "posts": "a[href*='/feed/update/'], a[href*='/posts/']",
    "jobs": "a[href*='/jobs/view/']",
    "companies": "a[href*='/company/']",
    "groups": "a[href*='/groups/']",
    "products": "a[href*='/products/']",
    "events": "a[href*='/events/']",
    "schools": "a[href*='/school/']",
    "services": "a[href*='/services/']",
    "courses": "a[href*='/learning/']",
}


def resolve_linkedin_scopes(scopes: list[str] | tuple[str, ...] | None) -> list[str]:
    requested: list[str] = []
    for scope in scopes or ():
        for part in str(scope).split(","):
            token = part.strip().lower()
            if token:
                requested.append(token)
    if not requested or "all" in requested:
        return list(LINKEDIN_SCOPE_PATHS.keys())
    unknown = [scope for scope in requested if scope not in LINKEDIN_SCOPE_PATHS]
    if unknown:
        valid = ", ".join(LINKEDIN_SCOPE_LABELS.keys())
        raise ValueError(f"Catégorie LinkedIn inconnue: {', '.join(unknown)}. Valeurs: {valid}, all")
    return requested


def build_linkedin_search_url(query: str, scope: str) -> str:
    segment = LINKEDIN_SCOPE_PATHS[scope]
    return (
        f"https://www.linkedin.com/search/results/{segment}/"
        f"?keywords={quote_plus(query.strip())}"
    )


def normalize_linkedin_result_url(href: str, scope: str) -> str:
    if not href:
        return ""
    cleaned = href.split("?")[0].strip()
    if cleaned.startswith("http"):
        return cleaned.rstrip("/")
    return urljoin("https://www.linkedin.com", cleaned).rstrip("/")


def _slug_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").strip() or EMPTY_VALUE


def _is_valid_scope_url(url: str, scope: str) -> bool:
    lowered = url.lower()
    checks = {
        "people": "/in/",
        "posts": ("/feed/update/", "/posts/", "activity"),
        "jobs": "/jobs/",
        "companies": "/company/",
        "groups": "/groups/",
        "products": "/products/",
        "events": "/events/",
        "schools": "/school/",
        "services": "/services/",
        "courses": "/learning/",
    }
    patterns = checks.get(scope, ())
    if isinstance(patterns, str):
        patterns = (patterns,)
    return any(pattern in lowered for pattern in patterns)


def _record_from_visible(scope: str, url: str, visible: str) -> ScraperRecord:
    label = LINKEDIN_SCOPE_LABELS[scope]
    if scope == "people":
        parsed = parse_linkedin_card(visible)
        return ScraperRecord(
            nom=parsed["nom"],
            email=EMPTY_VALUE,
            whatsapp=EMPTY_VALUE,
            pays=parsed["pays"],
            entreprise=parsed["entreprise"],
            poste=parsed["poste"],
            domaine=EMPTY_VALUE,
            site_web=EMPTY_VALUE,
            app="linkedin",
            link=url,
        )

    if scope == "companies":
        parsed = parse_linkedin_company_card(visible)
        return ScraperRecord(
            nom=parsed["nom"],
            email=EMPTY_VALUE,
            whatsapp=EMPTY_VALUE,
            pays=parsed["pays"],
            entreprise=parsed["entreprise"],
            poste=parsed["poste"],
            domaine=EMPTY_VALUE,
            site_web=EMPTY_VALUE,
            app="linkedin",
            link=url,
        )

    lines = [line.strip() for line in visible.splitlines() if line.strip()]
    nom = lines[0] if lines else _slug_from_url(url)
    poste = lines[1] if len(lines) > 1 else label
    entreprise = lines[2] if len(lines) > 2 else label
    pays = EMPTY_VALUE
    if len(lines) > 2 and "," in lines[-1]:
        pays = lines[-1]
    return ScraperRecord(
        nom=nom,
        email=EMPTY_VALUE,
        whatsapp=EMPTY_VALUE,
        pays=pays,
        entreprise=entreprise,
        poste=poste,
        domaine=EMPTY_VALUE,
        site_web=EMPTY_VALUE,
        app="linkedin",
        link=url,
    )


def _link_seen(url: str, skip_links: set[str] | None) -> bool:
    if not skip_links:
        return False
    return url in skip_links


def _extract_companies_from_cards(
    page,
    limit: int,
    *,
    skip_links: set[str] | None = None,
) -> list[ScraperRecord]:
    records: list[ScraperRecord] = []
    seen: set[str] = set()
    cards = page.locator(
        "div[data-view-name='search-result-lockup'], "
        "li.reusable-search__result-container, "
        "div[data-view-name='company-search-result']"
    )
    for index in range(cards.count()):
        card = cards.nth(index)
        anchor = card.locator("a[href*='/company/']").first
        if anchor.count() == 0:
            continue
        href = anchor.get_attribute("href") or ""
        url = normalize_linkedin_result_url(href, "companies")
        if (
            not url
            or not _is_valid_scope_url(url, "companies")
            or url in seen
            or _link_seen(url, skip_links)
        ):
            continue
        seen.add(url)
        visible = (card.inner_text() or "").strip()
        records.append(_record_from_visible("companies", url, visible))
        if len(records) >= limit:
            return records
    return records


def _extract_people_from_cards(
    page,
    limit: int,
    *,
    skip_links: set[str] | None = None,
) -> list[ScraperRecord]:
    records: list[ScraperRecord] = []
    seen: set[str] = set()
    cards = page.locator(
        "div[data-view-name='search-result-lockup'], "
        "li.reusable-search__result-container, "
        "div[data-view-name='people-search-result']"
    )
    for index in range(cards.count()):
        card = cards.nth(index)
        anchor = card.locator("a[href*='/in/']").first
        if anchor.count() == 0:
            continue
        href = anchor.get_attribute("href") or ""
        url = normalize_linkedin_result_url(href, "people")
        if (
            not url
            or not _is_valid_scope_url(url, "people")
            or url in seen
            or _link_seen(url, skip_links)
        ):
            continue
        seen.add(url)
        visible = (card.inner_text() or "").strip()
        records.append(_record_from_visible("people", url, visible))
        if len(records) >= limit:
            return records
    return records


def extract_linkedin_scope_records(
    page,
    scope: str,
    limit: int,
    *,
    skip_links: set[str] | None = None,
) -> list[ScraperRecord]:
    if scope == "people":
        card_records = _extract_people_from_cards(page, limit, skip_links=skip_links)
        if card_records:
            return card_records
    if scope == "companies":
        card_records = _extract_companies_from_cards(page, limit, skip_links=skip_links)
        if card_records:
            return card_records

    records: list[ScraperRecord] = []
    seen: set[str] = set()
    for selector in LINKEDIN_SCOPE_SELECTORS[scope]:
        for anchor in page.locator(selector).all():
            href = anchor.get_attribute("href") or ""
            url = normalize_linkedin_result_url(href, scope)
            if (
                not url
                or not _is_valid_scope_url(url, scope)
                or url in seen
                or _link_seen(url, skip_links)
            ):
                continue
            seen.add(url)
            visible = (anchor.inner_text() or "").strip()
            if not visible:
                card = anchor.locator("xpath=ancestor::li[1]")
                if card.count():
                    visible = (card.first.inner_text() or "").strip()
            records.append(_record_from_visible(scope, url, visible))
            if len(records) >= limit:
                return records
        if records:
            return records
    return records


def linkedin_scope_wait_selector(scope: str) -> str:
    return LINKEDIN_SCOPE_WAIT_SELECTORS[scope]
