"""Tests runtime worker — backoff, success detection."""

from __future__ import annotations

from workers.queue import ScraperJob, _backoff_seconds
from workers.worker_runtime import _default_success


def test_backoff_grows():
    assert _backoff_seconds(1) == 30
    assert _backoff_seconds(3) == 120
    assert _backoff_seconds(10) <= 3600


def test_default_success_content():
    job = ScraperJob(job_type="content-publish", payload={})
    assert _default_success(job, {"success": True})
    assert not _default_success(job, {"success": False, "error": "x"})


def test_default_success_outreach():
    job = ScraperJob(job_type="outreach-email", payload={})
    assert _default_success(job, {"returncode": 0})
    assert not _default_success(job, {"returncode": 1})
