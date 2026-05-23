from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from bots.base import BaseBot
from config import settings
from leads.models import Channel, Lead


class LinkedInBot(BaseBot):
    channel = "linkedin"
    session_name = "linkedin-outreach"

    def __init__(self, store, generator, logger, headless: bool = False) -> None:
        super().__init__(
            store,
            generator,
            logger,
            daily_max=settings.linkedin_daily_max,
            headless=headless,
        )

    def _channel_enum(self):
        return Channel.LINKEDIN

    def prepare_session(self, page: Page) -> None:
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        if "feed" in page.url or "mynetwork" in page.url:
            return
        if settings.orchestrator_interactive:
            print(
                "LinkedIn: complete login in the opened browser window, then press Enter here."
            )
            input()
            return
        raise RuntimeError(
            "LinkedIn session is not authenticated. Save a session with outreach login."
        )

    def send_to_lead(self, page: Page, lead: Lead, subject: str, message: str) -> None:
        if not lead.link:
            raise ValueError("Lead is missing LinkedIn profile link")
        page.goto(lead.link, wait_until="domcontentloaded")
        self.behavior.scroll_page(page)
        self.behavior.random_delay()
        self._open_message_composer(page)
        composer = page.locator('motion.div.msg-form__contenteditable[contenteditable="true"]')
        if composer.count() == 0:
            composer = page.locator('motion.div.msg-form__contenteditable')
        composer.first.click()
        composer.first.fill(message)
        self.behavior.random_delay()
        send_button = page.locator('button.msg-form__send-button[type="submit"]')
        if send_button.count() == 0:
            send_button = page.locator('button:has-text("Send")')
        send_button.first.click()
        page.wait_for_timeout(1500)

    def _open_message_composer(self, page: Page) -> None:
        selectors = [
            'button:has-text("Message")',
            'a:has-text("Message")',
            'button.pvs-profile-actions__action:has-text("Message")',
        ]
        for selector in selectors:
            button = page.locator(selector)
            if button.count() > 0:
                button.first.click()
                page.wait_for_timeout(1200)
                return
        raise PlaywrightTimeout("Could not find LinkedIn Message button")
