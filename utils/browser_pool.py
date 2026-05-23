"""
Browser singleton par process worker — réutilise Chromium + contextes par canal.

Usage:
    with browser_pool.page(channel, headless=True) as page:
        page.goto(...)
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import settings

_lock = threading.Lock()
_playwright = None
_browser = None
_contexts: dict[str, Any] = {}
_page_count = 0
_recycle_after = int(getattr(settings, "browser_pool_recycle_pages", 50) or 50)


def _needs_recycle() -> bool:
    global _page_count
    return _page_count >= _recycle_after


def _recycle_browser() -> None:
    global _playwright, _browser, _contexts, _page_count
    for ctx in list(_contexts.values()):
        try:
            ctx.close()
        except Exception:
            pass
    _contexts.clear()
    if _browser is not None:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None
    _page_count = 0


def _ensure_browser(headless: bool, proxy_url: str | None):
    global _playwright, _browser
    from playwright.sync_api import sync_playwright

    from utils.browser_session import launch_browser

    if _playwright is None:
        _playwright = sync_playwright().start()
    if _browser is None:
        _browser = launch_browser(_playwright, headless=headless, proxy_url=proxy_url)
    return _playwright, _browser


def _get_context(
    channel: str,
    *,
    headless: bool,
    proxy_url: str | None = None,
    storage_override: Path | str | None = None,
):
    from utils.browser_session import _open_storage_context

    key = f"{channel}:{storage_override or ''}:{proxy_url or ''}"
    if key in _contexts:
        try:
            if _contexts[key].pages:
                return _contexts[key]
        except Exception:
            del _contexts[key]
    pw, browser = _ensure_browser(headless, proxy_url)
    _, context, _ = _open_storage_context(
        pw,
        channel,
        headless=headless,
        proxy_url=proxy_url,
        storage_override=storage_override,
    )
    _contexts[key] = context
    return context


@contextmanager
def page(
    channel: str,
    *,
    headless: bool | None = None,
    proxy_url: str | None = None,
    storage_override: Path | str | None = None,
) -> Iterator[Any]:
    """Context manager — page Playwright avec fermeture garantie."""
    global _page_count
    hl = settings.scraper_headless if headless is None else headless

    with _lock:
        if _needs_recycle():
            _recycle_browser()
        context = _get_context(
            channel,
            headless=hl,
            proxy_url=proxy_url,
            storage_override=storage_override,
        )
        pg = context.new_page()
        _page_count += 1

    try:
        yield pg
    finally:
        try:
            pg.close()
        except Exception:
            pass


def persist_channel(channel: str, context_key: str | None = None) -> None:
    """Persiste storage_state après publish."""
    from utils.browser_session import persist_context_state

    key = context_key or channel
    ctx = _contexts.get(key)
    if ctx is not None:
        persist_context_state(channel, ctx)


def shutdown() -> None:
    with _lock:
        _recycle_browser()
