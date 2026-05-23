"""Consumer Redis Streams — analytics + side effects (E2)."""

from __future__ import annotations

import time

from services.events import EventBus


def handle_event(envelope: dict) -> None:
    et = envelope.get("event_type", "")
    payload = envelope.get("payload", envelope)
    tenant_id = envelope.get("tenant_id")
    if et == "content.published":
        from analytics.ingest import ingest_event

        ingest_event("content.published", payload, tenant_id=tenant_id)
    elif et.endswith(".failed"):
        try:
            import sentry_sdk

            sentry_sdk.capture_message(f"Event failed: {et}", level="warning")
        except Exception:
            pass


def run_consumer(group: str = "aios-workers", consumer: str = "c1") -> None:
    bus = EventBus()
    while True:
        if not bus.enabled:
            time.sleep(5)
            continue
        for env in bus.consume(group, consumer, count=10):
            try:
                handle_event(env)
                bus.ack(group, env.get("_msg_id", ""))
            except Exception:
                pass
        time.sleep(1)


if __name__ == "__main__":
    run_consumer()
