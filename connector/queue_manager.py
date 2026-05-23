from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import settings
from connector.models import BotLead


class QueueManager:
    def __init__(
        self,
        queue_path: Optional[Path] = None,
        processed_path: Optional[Path] = None,
        failed_path: Optional[Path] = None,
        sqlite_path: Optional[Path] = None,
    ) -> None:
        self.queue_path = Path(queue_path or settings.path(settings.connector_queue_path))
        self.processed_path = Path(
            processed_path or settings.path(settings.connector_processed_log)
        )
        self.failed_path = Path(failed_path or settings.path(settings.connector_failed_log))
        self.sqlite_path = Path(sqlite_path or settings.path(settings.connector_sqlite_path))
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.processed_path.parent.mkdir(parents=True, exist_ok=True)
        self.failed_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_leads (
                    fingerprint TEXT PRIMARY KEY,
                    name TEXT,
                    company TEXT,
                    email TEXT,
                    linkedin TEXT,
                    instagram TEXT,
                    tag TEXT,
                    processed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS outreach_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS failed_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT,
                    payload TEXT NOT NULL,
                    error TEXT NOT NULL,
                    failed_at TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    resolved INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def is_processed(self, lead: BotLead) -> bool:
        fingerprint = lead.fingerprint()
        if self._processed_in_log(fingerprint):
            return True
        return self._processed_in_sqlite(fingerprint)

    def mark_processed(self, lead: BotLead) -> None:
        fingerprint = lead.fingerprint()
        timestamp = datetime.utcnow().isoformat()
        record = {
            "fingerprint": fingerprint,
            "lead": lead.to_bot_payload(),
            "processed_at": timestamp,
        }
        with self.processed_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO processed_leads
                (fingerprint, name, company, email, linkedin, instagram, tag, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    lead.name,
                    lead.company,
                    lead.email,
                    lead.linkedin,
                    lead.instagram,
                    lead.tag.value,
                    timestamp,
                ),
            )

    def mark_failed(self, lead: BotLead, error: str) -> None:
        fingerprint = lead.fingerprint()
        timestamp = datetime.utcnow().isoformat()
        payload = lead.to_bot_payload()
        record = {
            "fingerprint": fingerprint,
            "lead": payload,
            "error": error,
            "failed_at": timestamp,
        }
        with self.failed_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                """
                INSERT INTO failed_leads
                (fingerprint, payload, error, failed_at, retry_count, resolved)
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (fingerprint, json.dumps(payload), error, timestamp),
            )

    def enqueue(self, leads: list[BotLead]) -> tuple[list[BotLead], list[BotLead]]:
        accepted: list[BotLead] = []
        skipped: list[BotLead] = []
        existing_queue = self._load_queue_file()
        existing_fingerprints = {item["fingerprint"] for item in existing_queue}

        for lead in leads:
            fingerprint = lead.fingerprint()
            if self.is_processed(lead) or fingerprint in existing_fingerprints:
                skipped.append(lead)
                continue
            accepted.append(lead)
            existing_fingerprints.add(fingerprint)

        if accepted:
            self._append_queue_file(accepted)
            self._upsert_sqlite_queue(accepted)
        return accepted, skipped

    def retry_failed(self, limit: Optional[int] = None) -> list[BotLead]:
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            query = """
                SELECT id, payload, retry_count
                FROM failed_leads
                WHERE resolved = 0
                ORDER BY failed_at ASC
            """
            if limit is not None:
                query += f" LIMIT {int(limit)}"
            rows = connection.execute(query).fetchall()

        retry_leads: list[BotLead] = []
        for row in rows:
            payload = json.loads(row["payload"])
            retry_leads.append(BotLead.model_validate(payload))
            with sqlite3.connect(self.sqlite_path) as connection:
                connection.execute(
                    """
                    UPDATE failed_leads
                    SET retry_count = retry_count + 1
                    WHERE id = ?
                    """,
                    (row["id"],),
                )
        return retry_leads

    def resolve_failed(self, lead: BotLead) -> None:
        fingerprint = lead.fingerprint()
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.execute(
                "UPDATE failed_leads SET resolved = 1 WHERE fingerprint = ?",
                (fingerprint,),
            )

    def queue_size(self) -> int:
        queue = self._load_queue_file()
        return len(queue)

    def processed_count(self) -> int:
        if not self.processed_path.exists():
            return 0
        return sum(1 for line in self.processed_path.read_text(encoding="utf-8").splitlines() if line.strip())

    def failed_count(self) -> int:
        with sqlite3.connect(self.sqlite_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM failed_leads WHERE resolved = 0"
            ).fetchone()
        return int(row[0]) if row else 0

    def _processed_in_log(self, fingerprint: str) -> bool:
        if not self.processed_path.exists():
            return False
        for line in self.processed_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("fingerprint") == fingerprint:
                return True
        return False

    def _processed_in_sqlite(self, fingerprint: str) -> bool:
        with sqlite3.connect(self.sqlite_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_leads WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return row is not None

    def _load_queue_file(self) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        data = json.loads(self.queue_path.read_text(encoding="utf-8") or "[]")
        if not isinstance(data, list):
            return []
        return data

    def _append_queue_file(self, leads: list[BotLead]) -> None:
        queue = self._load_queue_file()
        timestamp = datetime.utcnow().isoformat()
        for lead in leads:
            queue.append(
                {
                    "fingerprint": lead.fingerprint(),
                    "enqueued_at": timestamp,
                    "lead": lead.to_bot_payload(),
                }
            )
        self.queue_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_sqlite_queue(self, leads: list[BotLead]) -> None:
        timestamp = datetime.utcnow().isoformat()
        with sqlite3.connect(self.sqlite_path) as connection:
            for lead in leads:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO outreach_queue
                    (fingerprint, payload, status, enqueued_at, updated_at)
                    VALUES (?, ?, 'queued', ?, ?)
                    """,
                    (
                        lead.fingerprint(),
                        json.dumps(lead.to_bot_payload()),
                        timestamp,
                        timestamp,
                    ),
                )
