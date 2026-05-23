from __future__ import annotations

from services.linkedin_risk import RiskAssessment, assess


def test_assess_allows_by_default(monkeypatch) -> None:
    monkeypatch.setattr("services.linkedin_risk.settings.redis_url", "")
    r = assess("linkedin", operation="scrape")
    assert isinstance(r, RiskAssessment)
    assert r.risk_score < 90
