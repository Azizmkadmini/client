from __future__ import annotations

from services.crypto import decrypt_text, encrypt_text
from services.feature_flags import is_enabled
from services.rbac import role_allows
from services.idempotency import get_cached, store


def test_crypto_roundtrip() -> None:
    raw = "secret-token-123"
    assert decrypt_text(encrypt_text(raw)) == raw


def test_rbac() -> None:
    assert role_allows("editor", "publish")
    assert not role_allows("viewer", "publish")


def test_feature_flags_default() -> None:
    assert is_enabled("content.ai.claude") is True
    assert is_enabled("browser.grid.remote") is False


def test_idempotency(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("config.settings.app_db_path", str(tmp_path / "idem.db"))
    from storage.database import Database

    Database().migrate()
    store("k1", "t1", {"ok": True})
    assert get_cached("k1") == {"ok": True}
