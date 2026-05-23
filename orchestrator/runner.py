from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ai.generator import MessageGenerator
from bots.email import EmailBot
from bots.instagram import InstagramBot
from bots.linkedin import LinkedInBot
from bots.whatsapp import WhatsAppBot
from config import settings
from connector.ingest import IngestResult, QueueIngestor
from connector.pipeline import ConnectorPipeline, PipelineResult
from leads.store import LeadStore
from logs.logger import OutreachLogger
from orchestrator.scraper import ScraperResult, run_scraper
from utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

CHANNEL_BOTS = {
    "linkedin": LinkedInBot,
    "instagram": InstagramBot,
    "whatsapp": WhatsAppBot,
    "email": EmailBot,
}


@dataclass
class OutreachResult:
    sent_by_channel: dict[str, int] = field(default_factory=dict)
    errors_by_channel: dict[str, str] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    scraper: ScraperResult
    connector: PipelineResult
    ingest: IngestResult
    outreach: OutreachResult
    errors: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        store: Optional[LeadStore] = None,
        generator: Optional[MessageGenerator] = None,
        outreach_logger: Optional[OutreachLogger] = None,
    ) -> None:
        self.store = store or LeadStore()
        self.generator = generator or MessageGenerator()
        self.outreach_logger = outreach_logger or OutreachLogger()

    def run_once(
        self,
        *,
        source: str = "csv",
        retry_failed: bool = False,
        per_channel_limit: Optional[int] = None,
        headless: Optional[bool] = None,
        run_scraper_step: bool = True,
        run_outreach: bool = True,
    ) -> OrchestratorResult:
        scraper_result = run_scraper() if run_scraper_step else ScraperResult(
            output_exists=settings.path(settings.scraper_output_csv).exists()
        )
        connector = ConnectorPipeline()
        connector_result = connector.run(source=source, retry_failed=retry_failed)
        ingest_result = QueueIngestor(store=self.store).ingest()
        outreach_result = OutreachResult()
        errors: list[str] = []

        if scraper_result.error:
            errors.append(scraper_result.error)

        if run_outreach:
            outreach_result, outreach_errors = self._run_outreach(
                per_channel_limit=per_channel_limit,
                headless=headless,
            )
            errors.extend(outreach_errors)

        return OrchestratorResult(
            scraper=scraper_result,
            connector=connector_result,
            ingest=ingest_result,
            outreach=outreach_result,
            errors=errors,
        )

    def run_forever(
        self,
        *,
        hours: float,
        source: str = "csv",
        retry_failed: bool = True,
        per_channel_limit: Optional[int] = None,
        headless: Optional[bool] = None,
    ) -> None:
        if hours <= 0:
            raise ValueError("Schedule interval must be greater than zero hours.")
        interval = hours * 3600
        logger.info("starting orchestrator loop every %s hour(s)", hours)
        while True:
            result = self.run_once(
                source=source,
                retry_failed=retry_failed,
                per_channel_limit=per_channel_limit,
                headless=headless,
            )
            logger.info("orchestrator cycle complete: %s", summarize_result(result))
            time.sleep(interval)

    def _run_outreach(
        self,
        *,
        per_channel_limit: Optional[int],
        headless: Optional[bool],
    ) -> tuple[OutreachResult, list[str]]:
        result = OutreachResult()
        errors: list[str] = []
        use_headless = settings.orchestrator_headless if headless is None else headless

        for channel, bot_cls in CHANNEL_BOTS.items():
            try:
                if channel == "email":
                    bot = bot_cls(self.store, self.generator, self.outreach_logger)
                else:
                    bot = bot_cls(
                        self.store,
                        self.generator,
                        self.outreach_logger,
                        headless=use_headless,
                    )
                sent = bot.run_batch(limit=per_channel_limit)
                result.sent_by_channel[channel] = sent
                logger.info("outreach channel=%s sent=%s", channel, sent)
            except Exception as exc:  # noqa: BLE001
                message = f"{channel}: {exc}"
                result.errors_by_channel[channel] = str(exc)
                errors.append(message)
                self.outreach_logger.log_failed("orchestrator", channel, str(exc))
                logger.exception("outreach failed for channel=%s", channel)

        return result, errors

    def run_channel(
        self,
        channel: str,
        *,
        per_channel_limit: Optional[int] = None,
        headless: Optional[bool] = None,
    ) -> int:
        if channel not in CHANNEL_BOTS:
            raise ValueError(f"Unsupported channel: {channel}")
        use_headless = settings.orchestrator_headless if headless is None else headless
        bot_cls = CHANNEL_BOTS[channel]
        if channel == "email":
            bot = bot_cls(self.store, self.generator, self.outreach_logger)
        else:
            bot = bot_cls(
                self.store,
                self.generator,
                self.outreach_logger,
                headless=use_headless,
            )
        return bot.run_batch(limit=per_channel_limit)


def summarize_result(result: OrchestratorResult) -> dict[str, Any]:
    return {
        "scraper_ran": result.scraper.ran,
        "connector_loaded": result.connector.loaded,
        "connector_enqueued": result.connector.enqueued,
        "ingested": result.ingest.ingested,
        "outreach_sent": result.outreach.sent_by_channel,
        "errors": result.errors,
    }
