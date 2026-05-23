from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings
from storage.database import Database


class ComplianceRegistry:
    def __init__(
        self,
        csv_path: Optional[Path] = None,
        database: Optional[Database] = None,
    ) -> None:
        self.csv_path = Path(csv_path or settings.path(settings.opt_out_csv))
        self.database = database or Database()
        self.database.migrate()
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            pd.DataFrame(columns=["identifier", "reason", "created_at"]).to_csv(
                self.csv_path,
                index=False,
            )

    def is_opted_out(self, identifier: str) -> bool:
        normalized = identifier.strip().lower()
        if not normalized:
            return False
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM opt_outs WHERE lower(identifier) = ?",
                (normalized,),
            ).fetchone()
        return row is not None

    def register_opt_out(self, identifier: str, reason: str = "user_request") -> None:
        normalized = identifier.strip().lower()
        if not normalized:
            return
        timestamp = datetime.utcnow().isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO opt_outs(identifier, reason, created_at)
                VALUES (?, ?, ?)
                """,
                (normalized, reason, timestamp),
            )
        frame = pd.read_csv(self.csv_path, dtype=str).fillna("")
        if normalized not in frame["identifier"].str.lower().tolist():
            frame = pd.concat(
                [
                    frame,
                    pd.DataFrame(
                        [{"identifier": normalized, "reason": reason, "created_at": timestamp}]
                    ),
                ],
                ignore_index=True,
            )
            frame.to_csv(self.csv_path, index=False)

    def filter_allowed(self, identifiers: list[str]) -> list[str]:
        return [value for value in identifiers if not self.is_opted_out(value)]
