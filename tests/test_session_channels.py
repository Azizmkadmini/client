from __future__ import annotations

from pathlib import Path

import pytest

from utils.session_channels import (
    LINKEDIN_LEGACY,
    LINKEDIN_OUTREACH,
    LINKEDIN_SCRAPE,
    first_existing_session,
    login_storage_targets,
    normalize_login_channel,
    outreach_session_channel,
    scrape_session_channel,
)


def test_scrape_and_outreach_channel_names():
    assert scrape_session_channel("linkedin") == LINKEDIN_SCRAPE
    assert outreach_session_channel("linkedin") == LINKEDIN_OUTREACH
    assert scrape_session_channel("instagram") == "instagram"


def test_normalize_login_channel():
    assert normalize_login_channel("linkedin-scrape") == (LINKEDIN_SCRAPE, LINKEDIN_LEGACY)
    assert normalize_login_channel("linkedin") == (LINKEDIN_LEGACY, LINKEDIN_LEGACY)


def test_login_storage_targets_legacy():
    names = login_storage_targets("linkedin")
    assert LINKEDIN_SCRAPE in names and LINKEDIN_OUTREACH in names


def test_first_existing_session_fallback(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "session_dir", str(tmp_path))
    legacy = tmp_path / f"{LINKEDIN_LEGACY}.json"
    legacy.write_text("{}", encoding="utf-8")
    found = first_existing_session("linkedin", role="scrape")
    assert found == legacy
    found_out = first_existing_session("linkedin", role="outreach")
    assert found_out == legacy
