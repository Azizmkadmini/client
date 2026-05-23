"""Filtre géographique sur les leads scrapés (inclusion / exclusion par mots-clés pays/bio)."""



from __future__ import annotations



import re



from config import settings

from scraper.models import ScraperRecord, is_empty_value



_SPLIT_RE = re.compile(r"[,;\n\r]+")

_NON_WORD = r"a-z0-9àâäéèêëïîôùûüç'’\-"



# Indices qu'une liste d'exclusion vise la Tunisie → on applique aussi e-mail .tn et +216.

_TUNISIA_EXCLUDE_HINTS = frozenset(

    {

        "tunisia",

        "tunisie",

        "tunis",

        "monastir",

        "sfax",

        "sousse",

        "gouvernorat",

        "bizerte",

        "gabes",

        "gabès",

        "ariana",

        "nabeul",

        "تونس",

        "tn",

    }

)





def parse_location_keywords(raw: str | None = None) -> tuple[str, ...]:

    """Découpe une chaîne (virgules, retours ligne) en mots-clés normalisés."""

    text = (raw or "").strip()

    if not text:

        return ()

    tokens = [_normalize_keyword(t) for t in _SPLIT_RE.split(text) if t.strip()]

    return tuple(dict.fromkeys(tokens))





def parse_exclude_location_keywords(raw: str | None = None) -> tuple[str, ...]:

    """Mots-clés d'exclusion depuis l'argument ou SCRAPER_EXCLUDE_LOCATION_KEYWORDS (.env)."""

    if raw is not None:

        return parse_location_keywords(raw)

    return parse_location_keywords(getattr(settings, "scraper_exclude_location_keywords", "") or "")





def _normalize_keyword(token: str) -> str:

    return token.strip().lower()





def _record_location_blob(record: ScraperRecord) -> str:

    parts: list[str] = []

    for value in (record.pays, record.about, record.poste, record.entreprise, record.nom, record.site_web):

        if value and not is_empty_value(value):

            parts.append(str(value))

    return " ".join(parts).lower()





def _keyword_in_blob(blob: str, kw: str) -> bool:

    if not blob or not kw:

        return False

    kw = kw.strip().lower()

    if not kw:

        return False

    if " " in kw:

        return kw in blob

    # Mot entier : évite « nice » dans « magnificent », « lille » dans « grille », etc.

    return bool(

        re.search(

            rf"(?<![{_NON_WORD}]){re.escape(kw)}(?![{_NON_WORD}])",

            blob,

            flags=re.IGNORECASE,

        )

    )





def location_blob_matches_any(blob: str, keywords: tuple[str, ...]) -> bool:

    if not blob or not keywords:

        return False

    return any(_keyword_in_blob(blob, kw) for kw in keywords if kw)





def _exclude_list_implies_tunisia(keywords: tuple[str, ...]) -> bool:

    return any(k in _TUNISIA_EXCLUDE_HINTS for k in keywords)





def _whatsapp_digits(record: ScraperRecord) -> str:

    raw = (record.whatsapp or "").strip()

    if not raw or is_empty_value(raw):

        return ""

    digits = re.sub(r"\D", "", raw)

    if digits.startswith("00"):

        digits = digits[2:]

    return digits





def record_has_tunisia_phone(record: ScraperRecord) -> bool:

    digits = _whatsapp_digits(record)

    return bool(digits.startswith("216") and len(digits) >= 10)





def record_has_tunisia_email(record: ScraperRecord) -> bool:

    email = (record.email or "").strip().lower()

    if not email or is_empty_value(email):

        return False

    if "@" not in email:

        return False

    domain = email.rsplit("@", 1)[-1]

    return domain == "tn" or domain.endswith(".tn")





def record_indicates_tunisia_contact(record: ScraperRecord) -> bool:

    return record_has_tunisia_phone(record) or record_has_tunisia_email(record)





def record_matches_include_location(

    record: ScraperRecord,

    keywords: tuple[str, ...],

) -> bool:

    """True si le profil correspond à au moins un pays / mot-clé demandé."""

    if not keywords:

        return True

    blob = _record_location_blob(record)

    if not blob:

        return False

    return location_blob_matches_any(blob, keywords)





def record_indicates_excluded_location(

    record: ScraperRecord,

    keywords: tuple[str, ...],

) -> bool:

    if not keywords:

        return False

    blob = _record_location_blob(record)

    if location_blob_matches_any(blob, keywords):

        return True

    if _exclude_list_implies_tunisia(keywords) and record_indicates_tunisia_contact(record):

        return True

    if (

        getattr(settings, "scraper_exclude_location_strict", False)

        and _exclude_list_implies_tunisia(keywords)

        and not blob

    ):

        return True

    return False





def filter_records_included_locations(

    records: list[ScraperRecord],

    keywords: tuple[str, ...],

) -> list[ScraperRecord]:

    if not keywords:

        return records

    return [r for r in records if record_matches_include_location(r, keywords)]





def filter_records_excluded_locations(

    records: list[ScraperRecord],

    keywords: tuple[str, ...] | None = None,

) -> list[ScraperRecord]:

    effective = keywords if keywords is not None else parse_exclude_location_keywords()

    if not effective:

        return records

    return [r for r in records if not record_indicates_excluded_location(r, effective)]





def request_has_location_filters(

    include_keywords: tuple[str, ...],

    exclude_keywords: tuple[str, ...] | None,

) -> bool:

    if include_keywords:

        return True

    if exclude_keywords is not None:

        return bool(exclude_keywords)

    return bool(parse_exclude_location_keywords())





def apply_location_filters(

    records: list[ScraperRecord],

    *,

    include_keywords: tuple[str, ...] = (),

    exclude_keywords: tuple[str, ...] | None = None,

) -> list[ScraperRecord]:

    """Inclusion d'abord (pays choisis), puis exclusion (ex. Tunisie)."""

    if include_keywords:

        records = filter_records_included_locations(records, include_keywords)

    excl = exclude_keywords if exclude_keywords is not None else parse_exclude_location_keywords()

    if excl:

        records = filter_records_excluded_locations(records, excl)

    return records


def apply_location_filters_web(
    records: list[ScraperRecord],
    *,
    include_keywords: tuple[str, ...] = (),
    exclude_keywords: tuple[str, ...] | None = None,
) -> list[ScraperRecord]:
    """
    Filtre allégé pour collecte Google → sites.

    « Pays choisis » est ignoré (pas de pays sur la fiche). « Exclure Tunisie » :
    e-mail .tn, WhatsApp +216, ou mot-clé dans l'URL / nom du site.
    """
    _ = include_keywords
    excl = exclude_keywords if exclude_keywords is not None else ()
    if not excl:
        return records
    out: list[ScraperRecord] = []
    for record in records:
        blob = _record_location_blob(record)
        if location_blob_matches_any(blob, excl):
            continue
        if _exclude_list_implies_tunisia(excl) and record_indicates_tunisia_contact(record):
            continue
        out.append(record)
    return out

