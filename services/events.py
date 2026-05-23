"""Event bus — Redis Streams (E2)."""

from __future__ import annotations

import json
from typing import Any, Iterator

from config import settings

STREAM_KEY = "aios:events"
STREAM_MAXLEN = 100_000  # trim approx — évite croissance infinie


class EventBus:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = (redis_url or settings.redis_url or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url)

    def _client(self):
        import redis

        return redis.from_url(self.redis_url, decode_responses=True)

    def publish(self, event_type: str, envelope: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        client = self._client()
        msg_id = client.xadd(
            STREAM_KEY,
            {"type": event_type, "data": json.dumps(envelope, ensure_ascii=False)},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        return msg_id

    def trim_stream(self, maxlen: int | None = None) -> int:
        if not self.enabled:
            return 0
        client = self._client()
        return client.xtrim(STREAM_KEY, maxlen=maxlen or STREAM_MAXLEN, approximate=True)

    def stream_length(self) -> int:
        if not self.enabled:
            return 0
        return self._client().xlen(STREAM_KEY)

    def consume(self, group: str, consumer: str, count: int = 10) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        client = self._client()
        try:
            client.xgroup_create(STREAM_KEY, group, id="0", mkstream=True)
        except Exception:
            pass
        items = client.xreadgroup(group, consumer, {STREAM_KEY: ">"}, count=count, block=1000)
        out: list[dict[str, Any]] = []
        for _stream, messages in items or []:
            for msg_id, fields in messages:
                try:
                    data = json.loads(fields.get("data", "{}"))
                except json.JSONDecodeError:
                    data = {"raw": fields}
                data["_msg_id"] = msg_id
                out.append(data)
        return out

    def ack(self, group: str, msg_id: str) -> None:
        if self.enabled:
            self._client().xack(STREAM_KEY, group, msg_id)
