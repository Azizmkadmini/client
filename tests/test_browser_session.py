from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from config import settings
from utils.browser_session import import_system_browser_cookies, session_path


@pytest.fixture()
def temp_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "project_root", tmp_path)
    monkeypatch.setattr(settings, "session_dir", "sessions")
    (tmp_path / "sessions").mkdir()
    return tmp_path / "sessions"


def test_import_system_browser_cookies_writes_storage(
    temp_sessions: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie = SimpleNamespace(
        name="sessionid",
        value="abc",
        domain=".instagram.com",
        path="/",
        expires=1234567890,
        secure=True,
        _rest={"HttpOnly": True, "SameSite": "Lax"},
    )

    def fake_loader(domain_name: str = "", cookie_file: str | None = None, key_file: str | None = None):
        assert domain_name == ""
        return [cookie]

    def skip_snapshot(_source: str):
        raise RuntimeError("skip snapshot")

    fake_module = SimpleNamespace(chrome=fake_loader)
    monkeypatch.setitem(__import__("sys").modules, "browser_cookie3", fake_module)
    monkeypatch.setattr("utils.browser_session._snapshot_chromium_files", skip_snapshot)

    path = import_system_browser_cookies("instagram", browser_source="chrome")
    assert path == session_path("instagram")
    payload = path.read_text(encoding="utf-8")
    assert "sessionid" in payload
    assert ".instagram.com" in payload


def test_instagram_recaptcha_or_blank_url_detection() -> None:
    from utils.browser_session import _instagram_recaptcha_or_blank_url

    assert _instagram_recaptcha_or_blank_url(
        "https://www.instagram.com/auth_platform/recaptcha/?apc=x"
    )
    assert not _instagram_recaptcha_or_blank_url("https://www.instagram.com/accounts/login/")
