from __future__ import annotations

from playwright.sync_api import Page

from bots.base import BaseBot
from config import settings
from leads.models import Channel, Lead
from scraper.extractors import EMPTY_VALUE, normalize_whatsapp_number, parse_whatsapp_from_links


class WhatsAppBot(BaseBot):
    channel = "whatsapp"
    session_name = "whatsapp"

    def __init__(self, store, generator, logger, headless: bool = False) -> None:
        super().__init__(
            store,
            generator,
            logger,
            daily_max=settings.whatsapp_daily_max,
            headless=headless,
        )

    def _channel_enum(self):
        return Channel.WHATSAPP

    def prepare_session(self, page: Page) -> None:
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
        if page.locator('div[data-testid="chat-list"]').count() > 0:
            return
        if settings.orchestrator_interactive:
            print("WhatsApp Web: scan the QR code in the browser, then press Enter here.")
            input()
            return
        raise RuntimeError(
            "WhatsApp session is not authenticated. Save a session with outreach login."
        )

    def send_to_lead(self, page: Page, lead: Lead, subject: str, message: str) -> None:
        phone = self._normalize_phone(lead.phone or lead.link)
        if not phone:
            raise ValueError("Lead is missing WhatsApp phone number")
        page.goto(f"https://web.whatsapp.com/send?phone={phone}", wait_until="domcontentloaded")
        self.behavior.scroll_page(page, passes=1)
        self.behavior.random_delay()
        composer = page.locator('motion.div[contenteditable="true"][data-tab="10"]')
        if composer.count() == 0:
            composer = page.locator('div[contenteditable="true"][data-tab="10"]')
        composer.first.wait_for(timeout=30000)
        composer.first.click()
        composer.first.fill(message)
        self.behavior.random_delay()
        send = page.locator('button[data-testid="compose-btn-send"]')
        if send.count() == 0:
            send = page.locator('span[data-icon="send"]')
        send.first.click()
        page.wait_for_timeout(1500)

    def _normalize_phone(self, raw: str) -> str:
        raw = (raw or "").strip()
        if not raw or raw.lower() in {"vide", "empty", "n/a", "na"}:
            return ""
        lowered = raw.lower()
        if "wa.me" in lowered or "api.whatsapp.com" in lowered or "whatsapp.com/send" in lowered:
            parsed = parse_whatsapp_from_links(raw)
            if parsed != EMPTY_VALUE:
                return parsed
        n = normalize_whatsapp_number(raw)
        if n != EMPTY_VALUE:
            return n
        return "".join(ch for ch in raw if ch.isdigit())
