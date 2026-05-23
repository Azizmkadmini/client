"""Tests file Redis fiable — claim / ack / recovery / idempotence."""

from __future__ import annotations

import os
import time
import uuid

import pytest

from workers.queue import ACQUISITION_QUEUE, JobQueue, ScraperJob


@pytest.fixture
def redis_url():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        pytest.skip("REDIS_URL non défini")
    return url


@pytest.fixture
def queue(redis_url):
    from workers.queue import QueueNames

    ns = f"test:{uuid.uuid4().hex[:8]}"
    names = QueueNames(
        pending=f"{ns}:pending",
        processing=f"{ns}:processing",
        delayed=f"{ns}:delayed",
        dlq=f"{ns}:dlq",
        job_prefix=f"{ns}:job:",
        idem_prefix=f"{ns}:idem:",
    )
    q = JobQueue(redis_url, names=names)
    yield q
    client = q._client()
    for key in client.scan_iter(f"{ns}*"):
        client.delete(key)


def test_claim_ack(queue):
    job = queue.enqueue("test-job", {"x": 1})
    claimed = queue.claim(timeout=1)
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert queue.stats()["processing"] == 1
    queue.ack(claimed)
    assert queue.stats()["processing"] == 0


def test_recover_stale(queue):
    job = queue.enqueue("test-job", {})
    claimed = queue.claim(timeout=1)
    assert claimed
    # Simule job bloqué
    claimed.started_at = time.time() - 7200
    queue.save(claimed)
    n = queue.recover_stale(max_age_seconds=60)
    assert n >= 1
    assert queue.stats()["pending"] >= 1


def test_idempotency(queue):
    j1 = queue.enqueue("t", {"a": 1}, idempotency_key="idem-1")
    j2 = queue.enqueue("t", {"a": 2}, idempotency_key="idem-1")
    assert j1.job_id == j2.job_id


def test_dlq_after_max_attempts(queue):
    job = queue.enqueue("fail", {}, max_attempts=1)
    c = queue.claim(timeout=1)
    assert c
    c.attempts = 1
    queue.move_to_dlq(c)
    assert job.job_id in queue.list_dlq(limit=10)
