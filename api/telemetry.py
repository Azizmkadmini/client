"""OpenTelemetry + Sentry (E0)."""

from __future__ import annotations

from config import settings


def setup_telemetry(app=None) -> None:
    dsn = getattr(settings, "sentry_dsn", "") or ""
    if dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(dsn=dsn, integrations=[FastApiIntegration()], traces_sample_rate=0.1)
        except Exception:
            pass
    if getattr(settings, "otel_enabled", False):
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            if app is not None:
                FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass
