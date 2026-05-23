"""Publication LinkedIn — Playwright + pool comptes (Phase 4)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from config import settings
from content.account_pool import LinkedInAccountPool
from utils.session_channels import LINKEDIN_PUBLISH


def publish_text_post(
    body: str,
    *,
    headless: bool | None = None,
    tenant_id: str | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    from browser_supervisor.pool import browser_slot
    from utils import browser_pool

    channel = getattr(settings, "content_publish_session_channel", None) or LINKEDIN_PUBLISH
    hl = settings.scraper_headless if headless is None else headless
    text = (body or "").strip()
    if not text:
        raise ValueError("Corps du post vide")

    pool = LinkedInAccountPool(tenant_id)
    account = pool.store.get(account_id) if account_id else pool.pick("publish")
    proxy_url = (account or {}).get("proxy_url") or None
    storage_override = None
    if account and account.get("session_path"):
        storage_override = Path(account["session_path"])
    acct_id = (account or {}).get("id")

    from services.linkedin_risk import assess, record_outcome, wait_if_needed

    risk = assess("content_publish", tenant_id=tenant_id, account_id=acct_id, operation="publish")
    if not risk.allowed:
        return {
            "success": False,
            "error": f"throttled: {risk.reasons}",
            "risk_score": risk.risk_score,
            "retry_after": risk.delay_seconds,
        }
    wait_if_needed(risk)

    with browser_slot(channel):
        with browser_pool.page(
            channel,
            headless=hl,
            proxy_url=proxy_url,
            storage_override=storage_override,
        ) as page:
            try:
                page.goto(
                    "https://www.linkedin.com/feed/",
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
                page.wait_for_timeout(2000 + random.randint(0, 800))
                _open_composer(page)
                page.wait_for_timeout(800)
                _fill_composer(page, text)
                page.wait_for_timeout(500 + random.randint(0, 400))
                _click_post(page)
                page.wait_for_timeout(3000 + random.randint(0, 1500))
                url = page.url
                browser_pool.persist_channel(channel)
                if acct_id:
                    pool.record_success(acct_id)
                record_outcome(tenant_id=tenant_id, account_id=acct_id, success=True)
                return {
                    "success": True,
                    "url": url,
                    "channel": channel,
                    "account_id": acct_id,
                }
            except Exception as exc:
                err = str(exc)
                if acct_id:
                    pool.record_failure(acct_id)
                record_outcome(tenant_id=tenant_id, account_id=acct_id, success=False, error=err)
                return {
                    "success": False,
                    "error": err,
                    "channel": channel,
                    "account_id": acct_id,
                }


def _open_composer(page) -> None:
    selectors = [
        'button:has-text("Start a post")',
        'button:has-text("Commencer un post")',
        'button.share-box-feed-entry__trigger',
        'div.share-box-feed-entry__trigger',
        'button[aria-label*="post" i]',
        'button[aria-label*="publication" i]',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            return
    page.locator(".ql-editor, div[contenteditable='true']").first.click()


def _fill_composer(page, text: str) -> None:
    editors = [
        "div.ql-editor[data-placeholder]",
        "div.share-creation-state__text-editor div.ql-editor",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
    ]
    for sel in editors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            loc.first.fill(text)
            return
    raise RuntimeError("Éditeur de post LinkedIn introuvable")


def _click_post(page) -> None:
    selectors = [
        'button:has-text("Post")',
        'button:has-text("Publier")',
        'button.share-actions__primary-action',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            return
    raise RuntimeError("Bouton Publier introuvable")
