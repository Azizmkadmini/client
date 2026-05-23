from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AppName = Literal["linkedin", "instagram", "whatsapp", "email", "web"]
SearchMode = Literal["hashtag", "keyword"]

EMPTY_VALUE = "vide"

CSV_COLUMNS = [
    "nom",
    "email",
    "whatsapp",
    "whatsapp_link",
    "whatsapp_verif",
    "pays",
    "entreprise",
    "poste",
    "domaine",
    "site_web",
    "about",
    "app",
    "link",
]


def normalize_cell(value: str | None) -> str:
    if value is None:
        return EMPTY_VALUE
    text = str(value).strip()
    return text if text else EMPTY_VALUE


def is_empty_value(value: str) -> bool:
    return not str(value or "").strip() or str(value).strip().lower() == EMPTY_VALUE


@dataclass
class SearchRequest:
    mode: SearchMode
    query: str
    app: AppName
    limit: int = 20
    linkedin_scopes: tuple[str, ...] = ()
    include_location_keywords: tuple[str, ...] = ()
    exclude_location_keywords: tuple[str, ...] | None = None


@dataclass
class ScraperRecord:
    nom: str = ""
    email: str = ""
    whatsapp: str = ""
    pays: str = ""
    entreprise: str = ""
    poste: str = ""
    domaine: str = ""
    site_web: str = ""
    about: str = ""
    app: str = ""
    link: str = ""

    def to_row(self) -> dict[str, str]:
        from utils.whatsapp_verify import resolve_whatsapp_link_for_export

        wa = normalize_cell(self.whatsapp)
        wa_link, wa_verif = resolve_whatsapp_link_for_export(self.whatsapp)
        return {
            "nom": normalize_cell(self.nom),
            "email": normalize_cell(self.email),
            "whatsapp": wa,
            "whatsapp_link": wa_link,
            "whatsapp_verif": wa_verif,
            "pays": normalize_cell(self.pays),
            "entreprise": normalize_cell(self.entreprise),
            "poste": normalize_cell(self.poste),
            "domaine": normalize_cell(self.domaine),
            "site_web": normalize_cell(self.site_web),
            "about": normalize_cell(self.about),
            "app": normalize_cell(self.app),
            "link": normalize_cell(self.link),
        }
