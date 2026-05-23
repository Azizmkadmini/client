from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from config import settings
from connector.cleaner import LeadCleaner, LeadEnricher
from connector.loader import LeadLoader
from connector.logger import ConnectorLogger
from connector.models import BotLead
from connector.queue_manager import QueueManager


@dataclass
class PipelineResult:
    loaded: int = 0
    accepted: int = 0
    rejected: int = 0
    enqueued: int = 0
    skipped: int = 0
    processed: int = 0
    failed: int = 0
    retried: int = 0
    errors: list[str] = field(default_factory=list)


class ConnectorPipeline:
    def __init__(
        self,
        loader: Optional[LeadLoader] = None,
        cleaner: Optional[LeadCleaner] = None,
        enricher: Optional[LeadEnricher] = None,
        queue: Optional[QueueManager] = None,
        logger: Optional[ConnectorLogger] = None,
        export_mode: Optional[str] = None,
    ) -> None:
        self.loader = loader or LeadLoader()
        self.cleaner = cleaner or LeadCleaner()
        self.enricher = enricher or LeadEnricher()
        self.queue = queue or QueueManager()
        self.logger = logger or ConnectorLogger()
        self.export_mode = (export_mode or settings.connector_export_mode).lower()

    def run(self, source: str = "csv", retry_failed: bool = False) -> PipelineResult:
        result = PipelineResult()
        try:
            leads = self.loader.load(source)
            result.loaded = len(leads)
        except Exception as exc:  # noqa: BLE001
            message = f"load_failed: {exc}"
            result.errors.append(message)
            self.logger.log_error({"stage": "load", "error": message})
            return result

        if retry_failed:
            retry_leads = self.queue.retry_failed()
            result.retried = len(retry_leads)
            if retry_leads:
                retry_outcome = self._process_leads(retry_leads, result, source_label="retry")
                result.enqueued += retry_outcome["enqueued"]
                result.skipped += retry_outcome["skipped"]
                result.processed += retry_outcome["processed"]
                result.failed += retry_outcome["failed"]

        clean_result = self.cleaner.clean(leads)
        result.accepted = len(clean_result.accepted)
        result.rejected = len(clean_result.rejected)
        for rejected in clean_result.rejected:
            self.logger.log_rejected(rejected)

        bot_leads = self.enricher.enrich(clean_result.accepted)
        outcome = self._process_leads(bot_leads, result, source_label=source)
        result.enqueued += outcome["enqueued"]
        result.skipped += outcome["skipped"]
        result.processed += outcome["processed"]
        result.failed += outcome["failed"]
        return result

    def _process_leads(
        self,
        leads: list[BotLead],
        result: PipelineResult,
        source_label: str,
    ) -> dict[str, int]:
        enqueued = 0
        skipped = 0
        processed = 0
        failed = 0

        try:
            accepted, duplicates = self.queue.enqueue(leads)
            skipped += len(duplicates)
            for lead in accepted:
                try:
                    self._export_lead(lead)
                    self.queue.mark_processed(lead)
                    self.queue.resolve_failed(lead)
                    self.logger.log_processed(
                        {
                            "source": source_label,
                            "fingerprint": lead.fingerprint(),
                            "lead": lead.to_bot_payload(),
                        }
                    )
                    processed += 1
                    enqueued += 1
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    failed += 1
                    result.errors.append(error)
                    self.queue.mark_failed(lead, error)
                    self.logger.log_error(
                        {
                            "source": source_label,
                            "fingerprint": lead.fingerprint(),
                            "lead": lead.to_bot_payload(),
                            "error": error,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            error = f"enqueue_failed: {exc}"
            result.errors.append(error)
            self.logger.log_error({"stage": "enqueue", "error": error})

        return {
            "enqueued": enqueued,
            "skipped": skipped,
            "processed": processed,
            "failed": failed,
        }

    def _export_lead(self, lead: BotLead) -> None:
        if self.export_mode in {"sqlite", "both"}:
            self._export_sqlite(lead)

    def _export_sqlite(self, lead: BotLead) -> None:
        db_path = settings.path(settings.connector_sqlite_path)
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO outreach_queue
                (fingerprint, payload, status, enqueued_at, updated_at)
                VALUES (?, ?, 'queued', datetime('now'), datetime('now'))
                """,
                (lead.fingerprint(), json.dumps(lead.to_bot_payload())),
            )
