from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import settings
from connector.models import RawLead


ALLOWED_SQLITE_TABLES = frozenset({"leads", "scraper_leads", "outreach_queue"})


class LeadLoader:
    def __init__(
        self,
        csv_path: Optional[Path] = None,
        sqlite_path: Optional[Path] = None,
        sqlite_table: str = "leads",
        mongo_uri: str = "",
        mongo_db: str = "outreach",
        mongo_collection: str = "scraper_leads",
    ) -> None:
        self.csv_path = Path(csv_path or settings.path(settings.connector_source_csv))
        self.sqlite_path = Path(sqlite_path or settings.path(settings.connector_sqlite_path))
        self.sqlite_table = sqlite_table
        self.mongo_uri = mongo_uri or settings.mongodb_uri
        self.mongo_db = mongo_db or settings.mongodb_db
        self.mongo_collection = mongo_collection or settings.mongodb_collection

    def load(self, source: str) -> list[RawLead]:
        normalized = source.lower().strip()
        if normalized == "csv":
            return self.load_csv()
        if normalized == "sqlite":
            return self.load_sqlite()
        if normalized == "mongo":
            return self.load_mongo()
        raise ValueError(f"Unsupported source: {source}")

    def load_csv(self, path: Optional[Path] = None) -> list[RawLead]:
        if path is not None:
            target = Path(path)
            if not target.exists():
                raise FileNotFoundError(f"CSV source not found: {target}")
            frame = pd.read_csv(target, dtype=str).fillna("")
            return [
                RawLead.from_record(row.to_dict(), source=f"csv:{target.name}")
                for _, row in frame.iterrows()
            ]
        frames: list[pd.DataFrame] = []
        if self.csv_path.exists():
            frames.append(pd.read_csv(self.csv_path, dtype=str).fillna(""))
        extra = (getattr(settings, "scraper_instagram_output_csv", None) or "").strip()
        if extra:
            ig_path = settings.path(extra)
            if ig_path.exists() and ig_path.resolve() != self.csv_path.resolve():
                frames.append(pd.read_csv(ig_path, dtype=str).fillna(""))
        if not frames:
            raise FileNotFoundError(f"CSV source not found: {self.csv_path}")
        merged = pd.concat(frames, ignore_index=True)
        if "link" in merged.columns:
            merged = merged.drop_duplicates(subset=["link"], keep="last")
        return [
            RawLead.from_record(row.to_dict(), source="csv:merged")
            for _, row in merged.iterrows()
        ]

    def load_sqlite(
        self,
        path: Optional[Path] = None,
        table: Optional[str] = None,
    ) -> list[RawLead]:
        target = Path(path or self.sqlite_path)
        if not target.exists():
            raise FileNotFoundError(f"SQLite source not found: {target}")
        table_name = table or self.sqlite_table
        if table_name not in ALLOWED_SQLITE_TABLES:
            raise ValueError(f"Unsupported SQLite table: {table_name}")
        with sqlite3.connect(target) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f'SELECT * FROM "{table_name}"'
            ).fetchall()
        return [
            RawLead.from_record(dict(row), source=f"sqlite:{table_name}")
            for row in rows
        ]

    def load_mongo(
        self,
        uri: Optional[str] = None,
        database: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> list[RawLead]:
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError(
                "MongoDB source requires pymongo. Install with: pip install pymongo"
            ) from exc

        client = MongoClient(uri or self.mongo_uri)
        db_name = database or self.mongo_db
        collection_name = collection or self.mongo_collection
        documents: list[dict[str, Any]] = list(
            client[db_name][collection_name].find({})
        )
        leads: list[RawLead] = []
        for document in documents:
            payload = {key: value for key, value in document.items() if key != "_id"}
            if "_id" in document:
                payload["source_id"] = str(document["_id"])
            leads.append(
                RawLead.from_record(
                    payload,
                    source=f"mongo:{db_name}.{collection_name}",
                )
            )
        return leads
