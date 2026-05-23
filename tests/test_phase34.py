from __future__ import annotations

from services.rate_limit_engine import CentralRateLimiter


def test_central_rate_limiter_file_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.rate_limit_engine.settings.redis_url", "")
    rl = CentralRateLimiter("email", daily_max=3, state_dir=tmp_path)
    assert rl.can_send()
    rl.record_send()
    rl.record_send()
    rl.record_send()
    assert not rl.can_send()


def test_billing_mock_checkout(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("config.settings.app_db_path", str(tmp_path / "bill.db"))
    monkeypatch.setattr("config.settings.stripe_secret_key", "")
    from billing.service import BillingService

    svc = BillingService()
    tid = "00000000-0000-0000-0000-000000000001"
    out = svc.create_checkout_session(tid, plan="pro")
    assert out["mode"] == "mock"
    assert svc.get_balance(tid) >= 500
