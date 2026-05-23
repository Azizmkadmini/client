from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from config import settings
from storage.content_migrations import CONTENT_MIGRATIONS


MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        fingerprint TEXT UNIQUE,
        name TEXT NOT NULL,
        company TEXT,
        email TEXT,
        phone TEXT,
        link TEXT,
        linkedin TEXT,
        instagram TEXT,
        tag TEXT NOT NULL,
        status TEXT NOT NULL,
        channel TEXT NOT NULL,
        follow_up_stage INTEGER NOT NULL DEFAULT 1,
        last_contacted_at TEXT,
        next_follow_up_at TEXT,
        notes TEXT,
        consent INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS queue_ingest (
        fingerprint TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        status TEXT NOT NULL,
        ingested_at TEXT,
        error TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS opt_outs (
        identifier TEXT PRIMARY KEY,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_id TEXT,
        payload TEXT,
        created_at TEXT NOT NULL
    );
    """,
)


class Database:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or settings.path(settings.app_db_path))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        all_migrations = MIGRATIONS + CONTENT_MIGRATIONS
        with self.connect() as connection:
            for index, statement in enumerate(all_migrations, start=1):
                connection.executescript(statement)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                    (index,),
                )
            self._ensure_column(connection, "linkedin_accounts", "proxy_url", "TEXT")
            self._ensure_column(connection, "linkedin_accounts", "session_path", "TEXT")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
        cols = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
