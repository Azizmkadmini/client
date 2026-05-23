from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from ai.generator import MessageGenerator
from config import settings
from leads.models import Lead
from leads.store import LeadStore, next_stage
from logs.logger import OutreachLogger
from utils.behavior import HumanBehavior, RateLimiter
from utils.browser_session import (
    close_session,
    open_channel_context,
    persist_context_state,
    session_path,
)


class BaseBot(ABC):
    channel: str = "base"
    session_name: str = "default"

    def __init__(
        self,
        store: LeadStore,
        generator: MessageGenerator,
        logger: OutreachLogger,
        daily_max: int,
        headless: bool = False,
    ) -> None:
        self.store = store
        self.generator = generator
        self.logger = logger
        self.behavior = HumanBehavior()
        self.rate_limiter = RateLimiter(self.channel, daily_max)
        self.headless = headless
        self.session_dir = settings.path(settings.session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.storage_state = session_path(self.session_name)

    def run_batch(self, limit: Optional[int] = None) -> int:
        sent = 0
        leads = self.store.due_for_follow_up(channel=self._channel_enum())
        if limit is not None:
            leads = leads[:limit]

        with sync_playwright() as playwright:
            browser, context, owns_browser = open_channel_context(
                playwright,
                self.session_name,
                headless=self.headless,
            )
            page = context.new_page()
            self.prepare_session(page)
            for lead in leads:
                if not self.rate_limiter.can_send():
                    break
                stage = next_stage(lead)
                try:
                    subject, message = self.generator.generate(
                        lead,
                        stage,
                        self.channel,
                    )
                    if not self.generator.ensure_not_duplicate(message):
                        subject, message = self.generator.generate(
                            lead,
                            stage,
                            self.channel,
                            extra_context="Use different wording from prior outreach.",
                        )
                    self.behavior.random_delay()
                    self.send_to_lead(page, lead, subject, message)
                    self.rate_limiter.record_send()
                    self.store.mark_contacted(lead, stage)
                    self.logger.log_sent(
                        lead.id,
                        self.channel,
                        stage.value,
                        message,
                        subject=subject,
                    )
                    sent += 1
                    self.behavior.maybe_long_pause()
                except Exception as exc:  # noqa: BLE001 - per-lead isolation
                    self.store.mark_failed(lead.id, str(exc))
                    self.logger.log_failed(lead.id, self.channel, str(exc))
            persist_context_state(self.session_name, context)
            close_session(browser, context, owns_browser=owns_browser)
        return sent

    @abstractmethod
    def prepare_session(self, page: Page) -> None:
        raise NotImplementedError

    @abstractmethod
    def send_to_lead(self, page: Page, lead: Lead, subject: str, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def _channel_enum(self):
        raise NotImplementedError
