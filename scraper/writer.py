from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import settings
from scraper.models import CSV_COLUMNS, EMPTY_VALUE, ScraperRecord


def resolve_scraper_csv_path(app: str) -> Path:
    """
    Fichier CSV principal (LinkedIn / mixte) vs export dédié Instagram.
    Évite d'écrire les lignes Instagram dans le même CSV que LinkedIn.
    """
    app_l = (app or "").strip().lower()
    if app_l == "instagram":
        raw = (getattr(settings, "scraper_instagram_output_csv", None) or "").strip()
        if raw:
            path = settings.path(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    if app_l == "web":
        raw = (getattr(settings, "scraper_web_output_csv", None) or "").strip()
        if raw:
            path = settings.path(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    path = settings.path(settings.scraper_output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class ScraperWriter:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = Path(output_path or settings.path(settings.scraper_output_csv))
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, records: list[ScraperRecord], *, append: bool = True) -> Path:
        rows = [record.to_row() for record in records]
        incoming = pd.DataFrame(rows, columns=CSV_COLUMNS)
        if append and self.output_path.exists() and self.output_path.stat().st_size > 0:
            existing = pd.read_csv(self.output_path, dtype=str).fillna(EMPTY_VALUE)
            for column in CSV_COLUMNS:
                if column not in existing.columns:
                    existing[column] = EMPTY_VALUE
            combined = pd.concat([existing, incoming], ignore_index=True)
        else:
            combined = incoming
        combined = combined.fillna(EMPTY_VALUE)
        for column in CSV_COLUMNS:
            combined[column] = combined[column].apply(
                lambda value: EMPTY_VALUE if not str(value).strip() else str(value).strip()
            )
        if "link" in combined.columns:
            combined = combined.drop_duplicates(subset=["link"], keep="last")
        combined.to_csv(self.output_path, index=False)
        return self.output_path
