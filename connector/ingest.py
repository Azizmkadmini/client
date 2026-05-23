from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from compliance.registry import ComplianceRegistry
from connector.models import BotLead
from connector.queue_manager import QueueManager
from leads.models import Channel, FollowUpStage, Lead, LeadStatus, LeadTag
from leads.store import LeadStore
from storage.database import Database
from utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    loaded: int = 0
    ingested: int = 0
    skipped: int = 0
    opted_out: int = 0
    errors: list[str] = field(default_factory=list)


class QueueIngestor:
    def __init__(
        self,
        store: Optional[LeadStore] = None,
        queue: Optional[QueueManager] = None,
        compliance: Optional[ComplianceRegistry] = None,
        database: Optional[Database] = None,
    ) -> None:
        self.store = store or LeadStore()
        self.queue = queue or QueueManager()
        self.compliance = compliance or ComplianceRegistry()
        self.database = database or Database()
        self.database.migrate()

    def ingest(self, limit: Optional[int] = None) -> IngestResult:
        result = IngestResult()
        queue_items = self.queue._load_queue_file()
        result.loaded = len(queue_items)
        pending = [item for item in queue_items if not self._is_ingested(item.get("fingerprint", ""))]
        if limit is not None:
            pending = pending[:limit]

        for item in pending:
            fingerprint = item.get("fingerprint", "")
            payload = item.get("lead") or {}
            try:
                bot_lead = BotLead.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{fingerprint}: invalid payload ({exc})")
                self._mark_ingest(fingerprint, payload, "failed", str(exc))
                continue

            identifiers = [
                bot_lead.email,
                bot_lead.linkedin,
                bot_lead.instagram,
                bot_lead.name,
            ]
            if any(self.compliance.is_opted_out(value) for value in identifiers if value):
                result.opted_out += 1
                self._mark_ingest(fingerprint, bot_lead.to_bot_payload(), "opted_out", "opt_out")
                continue

            if self.store.find_by_fingerprint(fingerprint):
                result.skipped += 1
                self._mark_ingest(fingerprint, bot_lead.to_bot_payload(), "skipped", "duplicate")
                continue

            lead = self._to_lead(bot_lead, fingerprint)
            self.store.upsert_lead(lead)
            self._mark_ingest(fingerprint, bot_lead.to_bot_payload(), "ingested", "")
            result.ingested += 1
            logger.info("ingested lead fingerprint=%s channel=%s", fingerprint, lead.channel.value)

        return result

    def _to_lead(self, bot_lead: BotLead, fingerprint: str) -> Lead:
        channel, link, phone = self._resolve_channel(bot_lead)
        tag = LeadTag(bot_lead.tag.value)
        return Lead(
            id=str(uuid.uuid4()),
            name=bot_lead.name,
            company=bot_lead.company,
            link=link,
            email=bot_lead.email,
            phone=phone,
            tag=tag,
            status=LeadStatus.QUEUED,
            channel=channel,
            follow_up_stage=FollowUpStage.INTRO,
            fingerprint=fingerprint,
            notes=(bot_lead.notes or "").strip(),
        )

    def _resolve_channel(self, bot_lead: BotLead) -> tuple[Channel, str, str]:
        """Priorité e-mail : les profils scrapés avec adresse partent sur le canal email."""
        if bot_lead.email:
            return Channel.EMAIL, bot_lead.email, ""
        if bot_lead.linkedin:
            return Channel.LINKEDIN, bot_lead.linkedin, ""
        if bot_lead.instagram:
            return Channel.INSTAGRAM, bot_lead.instagram, ""
        if bot_lead.phone:
            return Channel.WHATSAPP, bot_lead.phone, bot_lead.phone
        return Channel.LINKEDIN, "", ""

    def _is_ingested(self, fingerprint: str) -> bool:
        if not fingerprint:
            return False
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM queue_ingest WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return bool(row and row["status"] in {"ingested", "skipped", "opted_out"})

    def _mark_ingest(
        self,
        fingerprint: str,
        payload: dict[str, Any],
        status: str,
        error: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO queue_ingest
                (fingerprint, payload, status, ingested_at, error)
                VALUES (?, ?, ?, datetime('now'), ?)
                """,
                (fingerprint, json.dumps(payload), status, error),
            )
