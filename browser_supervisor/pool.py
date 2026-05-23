"""Superviseur de slots navigateur (évite OOM / conflits)."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from config import settings

_locks: dict[str, threading.Lock] = {}
_global = threading.Semaphore(int(getattr(settings, "browser_pool_max_slots", 2) or 2))


def _channel_lock(channel: str) -> threading.Lock:
    if channel not in _locks:
        _locks[channel] = threading.Lock()
    return _locks[channel]


@contextmanager
def browser_slot(channel: str) -> Iterator[None]:
    """Un slot global + verrou par canal (scrape/outreach/publish)."""
    _global.acquire()
    lock = _channel_lock(channel)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        _global.release()


def open_channel_context_supervised(playwright, channel: str, *, headless: bool):
    from utils.browser_session import open_channel_context

    with browser_slot(channel):
        return open_channel_context(playwright, channel, headless=headless)
