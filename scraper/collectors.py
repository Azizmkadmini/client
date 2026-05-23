from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import quote_plus

from config import settings
from scraper.browser import require_session
from scraper.extractors import (
    guess_company,
    guess_role,
    normalize_email,
    normalize_whatsapp_number,
    parse_domain,
    parse_email,
    parse_whatsapp,
)
from scraper.linkedin_company import (
    enrich_linkedin_company_fast_email,
    enrich_linkedin_company_page,
    enrich_linkedin_company_records,
)
from scraper.linkedin_profile import (
    enrich_linkedin_profile_fast_email,
    enrich_linkedin_profile_page,
    enrich_linkedin_people_records,
)
from scraper.linkedin_search import (
    build_linkedin_search_url,
    extract_linkedin_scope_records,
    linkedin_scope_wait_selector,
    resolve_linkedin_scopes,
)
from scraper.models import EMPTY_VALUE, ScraperRecord, SearchRequest, is_empty_value
from scraper.progress import scraper_progress
from scraper.location_filter import apply_location_filters, request_has_location_filters
from scraper.query_parse import split_scraper_queries
from scraper import timing as scrape_timing
from scraper.linkedin_stability import (
    assert_linkedin_page_ok,
    effective_max_profiles_to_try,
    effective_search_terms_cap,
    maybe_long_pause_between_profiles,
    validate_linkedin_session_file,
)
from scraper.instagram_login import (
    ensure_instagram_logged_in_with_password,
    instagram_password_login_configured,
    instagram_session_storage_ready,
    launch_chromium_for_instagram_password,
)
from utils.browser_session import close_session, open_channel_context, persist_context_state

_INSTAGRAM_STATS_RE = re.compile(
    r"\b(posts?|publications?|followers?|following|abonnés?|abonnements?|suivis?|seguidores?)\b",
    re.IGNORECASE,
)
_INSTAGRAM_UI_NOISE_LOWER = frozenset(
    {
        "note",
        "notes",
        "note...",
        "notes...",
        "note…",
        "notes…",
        "follow",
        "following",
        "followers",
        "suivre",
        "suivi",
        "suivie",
        "suivis",
        "message",
        "messages",
        "more",
        "options",
        "paramètres",
        "settings",
        "edit profile",
        "modifier le profil",
        "voir la traduction",
        "voir plus",
        "see more",
        "link",
        "lien",
    }
)


def _instagram_line_is_ui_noise(line: str, handle: str) -> bool:
    """Filtre libellés Instagram / stats (évite « Note… », Suivre, etc. comme nom)."""
    s = (line or "").strip()
    if not s:
        return True
    low = s.lower()
    if len(s) > 160:
        return True
    if low == handle.lower() or low == f"@{handle}".lower():
        return True
    if low in _INSTAGRAM_UI_NOISE_LOWER:
        return True
    if low.rstrip(".") in {x.rstrip(".") for x in _INSTAGRAM_UI_NOISE_LOWER}:
        return True
    if re.fullmatch(r"notes?\.{1,5}", low):
        return True
    if _INSTAGRAM_STATS_RE.search(s) and re.search(r"\d", s):
        return True
    if ("·" in s or "•" in s) and _INSTAGRAM_STATS_RE.search(s):
        return True
    return False


def _instagram_bio_text(header: str, handle: str) -> str:
    lines = [
        ln.strip()
        for ln in (header or "").splitlines()
        if not _instagram_line_is_ui_noise(ln, handle)
    ]
    return "\n".join(lines).strip()


def _instagram_display_name(title: str, header: str, handle: str) -> str:
    if title and "Instagram" in title:
        candidate = title.split("•")[0].strip().split("·")[0].strip().split("(")[0].strip()
        if (
            candidate
            and candidate.lower() != "instagram"
            and not _instagram_line_is_ui_noise(candidate, handle)
        ):
            return candidate
    for line in (header or "").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.lower() == handle.lower():
            continue
        if not _instagram_line_is_ui_noise(cleaned, handle):
            return cleaned
    return handle


def _instagram_gather_bio_text(page, header: str, handle: str) -> str:
    """Header nettoyé + meta description + zone bio si présente (meilleure couverture pour regex)."""
    chunks: list[str] = []
    core = _instagram_bio_text(header, handle)
    if core.strip():
        chunks.append(core.strip())
    try:
        if page.locator('meta[name="description"]').count():
            desc = page.locator('meta[name="description"]').first.get_attribute("content") or ""
            desc = desc.strip()
            if desc and handle.lower() in desc.casefold():
                chunks.append(desc)
    except Exception:
        pass
    for sel in (
        '[data-testid="user-bio"]',
        "header span._ap3a",
        "header h1 + div span",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            t = (loc.inner_text() or "").strip()
            if t and not _instagram_line_is_ui_noise(t, handle):
                chunks.append(t)
                break
        except Exception:
            continue
    merged = "\n".join(dict.fromkeys(chunks))
    return merged.strip()


def _instagram_validate_record(record: ScraperRecord) -> ScraperRecord:
    """Re-valide e-mail / mobile et retire les domaines parasites (réseaux sociaux)."""
    email = record.email
    if not is_empty_value(email):
        email = normalize_email(email)
    wa = record.whatsapp
    if is_empty_value(wa):
        wa_clean = EMPTY_VALUE
    else:
        wa_clean = normalize_whatsapp_number(wa)
    dom = record.domaine
    if not is_empty_value(dom):
        low = dom.lower()
        if any(
            h in low
            for h in (
                "instagram.com",
                "facebook.com",
                "tiktok.com",
                "twitter.com",
                "x.com",
                "schema.org",
            )
        ):
            dom = EMPTY_VALUE
    return replace(record, email=email, whatsapp=wa_clean, domaine=dom)


def collect_live(request: SearchRequest) -> list[ScraperRecord]:
    if request.app == "instagram":
        return _collect_instagram(request)
    if request.app == "linkedin":
        return _collect_linkedin(request)
    raise RuntimeError(f"Collecte réelle non disponible pour l'app {request.app}.")


def _instagram_explore_url(query_term: str, mode: str) -> str:
    if mode == "hashtag":
        tag = query_term.lstrip("#").strip()
        return f"https://www.instagram.com/explore/tags/{quote_plus(tag)}/"
    return f"https://www.instagram.com/explore/search/keyword/?q={quote_plus(query_term)}"


def _collect_instagram(request: SearchRequest) -> list[ScraperRecord]:
    from playwright.sync_api import sync_playwright

    raw_query = (request.query or "").strip()
    if not raw_query:
        raise RuntimeError("Indiquez un hashtag ou un mot-clé pour une collecte réelle.")
    queries = split_scraper_queries(raw_query, mode=request.mode)
    if not queries:
        raise RuntimeError("Indiquez au moins un mot-clé ou hashtag valide.")

    # Fichier de session (login CDP / outreach) prioritaire sur identifiants .env (évite reCAPTCHA Playwright).
    use_password = instagram_password_login_configured() and not instagram_session_storage_ready()
    if not use_password:
        require_session("instagram")

    handles: list[str] = []
    seen_handles: set[str] = set()
    n_queries = len(queries)
    with sync_playwright() as playwright:
        if use_password:
            browser, context = launch_chromium_for_instagram_password(playwright)
            owns_browser = True
        else:
            browser, context, owns_browser = open_channel_context(
                playwright,
                "instagram",
                headless=settings.scraper_headless,
            )
        page = context.new_page()
        if use_password:
            scraper_progress(
                phase="instagram_nav",
                fraction=0.03,
                message="Connexion Instagram (identifiant / mot de passe)…",
            )
            ensure_instagram_logged_in_with_password(page)
        for q_idx, query_term in enumerate(queries):
            q_frac = q_idx / max(n_queries, 1)
            label = f"« {query_term} »"
            scraper_progress(
                phase="instagram_nav",
                fraction=0.05 + q_frac * 0.07,
                message=f"Recherche niche {q_idx + 1}/{n_queries} {label}…",
            )
            page.goto(
                _instagram_explore_url(query_term, request.mode),
                wait_until="domcontentloaded",
                timeout=90000,
            )
            page.wait_for_timeout(scrape_timing.collectors_instagram_first_wait_ms())
            _scroll_results(page, passes=2)
            scraper_progress(
                phase="instagram_discover",
                fraction=0.10 + q_frac * 0.02,
                message=f"Scrape profils {q_idx + 1}/{n_queries} {label}…",
            )
            for handle in _discover_instagram_handles(page, request.limit):
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                handles.append(handle)
        n = max(len(handles), 1)
        records = []
        nh = len(handles)
        for i, handle in enumerate(handles):
            lo = 0.12 + 0.88 * i / n
            hi = 0.12 + 0.88 * (i + 1) / n
            records.append(
                _scrape_instagram_profile(
                    context,
                    handle,
                    request.app,
                    progress_base=lo,
                    progress_width=hi - lo,
                    profile_index=i + 1,
                    profile_total=nh,
                )
            )
        scraper_progress(
            phase="instagram_done",
            fraction=1.0,
            message="Pipeline Instagram terminé (recherche → profils → bio → contacts → validation).",
        )
        persist_context_state("instagram", context)
        close_session(browser, context, owns_browser=owns_browser)

    records = [record for record in records if record.nom != EMPTY_VALUE]
    total_before_geo = len(records)
    records = apply_location_filters(
        records,
        include_keywords=request.include_location_keywords,
        exclude_keywords=request.exclude_location_keywords,
    )
    if not records and total_before_geo > 0 and request_has_location_filters(
        request.include_location_keywords,
        request.exclude_location_keywords,
    ):
        terms = ", ".join(queries)
        if request.include_location_keywords:
            raise RuntimeError(
                f"{total_before_geo} profil(s) trouvé(s) pour {terms}, mais aucun ne correspond aux "
                f"pays choisis dans le formulaire. Élargissez la liste de pays ou la saisie libre."
            )
        raise RuntimeError(
            f"{total_before_geo} profil(s) trouvé(s) pour {terms}, mais tous exclus par le filtre "
            f"géographique (.env ou formulaire)."
        )
    if not records:
        terms = ", ".join(queries)
        raise RuntimeError(
            f"Aucun profil trouvé pour : {terms}. "
            "Essayez d'autres termes ou vérifiez que vous êtes bien connecté. "
            "Sans sessions/instagram.json : `python outreach.py login instagram` (ou --cdp / --from-browser). "
            "Identifiants .env ne sont utilisés que s'il n'y a pas encore de fichier de session."
        )
    return records


def _discover_instagram_handles(page, limit: int) -> list[str]:
    handles: list[str] = []
    seen: set[str] = set()
    selectors = [
        "a[href^='/@']",
        "a[href*='/p/']",
        "a[role='link'][href*='/']",
    ]
    for selector in selectors:
        for anchor in page.locator(selector).all():
            href = anchor.get_attribute("href") or ""
            handle = _instagram_handle_from_href(href)
            if not handle or handle in seen:
                continue
            seen.add(handle)
            handles.append(handle)
            if len(handles) >= limit:
                return handles
    return handles


def _instagram_handle_from_href(href: str) -> str:
    if not href:
        return ""
    if "/p/" in href or "/explore/" in href or "/reels/" in href:
        return ""
    match = re.match(r"^/(?:@)?([^/?#]+)/?$", href)
    if not match:
        return ""
    handle = match.group(1).lower()
    if handle in {"accounts", "stories", "direct", "reels", "explore"}:
        return ""
    return handle


def _scrape_instagram_profile(
    context,
    handle: str,
    app: str,
    *,
    progress_base: float,
    progress_width: float,
    profile_index: int,
    profile_total: int,
) -> ScraperRecord:
    def bump(sub: float, message: str) -> None:
        scraper_progress(
            phase="instagram_profile",
            fraction=progress_base + progress_width * sub,
            message=f"[{profile_index}/{profile_total}] @{handle} — {message}",
        )

    bump(0.0, "entrer dans le profil…")
    page = context.new_page()
    page.goto(f"https://www.instagram.com/{handle}/", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(scrape_timing.collectors_instagram_profile_wait_ms())
    title = page.title() or ""
    header = page.locator("header").inner_text() if page.locator("header").count() else ""

    bump(0.22, "extraire la bio…")
    bio = _instagram_gather_bio_text(page, header, handle)
    name = _instagram_display_name(title, header, handle)
    bio_stripped = bio.strip()
    if len(bio_stripped) > 800:
        about = bio_stripped[:800] + "…"
    else:
        about = bio_stripped or EMPTY_VALUE

    bump(0.48, "regex e-mail / téléphone / liens…")
    record = ScraperRecord(
        nom=name,
        email=parse_email(bio),
        whatsapp=parse_whatsapp(bio),
        pays=EMPTY_VALUE,
        entreprise=guess_company(bio),
        poste=guess_role(bio),
        domaine=parse_domain(bio),
        site_web=EMPTY_VALUE,
        about=about,
        app=app,
        link=f"https://www.instagram.com/{handle}/",
    )

    bump(0.74, "validation des champs…")
    record = _instagram_validate_record(record)
    bump(1.0, "terminé")
    page.close()
    return record


def _ensure_channel_session(page, channel: str) -> None:
    if channel == "linkedin":
        assert_linkedin_page_ok(page, context="Session LinkedIn")
        return
    url = page.url.lower()
    if any(token in url for token in ("login", "signup", "checkpoint", "uas/login")):
        raise RuntimeError(
            f"Session {channel} expirée ou invalide. Relancez `python outreach.py login {channel}`."
        )


def _linkedin_prioritize_email() -> bool:
    return bool(getattr(settings, "scraper_linkedin_prioritize_email", True))


def _linkedin_has_email_or_whatsapp(record: ScraperRecord) -> bool:
    """Contact exploitable : e-mail prioritaire si ``scraper_linkedin_prioritize_email``."""
    has_email = not is_empty_value(record.email)
    has_wa = not is_empty_value(record.whatsapp)
    if _linkedin_prioritize_email():
        return has_email
    return has_email or has_wa


def _filter_linkedin_records_with_contact(records: list[ScraperRecord]) -> list[ScraperRecord]:
    if not getattr(settings, "scraper_linkedin_require_email_or_whatsapp", True):
        return records
    return [r for r in records if _linkedin_has_email_or_whatsapp(r)]


def _scroll_results(page, passes: int | None = None) -> None:
    n = passes if passes is not None else scrape_timing.linkedin_search_scroll_passes()
    step = scrape_timing.collectors_scroll_results_step_ms()
    for _ in range(n):
        page.evaluate("window.scrollBy(0, Math.max(document.body.scrollHeight, 1200))")
        page.wait_for_timeout(step)


def _linkedin_max_profiles_to_try(limit: int) -> int:
    """Nombre max de profils enrichis par recherche / catégorie avant abandon."""
    return effective_max_profiles_to_try(limit)


def _linkedin_collect_scope_batch_size(limit: int) -> int:
    """Profils extraits de la page résultats à chaque vague de scroll."""
    return min(25, max(10, limit * 6))


def _linkedin_record_passes_geo(record: ScraperRecord, request: SearchRequest) -> bool:
    if not request_has_location_filters(
        request.include_location_keywords,
        request.exclude_location_keywords,
    ):
        return True
    return bool(
        apply_location_filters(
            [record],
            include_keywords=request.include_location_keywords,
            exclude_keywords=request.exclude_location_keywords,
        )
    )


def _linkedin_can_pre_exclude_geo(record: ScraperRecord, request: SearchRequest) -> bool:
    """
    Pré-filtre géo sur les données partielles de la page résultats (avant ouverture Playwright).

    Retourne True si le profil PEUT DÉJÀ être exclu sans visiter sa fiche.
    On est volontairement conservateur : on n'exclut que les cas évidents
    (exclusion positive sur le texte déjà visible) pour éviter de rejeter à tort
    des profils dont la localisation n'est pas encore scrapée.
    """
    excl = request.exclude_location_keywords
    if not excl:
        return False
    from scraper.location_filter import record_indicates_excluded_location
    return record_indicates_excluded_location(record, excl)


def _profile_cache_lookup(candidate: ScraperRecord) -> tuple[str, ScraperRecord | None]:
    """Délègue au ProfileCache singleton — isole l'import pour éviter les dépendances circulaires."""
    try:
        from scraper.profile_cache import _normalize_domain, _profile_hash, get_profile_cache
        cache = get_profile_cache()
        url    = candidate.link or ""
        domain = _normalize_domain(candidate.domaine or candidate.site_web or "")
        phash  = _profile_hash(candidate.nom, candidate.entreprise, candidate.poste)
        return cache.lookup(url=url, domain=domain, phash=phash)
    except Exception:
        return "stale", None


def _profile_cache_mark_seen(record: ScraperRecord) -> None:
    try:
        from scraper.profile_cache import get_profile_cache
        get_profile_cache().mark_seen(record)
    except Exception:
        pass


def _email_pipeline_process(record: ScraperRecord) -> None:
    """Notifie le pipeline email après acceptance d'un lead enrichi (fire-and-forget)."""
    try:
        if not bool(getattr(settings, "scraper_email_pipeline_enabled", False)):
            return
        from scraper.email_pipeline import get_email_pipeline
        get_email_pipeline().process_accepted_lead(record)
    except Exception:
        pass


def _enrich_linkedin_record(page, record: ScraperRecord, scope: str) -> ScraperRecord:
    if not settings.scraper_linkedin_enrich_profiles:
        return record
    link = (record.link or "").lower()
    use_quick = bool(getattr(settings, "scraper_linkedin_quick_contact_probe", True)) and _linkedin_use_keep_searching()

    if scope == "people" and "/in/" in link:
        if use_quick:
            return enrich_linkedin_profile_fast_email(page, record)
        return enrich_linkedin_profile_page(page, record)
    if scope == "companies" and "/company/" in link:
        if use_quick:
            return enrich_linkedin_company_fast_email(page, record)
        return enrich_linkedin_company_page(page, record)
    return record


def _linkedin_use_keep_searching() -> bool:
    require_contact = bool(getattr(settings, "scraper_linkedin_require_email_or_whatsapp", True))
    keep = bool(getattr(settings, "scraper_linkedin_keep_searching_until_contact", True))
    return require_contact and keep


def _linkedin_collect_scope_until_contact(
    page,
    *,
    request: SearchRequest,
    query_term: str,
    scope: str,
    seen_links: set[str],
    tried_links: set[str],
    progress_base: float,
    progress_span: float,
    hunt_stats: dict[str, int] | None = None,
) -> list[ScraperRecord]:
    """Scroll + enrichit jusqu'à ``limit`` profils avec e-mail (priorité e-mail) ou épuisement du budget d'essais."""
    limit = request.limit
    max_rounds = max(1, int(getattr(settings, "scraper_linkedin_max_search_scroll_rounds", 12)))
    max_to_try = _linkedin_max_profiles_to_try(limit)
    batch_size = _linkedin_collect_scope_batch_size(limit)
    accepted: list[ScraperRecord] = []
    enrich_index = 0
    whatsapp_only = 0
    geo_rejected = 0
    consecutive_empty = 0  # scrolls consécutifs sans nouveaux liens

    for scroll_round in range(max_rounds):
        if enrich_index >= max_to_try:
            break
        if len(accepted) >= limit:
            break
        # 3 scrolls consécutifs sans aucun nouveau candidat → fin de page, inutile de continuer.
        if consecutive_empty >= 3:
            break

        if scroll_round > 0:
            _scroll_results(page)
            scraper_progress(
                phase="linkedin_search",
                fraction=progress_base + progress_span * 0.3 * (scroll_round / max_rounds),
                message=(
                    f"« {query_term} » ({scope}) — suite des résultats "
                    f"({scroll_round + 1}/{max_rounds}), {len(accepted)}/{limit} avec e-mail "
                    f"({enrich_index}/{max_to_try} essais)…"
                ),
            )

        candidates = extract_linkedin_scope_records(
            page,
            scope,
            batch_size,
            skip_links=seen_links,
        )
        if not candidates:
            consecutive_empty += 1
            continue
        consecutive_empty = 0  # reset si on trouve des nouveaux candidats

        for candidate in candidates:
            if enrich_index >= max_to_try or len(accepted) >= limit:
                break

            link = candidate.link or ""
            if link:
                seen_links.add(link)
                tried_links.add(link)

            # Pré-filtre géo sur données partielles (nom, pays, poste, entreprise)
            # visibles dans la page résultats — évite d'ouvrir le profil Playwright.
            if _linkedin_can_pre_exclude_geo(candidate, request):
                geo_rejected += 1
                continue

            # ── Cache incrémental ──────────────────────────────────────────────
            # Vérifie si ce profil a déjà été enrichi récemment (< TTL).
            # "hit"  → profil frais avec email  : on l'ajoute directement, 0 Playwright.
            # "skip" → profil frais sans email  : on abandonne, inutile de réessayer.
            # "stale"→ inconnu ou expiré        : on continue avec Playwright.
            cache_status, cached_record = _profile_cache_lookup(candidate)
            if cache_status == "hit":
                if _linkedin_record_passes_geo(cached_record, request):
                    accepted.append(cached_record)
                    scraper_progress(
                        phase="linkedin_cache",
                        fraction=progress_base
                        + progress_span * (0.35 + 0.65 * min(1.0, (enrich_index + 1) / max(max_to_try, 1))),
                        message=(
                            f"Cache — {cached_record.nom or link} déjà collecté "
                            f"({len(accepted)}/{limit})."
                        ),
                    )
                continue
            if cache_status == "skip":
                enrich_index += 1
                continue
            # cache_status == "stale" → enrichissement Playwright normal
            # ──────────────────────────────────────────────────────────────────

            enrich_index += 1
            if enrich_index > 1:
                maybe_long_pause_between_profiles(enrich_index)
                page.wait_for_timeout(scrape_timing.linkedin_inter_profile_pause_ms())
            scraper_progress(
                phase="linkedin_enrich",
                fraction=progress_base
                + progress_span * (0.35 + 0.65 * min(1.0, enrich_index / max(max_to_try, 1))),
                message=(
                    f"Essai {enrich_index}/{max_to_try} — {len(accepted)}/{limit} avec e-mail "
                    f"({query_term}, {scope})…"
                ),
            )
            enriched = _enrich_linkedin_record(page, candidate, scope)

            # Persistance dans le cache (avec ou sans email — pour éviter de réessayer)
            _profile_cache_mark_seen(enriched)

            has_email = not is_empty_value(enriched.email)
            has_wa = not is_empty_value(enriched.whatsapp)
            if not _linkedin_has_email_or_whatsapp(enriched):
                if has_wa and not has_email and _linkedin_prioritize_email():
                    whatsapp_only += 1
                continue
            if not _linkedin_record_passes_geo(enriched, request):
                geo_rejected += 1
                continue
            accepted.append(enriched)
            # Notifie le pipeline email (si activé) — zéro Playwright, zéro HTTP
            _email_pipeline_process(enriched)

        if len(accepted) >= limit:
            break

    if hunt_stats is not None:
        hunt_stats["whatsapp_only"] = hunt_stats.get("whatsapp_only", 0) + whatsapp_only
        hunt_stats["geo_rejected"] = hunt_stats.get("geo_rejected", 0) + geo_rejected
        hunt_stats["max_to_try"] = max(hunt_stats.get("max_to_try", 0), max_to_try)
    return accepted[:limit]


def _collect_linkedin(request: SearchRequest) -> list[ScraperRecord]:
    from playwright.sync_api import sync_playwright

    raw_query = (request.query or "").strip()
    if not raw_query:
        raise RuntimeError("Indiquez un mot-clé pour une collecte LinkedIn réelle.")
    queries = split_scraper_queries(raw_query, mode=request.mode)
    if not queries:
        raise RuntimeError("Indiquez au moins un mot-clé valide.")
    cap_terms = effective_search_terms_cap(len(queries))
    if cap_terms < len(queries):
        scraper_progress(
            phase="linkedin_limit",
            fraction=0.01,
            message=(
                f"Mode stable : {cap_terms}/{len(queries)} mot(s)-clé utilisés "
                f"(limitez SCRAPER_LINKEDIN_MAX_SEARCH_TERMS pour changer)."
            ),
        )
        queries = queries[:cap_terms]

    scopes = resolve_linkedin_scopes(request.linkedin_scopes)
    validate_linkedin_session_file()
    require_session("linkedin")  # → linkedin-scrape (fallback linkedin.json)
    records: list[ScraperRecord] = []
    people_to_enrich: list[ScraperRecord] = []
    companies_to_enrich: list[ScraperRecord] = []
    seen_links: set[str] = set()
    tried_links: set[str] = set()
    hunt_stats: dict[str, int] = {"whatsapp_only": 0, "geo_rejected": 0, "max_to_try": 0}
    keep_searching = _linkedin_use_keep_searching()
    n_scopes = max(len(scopes), 1)
    n_queries = len(queries)
    search_steps = max(n_queries * n_scopes, 1)
    with sync_playwright() as playwright:
        from utils.session_channels import scrape_session_channel

        browser, context, owns_browser = open_channel_context(
            playwright,
            scrape_session_channel("linkedin"),
            headless=settings.scraper_headless,
        )
        page = context.new_page()
        page.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_timeout(scrape_timing.collectors_linkedin_search_wait_ms())
        assert_linkedin_page_ok(page)
        scraper_progress(
            phase="linkedin_start",
            fraction=0.02,
            message="Session LinkedIn OK — démarrage collecte (mode stable)…",
        )
        step = 0
        for q_idx, query_term in enumerate(queries):
            for scope_index, scope in enumerate(scopes):
                step += 1
                progress_base = 0.02 + 0.96 * ((step - 1) / search_steps)
                progress_span = 0.96 / search_steps
                search_url = build_linkedin_search_url(query_term, scope)
                scraper_progress(
                    phase="linkedin_search",
                    fraction=progress_base,
                    message=(
                        f"Recherche LinkedIn « {query_term} » ({scope}) "
                        f"— {q_idx + 1}/{n_queries}…"
                    ),
                )
                page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(scrape_timing.collectors_linkedin_search_wait_ms())
                _ensure_channel_session(page, "linkedin")
                try:
                    page.wait_for_selector(linkedin_scope_wait_selector(scope), timeout=20000)
                except Exception:
                    pass
                _scroll_results(page)

                if keep_searching:
                    scope_accepted = _linkedin_collect_scope_until_contact(
                        page,
                        request=request,
                        query_term=query_term,
                        scope=scope,
                        seen_links=seen_links,
                        tried_links=tried_links,
                        progress_base=progress_base,
                        progress_span=progress_span,
                        hunt_stats=hunt_stats,
                    )
                    records.extend(scope_accepted)
                    continue

                scope_records = extract_linkedin_scope_records(
                    page, scope, request.limit, skip_links=seen_links
                )
                for record in scope_records:
                    if record.link in seen_links:
                        continue
                    # Filtre les profils anonymes (LinkedIn Member / 3rd+)
                    if scope == "people" and is_empty_value(record.nom):
                        continue
                    seen_links.add(record.link)
                    records.append(record)
                    if (
                        scope == "people"
                        and settings.scraper_linkedin_enrich_profiles
                        and "/in/" in (record.link or "").lower()
                    ):
                        people_to_enrich.append(record)
                    if (
                        scope == "companies"
                        and settings.scraper_linkedin_enrich_profiles
                        and "/company/" in (record.link or "").lower()
                    ):
                        companies_to_enrich.append(record)

        if not keep_searching:
            enrich_total = 0
            if settings.scraper_linkedin_enrich_profiles:
                enrich_total = len(people_to_enrich) + len(companies_to_enrich)
            enrich_step = 0

            def _emit_enrich(done: int, total: int, kind: str) -> None:
                nonlocal enrich_step
                enrich_step += 1
                if enrich_total <= 0:
                    return
                scraper_progress(
                    phase="linkedin_enrich",
                    fraction=0.35 + 0.65 * (enrich_step / enrich_total),
                    message=f"Enrichissement {kind} {done}/{total}…",
                )

            enriched_by_link: dict[str, ScraperRecord] = {}
            if people_to_enrich and settings.scraper_linkedin_enrich_profiles:
                for item in enrich_linkedin_people_records(
                    context,
                    people_to_enrich,
                    page=page,
                    on_step=lambda d, t: _emit_enrich(d, t, "profil"),
                ):
                    enriched_by_link[item.link] = item
            if companies_to_enrich and settings.scraper_linkedin_enrich_profiles:
                for item in enrich_linkedin_company_records(
                    context,
                    companies_to_enrich,
                    page=page,
                    on_step=lambda d, t: _emit_enrich(d, t, "entreprise"),
                ):
                    enriched_by_link[item.link] = item
            if enriched_by_link:
                records = [enriched_by_link.get(item.link, item) for item in records]

        scraper_progress(
            phase="linkedin_done",
            fraction=1.0,
            message=(
                f"Collecte LinkedIn terminée — {len(records)} profil(s) avec e-mail."
                if keep_searching
                else "Collecte LinkedIn terminée."
            ),
        )
        persist_context_state("linkedin", context)
        close_session(browser, context, owns_browser=owns_browser)

    if keep_searching:
        if records:
            return records
        terms = ", ".join(queries)
        tried = len(tried_links)
        max_to_try = hunt_stats.get("max_to_try") or _linkedin_max_profiles_to_try(request.limit)
        hints: list[str] = [
            f"Aucun profil avec e-mail après {tried} essai(s) (budget jusqu'à {max_to_try}) pour : {terms}.",
            "Priorité e-mail : le WhatsApp seul ne suffit pas.",
        ]
        wa_only = hunt_stats.get("whatsapp_only", 0)
        geo_skip = hunt_stats.get("geo_rejected", 0)
        if wa_only:
            hints.append(f"{wa_only} profil(s) avaient WhatsApp sans e-mail public.")
        if geo_skip:
            hints.append(f"{geo_skip} profil(s) avaient un contact mais ont été exclus par le filtre pays.")
        hints.append(
            "Vérifiez SCRAPER_FETCH_CONTACTS_FROM_WEBSITE=true, SCRAPER_GUESS_CONTACT_EMAILS=true "
            "(SCRAPER_GUESS_EMAIL_REQUIRE_MX=false si les e-mails devinés sont tous rejetés). "
            "Augmentez SCRAPER_LINKEDIN_MAX_SEARCH_SCROLL_ROUNDS ou SCRAPER_LINKEDIN_MAX_PROFILES_TO_TRY."
        )
        raise RuntimeError(" ".join(hints))

    total_before_filter = len(records)
    records = _filter_linkedin_records_with_contact(records)
    after_contact = len(records)
    records = apply_location_filters(
        records,
        include_keywords=request.include_location_keywords,
        exclude_keywords=request.exclude_location_keywords,
    )
    if not records:
        if after_contact > 0 and request_has_location_filters(
            request.include_location_keywords,
            request.exclude_location_keywords,
        ):
            terms = ", ".join(queries)
            if request.include_location_keywords:
                raise RuntimeError(
                    f"{after_contact} profil(s) LinkedIn avec contact pour {terms}, mais aucun ne "
                    f"correspond aux pays choisis. Élargissez la sélection pays du formulaire."
                )
            raise RuntimeError(
                f"{after_contact} profil(s) LinkedIn avec contact, mais tous exclus par le filtre "
                f"géographique (.env ou formulaire)."
            )
        if total_before_filter > 0 and getattr(
            settings, "scraper_linkedin_require_email_or_whatsapp", True
        ):
            raise RuntimeError(
                f"{total_before_filter} profil(s) LinkedIn trouvé(s), mais aucun avec e-mail ou WhatsApp. "
                "Le mode « continuer jusqu'à trouver » est actif : augmentez la limite, "
                "les mots-clés, ou SCRAPER_LINKEDIN_MAX_SEARCH_SCROLL_ROUNDS dans .env."
            )
        terms = ", ".join(queries)
        raise RuntimeError(
            f"Aucun résultat LinkedIn trouvé pour : {terms}. "
            "Vérifiez la session avec `python outreach.py login linkedin`, "
            "puis relancez avec d'autres mots-clés ou catégories."
        )
    return records
