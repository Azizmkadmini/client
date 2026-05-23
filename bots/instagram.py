from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from bots.base import BaseBot
from config import settings
from leads.models import Channel, Lead


class InstagramBot(BaseBot):
    channel = "instagram"
    session_name = "instagram"

    def __init__(self, store, generator, logger, headless: bool = False) -> None:
        super().__init__(
            store,
            generator,
            logger,
            daily_max=settings.instagram_daily_max,
            headless=headless,
        )

    def _channel_enum(self):
        return Channel.INSTAGRAM

    def prepare_session(self, page: Page) -> None:
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
        if "instagram.com/accounts/login" not in page.url:
            return
        if settings.orchestrator_interactive:
            print(
                "Instagram: complete login in the opened browser window, then press Enter here."
            )
            input()
            return
        raise RuntimeError(
            "Instagram session is not authenticated. Save a session with outreach login."
        )

    def send_to_lead(self, page: Page, lead: Lead, subject: str, message: str) -> None:
        profile_url = self._profile_url(lead)
        page.goto(profile_url, wait_until="domcontentloaded")
        self.behavior.scroll_page(page, passes=2)
        self.behavior.random_delay()
        message_button = page.locator('div[role="button"]:has-text("Message")')
        if message_button.count() == 0:
            message_button = page.locator('a:has-text("Message")')
        if message_button.count() == 0:
            raise PlaywrightTimeout("Could not find Instagram Message button")
        message_button.first.click()
        page.wait_for_timeout(1500)
        textarea = page.locator('textarea[placeholder*="Message"]')
        if textarea.count() == 0:
            textarea = page.locator('div[contenteditable="true"][role="textbox"]')
        textarea.first.click()
        textarea.first.fill(message)
        self.behavior.random_delay()
        send = page.locator('motion.div[role="button"]:has-text("Send")')
        if send.count() == 0:
            send = page.locator('button:has-text("Send")')
        send.first.click()
        page.wait_for_timeout(1500)

    def _profile_url(self, lead: Lead) -> str:
        if lead.link:
            return lead.link
        handle = lead.name.replace(" ", "").lower()
        return f"https://www.instagram.com/{handle}/"
