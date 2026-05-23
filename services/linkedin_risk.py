"""
LinkedIn Risk Engine v2 — ralentit AVANT restriction.

Signaux: health_score, rate limits, échecs récents, captcha keywords, proxy health.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config import settings


@dataclass
class RiskAssessment:
    allowed: bool
    delay_seconds: float = 0.0
    risk_score: float = 0.0  # 0=sain, 100=critique
    reasons: list[str] = field(default_factory=list)
    throttle_factor: float = 1.0  # multiplier sur pauses (>1 = plus lent)


def assess(
    channel: str = "linkedin",
    *,
    tenant_id: str | None = None,
    account_id: str | None = None,
    operation: str = "scrape",
) -> RiskAssessment:
    """Évalue si une action LI peut partir maintenant."""
    tid = tenant_id or settings.default_tenant_id
    reasons: list[str] = []
    score = 0.0

    from services.rate_limit_engine import CentralRateLimiter

    rl = CentralRateLimiter(channel, tenant_id=tid)
    remaining = rl.remaining()
    daily = rl.daily_max
    if daily > 0 and remaining / daily < 0.15:
        score += 40
        reasons.append(f"quota_journalier_bas:{remaining}/{daily}")

    if not rl.can_send():
        return RiskAssessment(
            allowed=False,
            delay_seconds=3600.0,
            risk_score=90.0,
            reasons=["rate_limit_exceeded"],
            throttle_factor=3.0,
        )

    if account_id:
        score, reasons = _account_signals(account_id, score, reasons)

    recent_failures = _recent_failure_count(tid, account_id)
    if recent_failures >= 3:
        score += 25
        reasons.append(f"failures_1h:{recent_failures}")
    if recent_failures >= 5:
        return RiskAssessment(
            allowed=False,
            delay_seconds=1800.0,
            risk_score=min(100.0, score),
            reasons=reasons + ["circuit_open"],
            throttle_factor=5.0,
        )

    throttle = 1.0 + (score / 50.0)
    delay = 0.0
    if score >= 60:
        delay = 300.0 * throttle
    elif score >= 35:
        delay = 60.0 * throttle

    return RiskAssessment(
        allowed=delay < 600 or score < 70,
        delay_seconds=delay,
        risk_score=score,
        reasons=reasons,
        throttle_factor=throttle,
    )


def wait_if_needed(assessment: RiskAssessment) -> None:
    if assessment.delay_seconds > 0 and assessment.allowed:
        time.sleep(min(assessment.delay_seconds, 120.0))


def record_outcome(
    *,
    tenant_id: str | None,
    account_id: str | None,
    success: bool,
    error: str | None = None,
) -> None:
    """Enregistre succès/échec pour circuit breaker."""
    key = _failure_key(tenant_id, account_id)
    try:
        import redis

        if not settings.redis_url:
            return
        client = redis.from_url(settings.redis_url, decode_responses=True)
        if success:
            client.delete(key)
            return
        client.incr(key)
        client.expire(key, 3600)
        err = (error or "").lower()
        if any(w in err for w in ("captcha", "challenge", "verify", "checkpoint")):
            client.setex(f"{key}:captcha", 86400, "1")
            if account_id:
                from content.account_pool import LinkedInAccountPool

                LinkedInAccountPool(tenant_id).record_failure(account_id, delta=30.0)
    except Exception:
        pass


def _failure_key(tenant_id: str | None, account_id: str | None) -> str:
    return f"li:risk:fail:{tenant_id or 'default'}:{account_id or 'global'}"


def _recent_failure_count(tenant_id: str | None, account_id: str | None) -> int:
    try:
        import redis

        if not settings.redis_url:
            return 0
        client = redis.from_url(settings.redis_url, decode_responses=True)
        v = client.get(_failure_key(tenant_id, account_id))
        return int(v or 0)
    except Exception:
        return 0


def _account_signals(account_id: str, score: float, reasons: list[str]) -> tuple[float, list[str]]:
    try:
        from content.accounts import LinkedInAccountStore

        acc = LinkedInAccountStore().get(account_id)
        health = float(acc.get("health_score") or 100)
        if health < 50:
            score += 20
            reasons.append(f"health_low:{health}")
        if health < 25:
            score += 30
            reasons.append("health_critical")
        if acc.get("disabled_at"):
            score = 100.0
            reasons.append("account_disabled")
    except Exception:
        pass
    return score, reasons
