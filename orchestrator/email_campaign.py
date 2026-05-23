"""Campagne e-mail : CSV scraper → file → ingest → envoi personnalisé par profil."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from connector.ingest import IngestResult, QueueIngestor
from connector.pipeline import ConnectorPipeline, PipelineResult
from orchestrator.runner import Orchestrator
from utils.smtp_config import smtp_configured


@dataclass
class EmailCampaignResult:
    connector: PipelineResult | None = None
    ingest: IngestResult | None = None
    emails_sent: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_loaded": self.connector.loaded if self.connector else 0,
            "connector_enqueued": self.connector.enqueued if self.connector else 0,
            "ingested": self.ingest.ingested if self.ingest else 0,
            "ingest_skipped": self.ingest.skipped if self.ingest else 0,
            "emails_sent": self.emails_sent,
            "errors": self.errors,
        }


def run_email_campaign_from_scraper_csv(
    *,
    limit: Optional[int] = None,
    retry_failed: bool = False,
) -> EmailCampaignResult:
    """
    1. Charge les CSV scraper (LinkedIn + Instagram si configuré)
    2. Met en file et ingère les leads (canal **email** si adresse présente)
    3. Envoie un e-mail personnalisé (IA) par lead éligible
    """
    result = EmailCampaignResult()
    if not smtp_configured():
        result.errors.append(
            "SMTP non configuré : renseignez SMTP_USER, SMTP_PASSWORD et SMTP_FROM dans .env"
        )
        return result

    connector = ConnectorPipeline()
    result.connector = connector.run(source="csv", retry_failed=retry_failed)

    ingestor = QueueIngestor()
    result.ingest = ingestor.ingest(limit=limit)

    try:
        result.emails_sent = Orchestrator().run_channel("email", per_channel_limit=limit)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(str(exc))
    return result
