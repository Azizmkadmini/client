from __future__ import annotations

import pytest

from api.auth_jwt import bootstrap_user, create_token, decode_token


def test_jwt_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.auth_jwt.settings.api_key", "test-secret-key")
    token = create_token(user_id="u1", tenant_id="t1", email="a@test.com")
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "t1"


def test_bootstrap_and_login(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("config.settings.app_db_path", str(tmp_path / "auth.db"))
    monkeypatch.setattr("api.auth_jwt.settings.api_key", "test-key")
    from api.auth_jwt import login_user

    bootstrap_user("test@example.com", "password123")
    out = login_user("test@example.com", "password123")
    assert "access_token" in out
