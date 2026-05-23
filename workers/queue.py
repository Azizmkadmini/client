"""
File Redis fiable — pending → processing (BRPOPLPUSH), ack, DLQ, recovery.

Pattern:
  LPUSH pending
  BRPOPLPUSH pending processing  (claim atomique)
  LREM processing              (ack après succès)
  ZADD delayed                 (retry backoff)
  LPUSH dlq                    (échec final)
"""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from config import settings

# Acquisition / scraper (legacy keys compat)
QUEUE_PENDING = "outreach:scraper:jobs"
QUEUE_PROCESSING = "outreach:scraper:processing"
QUEUE_DELAYED = "outreach:delayed"
DLQ_KEY = "outreach:dead-letter"
JOB_PREFIX = "outreach:scraper:job:"
IDEM_PREFIX = "outreach:job:idem:"

# Content OS
CONTENT_QUEUE_PENDING = "aios:content:jobs"
CONTENT_QUEUE_PROCESSING = "aios:content:processing"
CONTENT_QUEUE_DELAYED = "aios:content:delayed"
CONTENT_DLQ_KEY = "aios:content:dead-letter"
CONTENT_JOB_PREFIX = "aios:content:job:"
CONTENT_IDEM_PREFIX = "aios:content:job:idem:"


@dataclass(frozen=True)
class QueueNames:
    pending: str
    processing: str
    delayed: str
    dlq: str
    job_prefix: str
    idem_prefix: str


ACQUISITION_QUEUE = QueueNames(
    pending=QUEUE_PENDING,
    processing=QUEUE_PROCESSING,
    delayed=QUEUE_DELAYED,
    dlq=DLQ_KEY,
    job_prefix=JOB_PREFIX,
    idem_prefix=IDEM_PREFIX,
)

CONTENT_QUEUE = QueueNames(
    pending=CONTENT_QUEUE_PENDING,
    processing=CONTENT_QUEUE_PROCESSING,
    delayed=CONTENT_QUEUE_DELAYED,
    dlq=CONTENT_DLQ_KEY,
    job_prefix=CONTENT_JOB_PREFIX,
    idem_prefix=CONTENT_IDEM_PREFIX,
)


@dataclass
class ScraperJob:
    job_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    idempotency_key: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> ScraperJob:
        data = json.loads(raw)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class JobQueue:
    def __init__(
        self,
        redis_url: str | None = None,
        *,
        names: QueueNames | None = None,
    ) -> None:
        self.redis_url = (redis_url or settings.redis_url or "").strip()
        self.names = names or ACQUISITION_QUEUE
        self._pool = None

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url)

    def _client(self):
        if self._pool is None:
            import redis

            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=20,
            )
        import redis

        return redis.Redis(connection_pool=self._pool)

    def _job_key(self, job_id: str) -> str:
        return f"{self.names.job_prefix}{job_id}"

    def _save_blob(self, job: ScraperJob) -> None:
        ttl = int(getattr(settings, "queue_job_ttl_seconds", 604800))
        self._client().set(self._job_key(job.job_id), job.to_json(), ex=ttl)

    def get(self, job_id: str) -> ScraperJob | None:
        if not self.enabled:
            return None
        raw = self._client().get(self._job_key(job_id))
        if not raw:
            return None
        return ScraperJob.from_json(raw)

    def save(self, job: ScraperJob) -> None:
        if not self.enabled:
            return
        self._save_blob(job)
        self._persist_postgres(job)

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> ScraperJob:
        if not self.enabled:
            raise RuntimeError("Redis non configuré (REDIS_URL).")
        client = self._client()
        if idempotency_key:
            idem_key = f"{self.names.idem_prefix}{idempotency_key}"
            existing = client.get(idem_key)
            if existing:
                job = self.get(existing)
                if job:
                    return job
            if not client.set(idem_key, "pending", nx=True, ex=86400):
                existing = client.get(idem_key)
                if existing and existing != "pending":
                    job = self.get(existing)
                    if job:
                        return job

        job = ScraperJob(
            job_type=job_type,
            payload=payload or {},
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
        )
        self._save_blob(job)
        client.lpush(self.names.pending, job.job_id)
        if idempotency_key:
            client.set(f"{self.names.idem_prefix}{idempotency_key}", job.job_id, ex=86400)
        return job

    def claim(self, timeout: int = 5) -> ScraperJob | None:
        """BRPOPLPUSH pending → processing (atomique)."""
        if not self.enabled:
            return None
        client = self._client()
        item = client.brpoplpush(self.names.pending, self.names.processing, timeout=timeout)
        if not item:
            return None
        job_id = item
        raw = client.get(self._job_key(job_id))
        if not raw:
            client.lrem(self.names.processing, 1, job_id)
            return None
        job = ScraperJob.from_json(raw)
        job.status = "running"
        job.started_at = time.time()
        self._save_blob(job)
        return job

    def dequeue(self, timeout: int = 5) -> ScraperJob | None:
        """Alias — utilise claim()."""
        return self.claim(timeout=timeout)

    def ack(self, job: ScraperJob) -> None:
        """Retire le job de la processing list après succès."""
        if not self.enabled:
            return
        self._client().lrem(self.names.processing, 0, job.job_id)

    def recover_stale(self, max_age_seconds: int | None = None) -> int:
        """Remet en pending les jobs bloqués en processing (crash worker)."""
        if not self.enabled:
            return 0
        max_age = max_age_seconds or int(getattr(settings, "worker_processing_stale_seconds", 3600))
        client = self._client()
        recovered = 0
        for job_id in client.lrange(self.names.processing, 0, -1):
            raw = client.get(self._job_key(job_id))
            if not raw:
                client.lrem(self.names.processing, 1, job_id)
                recovered += 1
                continue
            job = ScraperJob.from_json(raw)
            started = job.started_at or job.created_at
            if time.time() - started > max_age:
                client.lrem(self.names.processing, 1, job_id)
                client.lpush(self.names.pending, job_id)
                job.status = "queued"
                job.error = (job.error or "") + " [recovered_from_processing]"
                self._save_blob(job)
                recovered += 1
        return recovered

    def requeue(self, job: ScraperJob, *, delay_seconds: int | None = None) -> None:
        if not self.enabled:
            return
        self.ack(job)
        job.attempts += 1
        job.status = "queued"
        job.started_at = None
        self._save_blob(job)
        base = delay_seconds if delay_seconds is not None else _backoff_seconds(job.attempts)
        jitter = random.uniform(0, min(30, base * 0.2))
        delay = int(base + jitter)
        client = self._client()
        if delay > 0:
            client.zadd(self.names.delayed, {job.job_id: time.time() + delay})
        else:
            client.lpush(self.names.pending, job.job_id)

    def move_to_dlq(self, job: ScraperJob) -> None:
        if not self.enabled:
            return
        self.ack(job)
        job.status = "dead"
        self._save_blob(job)
        self._client().lpush(self.names.dlq, job.job_id)

    def promote_delayed(self) -> int:
        if not self.enabled:
            return 0
        client = self._client()
        now = time.time()
        ids = client.zrangebyscore(self.names.delayed, 0, now)
        for job_id in ids:
            client.lpush(self.names.pending, job_id)
            client.zrem(self.names.delayed, job_id)
        return len(ids)

    def list_dlq(self, limit: int = 50) -> list[str]:
        if not self.enabled:
            return []
        return self._client().lrange(self.names.dlq, 0, limit - 1)

    def replay_dlq(self, job_id: str) -> bool:
        """Rejoue un job depuis la DLQ."""
        if not self.enabled:
            return False
        client = self._client()
        removed = client.lrem(self.names.dlq, 1, job_id)
        if removed:
            job = self.get(job_id)
            if job:
                job.status = "queued"
                job.attempts = 0
                job.error = None
                self._save_blob(job)
            client.lpush(self.names.pending, job_id)
            return True
        return False

    def stats(self) -> dict[str, int]:
        if not self.enabled:
            return {}
        c = self._client()
        return {
            "pending": c.llen(self.names.pending),
            "processing": c.llen(self.names.processing),
            "delayed": c.zcard(self.names.delayed),
            "dlq": c.llen(self.names.dlq),
        }

    def _persist_postgres(self, job: ScraperJob) -> None:
        try:
            from storage.postgres import postgres_configured
            from storage.postgres_backend import persist_scraper_job

            if postgres_configured():
                persist_scraper_job(asdict(job))
        except Exception:
            pass


def _backoff_seconds(attempt: int) -> int:
    """Backoff exponentiel: 30, 120, 600, 1800..."""
    return min(3600, int(30 * (2 ** max(0, attempt - 1))))


# Alias legacy
QUEUE_KEY = QUEUE_PENDING
