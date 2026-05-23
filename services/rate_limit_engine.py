"""Rate limit central — Redis si disponible, sinon fichiers JSON (Phase 4)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from config import settings

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rate_limits.yaml"


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {"defaults": {}}
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _limits_for(channel: str) -> dict[str, int]:
    cfg = _load_config().get("defaults", {})
    ch = cfg.get(channel, {})
    return {
        "daily_max": int(ch.get("daily_max", getattr(settings, f"{channel}_daily_max", 50))),
        "burst_per_hour": int(ch.get("burst_per_hour", 20)),
    }


class CentralRateLimiter:
    """Compteur journalier + horaire par clé (tenant:channel ou channel seul)."""

    def __init__(
        self,
        channel: str,
        *,
        tenant_id: str | None = None,
        daily_max: int | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self.channel = channel
        self.tenant_id = tenant_id or settings.default_tenant_id
        lim = _limits_for(channel)
        self.daily_max = daily_max if daily_max is not None else lim["daily_max"]
        self.burst_per_hour = lim["burst_per_hour"]
        self.key = f"{self.tenant_id}:{channel}"
        self.state_dir = state_dir or settings.path("logs/rate_limits")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._redis = self._redis_client()

    def _redis_client(self):
        if not settings.redis_url:
            return None
        try:
            import redis

            return redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            return None

    def _file_path(self) -> Path:
        safe = self.key.replace(":", "_")
        return self.state_dir / f"{safe}.json"

    def _load_file(self) -> dict[str, Any]:
        p = self._file_path()
        if not p.exists():
            return self._empty_state()
        data = json.loads(p.read_text(encoding="utf-8"))
        today = date.today().isoformat()
        hour = datetime.utcnow().strftime("%Y-%m-%d-%H")
        if data.get("date") != today:
            data["date"] = today
            data["count"] = 0
        if data.get("hour") != hour:
            data["hour"] = hour
            data["hour_count"] = 0
        return data

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "date": date.today().isoformat(),
            "count": 0,
            "hour": datetime.utcnow().strftime("%Y-%m-%d-%H"),
            "hour_count": 0,
        }

    def _save_file(self, data: dict[str, Any]) -> None:
        self._file_path().write_text(json.dumps(data), encoding="utf-8")

    def remaining(self) -> int:
        data = self._snapshot()
        return max(0, self.daily_max - int(data.get("count", 0)))

    def can_send(self) -> bool:
        data = self._snapshot()
        if int(data.get("count", 0)) >= self.daily_max:
            return False
        return int(data.get("hour_count", 0)) < self.burst_per_hour

    def record_send(self, n: int = 1) -> None:
        if self._redis:
            pipe = self._redis.pipeline()
            day_key = f"rl:{self.key}:day:{date.today().isoformat()}"
            hour_key = f"rl:{self.key}:hour:{datetime.utcnow().strftime('%Y-%m-%d-%H')}"
            pipe.incrby(day_key, n)
            pipe.expire(day_key, 86400 * 2)
            pipe.incrby(hour_key, n)
            pipe.expire(hour_key, 7200)
            pipe.execute()
            return
        data = self._load_file()
        data["count"] = int(data.get("count", 0)) + n
        data["hour_count"] = int(data.get("hour_count", 0)) + n
        data["last_sent_at"] = datetime.utcnow().isoformat()
        self._save_file(data)

    def _snapshot(self) -> dict[str, Any]:
        if self._redis:
            day_key = f"rl:{self.key}:day:{date.today().isoformat()}"
            hour_key = f"rl:{self.key}:hour:{datetime.utcnow().strftime('%Y-%m-%d-%H')}"
            return {
                "count": int(self._redis.get(day_key) or 0),
                "hour_count": int(self._redis.get(hour_key) or 0),
            }
        return self._load_file()
