from __future__ import annotations

from pathlib import Path

from utils.browser_session import (
    require_session_file,
    session_available,
    session_path,
)
from utils.session_channels import scrape_session_channel

ScraperError = RuntimeError


def session_file(app: str) -> Path:
    return session_path(scrape_session_channel(app))


def require_session(app: str) -> Path | None:
    channel = scrape_session_channel(app)
    try:
        return require_session_file(channel)
    except RuntimeError as exc:
        raise ScraperError(str(exc)) from exc
