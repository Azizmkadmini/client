"""Pays proposés dans le formulaire scraper (dashboard) → mots-clés pour le filtre pays/bio."""

from __future__ import annotations

from scraper.location_filter import parse_location_keywords

SCRAPE_COUNTRY_PRESETS: dict[str, tuple[str, ...]] = {
    "France": ("france", "paris", "lyon", "marseille", "toulouse", "bordeaux", "lille", "nice"),
    "Belgique": ("belgique", "belgium", "bruxelles", "brussels", "anvers", "antwerp"),
    "Suisse": ("suisse", "switzerland", "genève", "geneva", "zurich", "lausanne"),
    "Canada": ("canada", "montréal", "montreal", "toronto", "vancouver", "québec", "quebec"),
    "États-Unis": ("united states", "usa", "u.s.", "new york", "california", "texas", "florida"),
    "Royaume-Uni": ("royaume-uni", "united kingdom", "uk", "london", "londres", "manchester"),
    "Allemagne": ("allemagne", "germany", "berlin", "munich", "münchen", "frankfurt"),
    "Espagne": ("espagne", "spain", "madrid", "barcelona", "barcelone", "valencia"),
    "Italie": ("italie", "italy", "milan", "milano", "rome", "roma", "naples"),
    "Maroc": ("maroc", "morocco", "casablanca", "rabat", "marrakech", "tanger"),
    "Algérie": ("algérie", "algeria", "alger", "algiers", "oran"),
    "Émirats arabes unis": (
        "émirats",
        "emirates",
        "uae",
        "dubai",
        "dubaï",
        "abu dhabi",
        "abou dhabi",
    ),
    "Arabie saoudite": ("arabie saoudite", "saudi", "riyadh", "riyad", "jeddah"),
    "Qatar": ("qatar", "doha"),
    "Turquie": ("turquie", "turkey", "istanbul", "ankara"),
    "Sénégal": ("sénégal", "senegal", "dakar"),
    "Côte d'Ivoire": ("côte d'ivoire", "ivory coast", "abidjan"),
}

TUNISIA_EXCLUDE_PRESET: tuple[str, ...] = (
    "tunisia",
    "tunisie",
    "tunis",
    "monastir",
    "sfax",
    "sousse",
    "bizerte",
    "gouvernorat",
    "gabes",
    "gabès",
    "ariana",
    "nabeul",
    "تونس",
)


def country_labels() -> list[str]:
    return list(SCRAPE_COUNTRY_PRESETS.keys())


def keywords_for_country_form(
    selected_labels: list[str],
    extra_raw: str = "",
) -> tuple[str, ...]:
    """Transforme la sélection dashboard + saisie libre en mots-clés de filtre."""
    tokens: list[str] = []
    for label in selected_labels:
        preset = SCRAPE_COUNTRY_PRESETS.get(label)
        if preset:
            tokens.extend(preset)
        elif label.strip():
            tokens.append(label.strip().lower())
    tokens.extend(parse_location_keywords(extra_raw))
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.casefold()
        if not t or key in seen:
            continue
        seen.add(key)
        out.append(t)
    return tuple(out)
